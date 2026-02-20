#!/usr/bin/python3
import json
import os
import pathlib
import sys

from typing import Any, List
from datetime import datetime

import argparse
import click
import yaml

import boto3
import botocore

from . import (
    find_package,
    merge_dicts,
    run_command,
    source_file,
    tag_file,
    wait_for_index,
    invalidate_file_cloudfront
)


def create_image(name: str, distribution: str, apt_repo: str, release_track: str, release_label: str, flavour: str,
                 organization: str, docker_registry: str, rosdistro_path: pathlib.Path, timestamp:str,
                 publish: bool = False):
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
    :param timestamp: Timestamp of the current image build
    :param publish: Whether to publish the images
    """

    # Read configuration files
    common_config = yaml.safe_load((rosdistro_path / 'config/recipes.yaml').open())['common']
    recipe = yaml.safe_load((rosdistro_path / 'config/images.yaml').open())['images']
    distro = recipe[name]['distro']
    build_type = recipe[name]['build_type']
    env = source_file(f'{os.environ["BUNDLE_ROOT"]}/{distro}/setup.bash')
    today = timestamp
    extra_vars: List[Any] = []

    try:
        package = recipe[name]['package']
        provision_file = recipe[name]['provision_file']
    except KeyError:
        package = '/tailor-image'
        provision_file = f'{build_type}.yaml'

    env['ANSIBLE_CONFIG'] = find_package(package, 'ansible.cfg', env)
    template_path = f'/tailor-image/environment/image_recipes/{build_type}/{build_type}.json'
    provision_file_path = find_package(package, 'playbooks/' + provision_file, env)

    optional_vars = []
    optional_var_names = ['username', 'password', 'extra_arguments_ansible',
                          'ansible_command', 'description', 'disk_size', 'group']

    for var in optional_var_names:
        if var in recipe[name]:
            optional_vars.extend(['-var', f'{var}={recipe[name][var]}'])

    if build_type == 'docker':
        image_name = f'tailor-image-{name}-{distribution}-{release_label}'
        docker_registry_data = docker_registry.replace('https://', '').split('/')
        entrypoint_path ='/tailor-image/environment/image_recipes/docker/entrypoint.sh'
        ecr_server = docker_registry_data[0]
        ecr_repository = docker_registry_data[1]
        image_base_tag = f'{ecr_server}/{ecr_repository}:{image_name}-base'
        image_tag = f'{ecr_server}/{ecr_repository}:{image_name}'
        dockerfile_path=f'/tailor-image/environment/image_recipes/{build_type}/Dockerfile'
        build_args = [
            '--build-arg', f'OS_VERSION={distribution}',
            '--build-arg', f'ORGANIZATION={organization}',
            '--build-arg', f'BUNDLE_FLAVOUR={flavour}',
            '--build-arg', f'BUNDLE_VERSION={release_label}',
            '--build-arg', f'AWS_ACCESS_KEY_ID={os.environ["AWS_ACCESS_KEY_ID"]}',
            '--build-arg', f'APT_REPO={common_config['apt_repo']}',
            '--build-arg', f'USERNAME={recipe[name]['username']}',
            '--secret','id=aws_secret,src=build-context/aws-secret.env',
            '--secret', 'id=creds,src=build-context/creds.env'
        ]

        click.echo(f'Building {build_type} image {image_base_tag}', err=True)
        click.echo('Preparing build context...', err=True)
        run_command(['rm', '-rf', 'build-context'])
        run_command(['mkdir', '-p', 'build-context'])
        run_command(['cp', entrypoint_path, 'build-context/entrypoint.sh'])
        with open('build-context/aws-secret.env', 'w') as f:
            f.write(f'AWS_SECRET_ACCESS_KEY={os.environ.get("AWS_SECRET_ACCESS_KEY")}')
        with open('build-context/creds.env', 'w') as f:
            f.write(f'PASSWORD={recipe[name]["password"]}')

        # Run docker build command
        container_name = 'default'
        run_command(['docker', 'rm', '-f', container_name], check=False)
        docker_build_cmd = (
            ['docker', 'build','--progress=plain','--target', 'runtime']
            + build_args
            + ['-f', dockerfile_path, '-t', image_base_tag]
            + ['build-context']
        )
        run_command(docker_build_cmd)

        # Configure docker with ansible
        click.echo(f'Configure {build_type} image {image_tag} with: {provision_file}', err=True)
        run_command([
            'docker', 'run', '-d', '--name', container_name, image_base_tag, 'sleep', 'infinity'
        ])
        ansible_cmd = [
            'bash', '-lc',
            f'source "{os.environ["BUNDLE_ROOT"]}/{distro}/setup.bash" && '
            f'{recipe[name]['ansible_command']} "{provision_file_path}" '
            f'-i "{container_name}", '
            '-e ansible_connection=docker '
            f'-e ansible_host="{container_name}" '
            f'-e organization="{organization}" '
            f'-e bundle_version="{release_label}" '
            f'-e bundle_flavour="{flavour}" '
            f'{recipe[name]['extra_arguments_ansible']} '
            '--vault-password-file=/home/tailor/.vault_pass.txt '
        ]

        # Run ansible command inside ansible package
        os.chdir(f'{os.environ["BUNDLE_ROOT"]}/{distro}/share/{recipe[name]['package']}')
        run_command(ansible_cmd)
        run_command(['docker', 'commit', container_name, image_tag])

        if publish:
            click.echo('Docker login...', err=True)
            login_command = f"aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin {ecr_server}"
            run_command([login_command], shell=True)
            click.echo('Push docker image', err=True)
            run_command(['docker', 'push', image_tag])
            logout_cmd = f"docker logout {ecr_server}"
            run_command([logout_cmd], shell=True)

        run_command(['rm', '-rf', 'build-context'])
        run_command(['docker', 'rm', '-f', container_name], check=False)
        click.echo(f'Image {build_type} finished building', err=True)
        return 0

    elif build_type in ['bare_metal', 'lxd'] and publish:
        # Get information about base image
        base_image = recipe[name]['base_image'].replace('$distribution', distribution)

        # Get disk size to use
        disk_size = recipe[name].get('disk_size', 9) # In GB

        # Get base image
        base_image_local_path = '/tmp/' + base_image
        base_image_key = release_label + '/images/' + base_image
        click.echo(f'Downloading image from {base_image_key}')
        try:
            boto3.resource('s3').Bucket(apt_repo).download_file(base_image_key, base_image_local_path)
        except botocore.exceptions.ClientError:
            click.echo(f'Unable to download base image from {base_image_key}, creating a new one')
            run_command(['bash',
                         '/tailor-image/environment/create_base_image.bash',
                         f'{base_image_local_path}',
                         f'{distribution}'])
            boto3.resource('s3').Bucket(apt_repo).upload_file(base_image_local_path, base_image_key)

        # Enable nbd kernel module, necesary for qemu's packer chroot builder
        run_command(['modprobe', 'nbd'])

        # Resize image
        run_command(['qemu-img', 'resize', base_image_local_path, '30G'])

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
            '-var', f'distribution={distribution}',
            '-var', f'disk_size={disk_size}'
        ]

        # Make sure to clean old image builds
        run_command(['rm', '-rf', '/tmp/images'])

    elif build_type == 'ami':
        image_name = f'{organization}_{name}_{distribution}_ami_{release_label}'
        # Get ami-id for base image
        source_ami_id = recipe[name]['source_ami'].get(distribution)

        if not source_ami_id:
            click.echo(f'You need to specify a bas AMI for the desired distribution {distribution}')
            sys.exit(1)

        # Increase fow how long we wait for image to be ready. Default is 30 minutes, sometime it might take longer
        env['AWS_MAX_ATTEMPTS'] = '90' # minutes
        env['AWS_POLL_DELAY_SECONDS'] = '60' # Poll for status every minute

        extra_vars = [
            '-var', f'build_date={today}',
            '-var', f'image_name={image_name}',
            '-var', f'name={name}',
            '-var', f'source_ami_id={source_ami_id}',
            '-var', f'distribution={distribution}',
            '-var', f'release_label={release_label}',
            '-var', f'aws_access_key={os.environ["AWS_ACCESS_KEY_ID"]}',
            '-var', f'aws_secret_key={os.environ["AWS_SECRET_ACCESS_KEY"]}'
        ]
    else:
        return 0

    extra_vars.extend(optional_vars)

    click.echo(f'Building {build_type} image with: {provision_file}', err=True)

    command = ['packer', 'build',
               '-var', f'playbook_file={provision_file_path}',
               '-var', f'organization={organization}',
               '-var', f'bundle_track={release_track}',
               '-var', f'bundle_version={release_label}'] + extra_vars + ['-timestamp-ui', template_path]

    run_command(command, env=env, cwd='/tmp')

    if build_type in ['bare_metal', 'lxd'] and publish:
        update_image_index(release_label, apt_repo, common_config, image_name)


def update_image_index(release_label, apt_repo, common_config, image_name):
    """Updates the index file used to track bare metal images

    Current format:
    {
      "<timestamp>": {
        "raw": {
          "bot": {
            "<distribution>": {
              "file": "<organization>_<flavour>_<distribution>_<release_label>_<date><time>",
              "checksum": <md5sum_of_image>
            }
          }
        }
      },
      ...
    }
    """
    s3 = boto3.client('s3')

    # Helper methods
    json.load_s3 = lambda f: json.load(s3.get_object(Bucket=apt_repo, Key=f)['Body'])
    json.dump_s3 = lambda obj, f: s3.put_object(Bucket=apt_repo,
                                                Key=f,
                                                Body=json.dumps(obj, indent=2))

    index_key = release_label + '/images/index'

    _, flavour, distribution, release_label, timestamp = image_name.split('_')

    # Read checksum from generated file
    with open(f'/tmp/{image_name}', 'r') as checksum_file:
        checksum = checksum_file.read().replace('\n', '').split(' ')[0]
    os.remove(f'/tmp/{image_name}')

    image_data = {
        'raw': {
            flavour: {
                distribution: {
                    'file': image_name,
                    'checksum': checksum
                }
            }
        }
    }

    data = {}
    try:
        # Wait for file to be ready to write
        wait_for_index(s3, apt_repo, index_key)
        data = json.load_s3(index_key)
    except botocore.exceptions.ClientError as error:
        # If file doesn't exists, we'll create a new one
        if error.response['Error']['Code'] == 'NoSuchKey':
            click.echo('Index file doesn\'t exist, creating a new one')

    try:
        data[timestamp] = merge_dicts(data[timestamp], image_data)
    except KeyError:
        data[timestamp] = image_data

    # Write data to index file
    json.dump_s3(data, index_key)
    tag_file(s3, apt_repo, index_key, 'Lock', 'False')

    # Invalidate image index cache
    if 'cloudfront_distribution_id' in common_config:
        invalidate_file_cloudfront(common_config['cloudfront_distribution_id'], index_key)


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
    parser.add_argument(
        '--timestamp', type=str, default=datetime.now().strftime("%Y%m%d.%H%M%S")
    )

    args = parser.parse_args()

    # Print full command, useful for debugging
    click.echo(' '.join(sys.argv))

    sys.exit(create_image(**vars(args)))


if __name__ == '__main__':
    main()
