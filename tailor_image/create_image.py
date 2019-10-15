#!/usr/bin/python3
import datetime
import json
import os
import pathlib
import sys

from typing import Any, List

import argparse
import boto3
import botocore
import click
import yaml

from . import find_package, run_command, source_file


def create_image(name: str, distribution: str, apt_repo: str, release_track: str, release_label: str, flavour: str,
                 organization: str, docker_registry: str, rosdistro_path: pathlib.Path, publish: bool = False):
    """Create different type of images based on recipes
    :param name: Name for the image
    :param distribution: Ubuntu distribution to build the image against
    :param apt_repo: APT repository to get debian packages from
    :param release_track: The main release track to use for naming, packages, etc
    :param release_label: Contains the release_track + the label for the most current version
    :param flavour: Bundle flavour to install on the images
    :param organization: Name of the organization
    :param docker_registry: URL for the docker registry to use to push images from/to
    :param rosdistro_path: Path for the rosdistro configuration files
    :param publish: Whether to publish the images
    """

    # Read configuration files
    common_config = yaml.safe_load((rosdistro_path / 'config/recipes.yaml').open())['common']
    recipe = yaml.safe_load((rosdistro_path / 'config/images.yaml').open())['images']
    distro = recipe[name]['distro']
    build_type = recipe[name]['build_type']
    env = source_file(f'{os.environ["BUNDLE_ROOT"]}/{distro}/setup.bash')
    today = datetime.date.today().strftime('%Y%m%d')
    extra_vars = []  # type: List[Any]

    if 'package' in recipe[name]:
        package = recipe[name]['package']
    else:
        package = '/tailor-image'

    provision_file = recipe[name]['provision_file']

    template_path = find_package(package, f'image_recipes/{name}/{name}.json', env)
    provision_file_path = find_package(package, 'playbooks/' + provision_file, env)
    ansible_path = find_package(package, 'ansible.cfg', env)

    if ansible_path is not None:
        env['ANSIBLE_CONFIG'] = ansible_path

    if build_type == 'docker':
        image_name = f'tailor-image-{name}-{distribution}-{release_label}'
        docker_registry_data = docker_registry.replace('https://', '').split('/')
        ecr_server = docker_registry_data[0]
        ecr_repository = docker_registry_data[1]
        extra_vars = [
            '-var', f'bundle_flavour={flavour}',
            '-var', f'image_name={image_name}',
            '-var', f'ecr_server={ecr_server}',
            '-var', f'os_version={distribution}',
            '-var', f'ecr_repository={ecr_repository}',
            '-var', f'aws_access_key={os.environ["AWS_ACCESS_KEY_ID"]}',
            '-var', f'aws_secret_key={os.environ["AWS_SECRET_ACCESS_KEY"]}'
        ]

        if not publish:
            extra_vars += ['-except', 'publish']

    elif build_type == 'bare_metal' and publish and distribution == 'xenial':
        # Get information about base image
        base_image = recipe[name]['base_image'].replace('$distribution', distribution)
        optional_vars = []
        optional_var_names = ['username', 'password', 'extra_arguments_ansible', 'ansible_command']
        for var in optional_var_names:
            if var in recipe[name]:
                optional_vars.extend(['-var', f'{var}={recipe[name][var]}'])

        # Get base image
        base_image_local_path = '/tmp/' + base_image
        base_image_key = release_track + '/images/' + base_image
        click.echo(f'Downloading image from {base_image_key}')
        boto3.resource('s3').Bucket(apt_repo).download_file(base_image_key, base_image_local_path)

        # Enable nbd kernel module, necesary for qemu's packer chroot builder
        run_command(['modprobe', 'nbd'])

        # Resize image
        run_command(['qemu-img', 'resize', base_image_local_path, '+9G'])

        # Copy image
        tmp_image = base_image_local_path.replace('disk1', 'disk1-resized')
        run_command(['cp', base_image_local_path, tmp_image])

        # Resize partition inside qcow image
        run_command(['virt-resize', '--expand', '/dev/sda1', base_image_local_path, tmp_image])
        run_command(['mv', tmp_image, base_image_local_path])

        # Generate image name
        image_name = f'{organization}_{name}_{distribution}_{release_label}_{today}'

        extra_vars = [
            '-var', f'image_name={image_name}',
            '-var', f's3_bucket={apt_repo}',
            '-var', f'iso_image={base_image_local_path}',
        ]

        extra_vars.extend(optional_vars)

    else:
        return 0

    click.echo(f'Building {build_type} image with: {provision_file}', err=True)

    command = ['packer', 'build',
               '-var', f'playbook_file={provision_file_path}',
               '-var', f'organization={organization}',
               '-var', f'bundle_track={release_track}',
               '-var', f'bundle_version={release_label}'] + extra_vars + ['-timestamp-ui', template_path]

    run_command(command, env=env)

    # TODO(gservin): If we build more that one bare metal image at the same time, we can have a race condition here
    if build_type == 'bare_metal' and publish and distribution == 'xenial':
        update_image_index(release_track, apt_repo, common_config, image_name)


def update_image_index(release_track, apt_repo, common_config, image_name):
    index_key = release_track + '/images/index'
    s3_object = boto3.resource("s3").Bucket(apt_repo)
    json.load_s3 = lambda f: json.load(s3_object.Object(key=f).get()["Body"])
    json.dump_s3 = lambda obj, f: s3_object.Object(key=f).put(Body=json.dumps(obj, indent=2))
    _, _, distribution, release_label, _ = image_name.split('_')

    # Read checksum from generated file
    with open(f'/tmp/{image_name}', 'r') as checksum_file:
        checksum = checksum_file.read().replace('\n', '').split(' ')[0]
    os.remove(f'/tmp/{image_name}')

    data = {'latest': {release_label: {distribution: ''}}}

    try:
        data = json.load_s3(index_key)
    except botocore.exceptions.ClientError as error:
        # If file doesn't exists, we'll create a new one
        if error.response['Error']['Code'] == "404":
            pass

    # Update latest image
    if release_label not in data['latest']:
        data['latest'][release_label] = {distribution: image_name}
    else:
        data['latest'][release_label][distribution] = image_name

    # Add checksum for new image
    data[image_name] = checksum

    json.dump_s3(data, index_key)

    # Invalidate image index cache
    if 'cloudfront_distribution_id' in common_config:
        distribution_id = common_config['cloudfront_distribution_id']
        client = boto3.client('cloudfront')
        client.create_invalidation(DistributionId=distribution_id,
                                   InvalidationBatch={
                                       'Paths': {
                                           'Quantity': 1,
                                           'Items': [
                                               f'/{index_key}',
                                           ]
                                       },
                                       'CallerReference':  datetime.datetime.now().strftime('%Y%m%d%H%M%S')
                                   })


def main():
    parser = argparse.ArgumentParser(description=create_image.__doc__)
    parser.add_argument('--name', type=str, required=True)
    parser.add_argument('--distribution', type=str, required=True)
    parser.add_argument('--apt-repo', type=str)
    parser.add_argument('--release-track', type=str)
    parser.add_argument('--release-label', type=str)
    parser.add_argument('--flavour', type=str)
    parser.add_argument('--organization', type=str)
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--docker-registry', type=str)
    parser.add_argument('--rosdistro-path', type=pathlib.Path)

    args = parser.parse_args()

    sys.exit(create_image(**vars(args)))


if __name__ == '__main__':
    main()
