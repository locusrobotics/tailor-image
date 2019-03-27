#!/usr/bin/python3
import base64
import os
import pathlib
import sys

import argparse
import boto3
import click
import docker
import yaml

from catkin.find_in_workspaces import find_in_workspaces
from . import run_command


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
    recipe = yaml.safe_load((rosdistro_path / 'config/images.yaml').open())['images']
    build_type = recipe[name]['build_type']
    package = recipe[name]['package']
    provision_file = recipe[name]['provision_file']

    if build_type == 'docker':
        create_docker_image(name=name, dockerfile=provision_file, distribution=distribution, apt_repo=apt_repo,
                            release_track=release_track, flavour=flavour, release_label=release_label,
                            organization=organization, publish=publish, docker_registry=docker_registry)

    # Building takes around 1,5 hours, build only if publish is set to true
    # TODO(gservin): Only build bare_metal if we're on xenial for now, add a better check
    elif build_type == 'bare_metal' and publish and distribution == 'xenial':
        # Get information about base image
        base_image = recipe[name]['base_image']
        base_image_checksum = recipe[name]['base_image_checksum']
        create_bare_metal_image(image_name=name, package=package, provision_file=provision_file, s3_bucket=apt_repo,
                                release_track=release_track, release_label=release_label, base_image=base_image,
                                base_image_checksum=base_image_checksum)


def create_docker_image(name: str, dockerfile: str, distribution: str, apt_repo: str, release_track: str, flavour: str,
                        release_label: str, organization: str, docker_registry: str, publish: bool):
    """Create docker images
    :param name: Name for the image
    :param dockerfile: Dockerfile to use to build the image
    :param distribution: Ubuntu distribution to build the image against
    :param apt_repo: APT repository to get debian packages from
    :param release_track: The main release track to use for naming, packages, etc
    :param release_label: Contains the release_track + the label for the most current version
    :param flavour: Bundle flavour to install on the images
    :param organization: Name of the organization
    :param docker_registry: URL for the docker registry to use to push images from/to
    :param publish: Whether to publish the images
    """

    click.echo(f'Building docker image with: {dockerfile}')
    docker_client = docker.from_env()

    ecr_client = boto3.client('ecr', region_name='us-east-1')
    token = ecr_client.get_authorization_token()
    username, password = base64.b64decode(token['authorizationData'][0]['authorizationToken']).decode().split(':')

    tag = 'tailor-image-' + name + '-' + distribution + '-' + release_label
    full_tag = docker_registry.replace('https://', '') + ':' + tag

    buildargs = {
        'OS_NAME': 'ubuntu',
        'OS_VERSION': distribution,
        'APT_REPO': apt_repo,
        'RELEASE_LABEL': release_label,
        'RELEASE_TRACK': release_track,
        'ORGANIZATION': organization,
        'FLAVOUR': flavour,
        'AWS_ACCESS_KEY_ID': os.environ['AWS_ACCESS_KEY_ID'],
        'AWS_SECRET_ACCESS_KEY': os.environ['AWS_SECRET_ACCESS_KEY']
    }

    # Build using provided dockerfile
    try:
        image, logs = docker_client.images.build(path='.',
                                                 dockerfile=dockerfile,
                                                 tag=full_tag,
                                                 nocache=True,
                                                 rm=True,
                                                 buildargs=buildargs)

        for line in logs:
            process_docker_api_line(line)

        if publish:
            auth_config = {'username': username, 'password': password}
            for line in docker_client.images.push(docker_registry.replace('https://', ''),
                                                  tag=tag,
                                                  stream=True,
                                                  decode=True,
                                                  auth_config=auth_config):
                process_docker_api_line(line)

        click.echo(f'Image successfully built: {image.tags[0]}')
    except docker.errors.APIError as error:
        click.echo(f'Docker API Error: {error}', err=True)
    except docker.errors.BuildError as error:
        for line in error.build_log:
            process_docker_api_line(line)

    return 0


def process_docker_api_line(line):
    """ Process the output from API stream """
    if 'errorDetail'in line:
        error = line["errorDetail"]
        click.echo(f'Error: {error["message"]}', err=True)
    elif 'stream' in line:
        if line['stream'].endswith('\n'):
            line['stream'] = line['stream'][:-1]

        if line['stream'] != '':
            click.echo(line["stream"], err=True)
    elif 'status' in line:
        click.echo(line["status"], err=True)


def create_bare_metal_image(image_name: str, package: str, provision_file: str, s3_bucket: str, release_track: str,
        release_label: str, base_image: str, base_image_checksum: str):
    """Create bare metal image using packer and provisioned via ansible
    :param name: Name for the image
    :param package: Package containing the configuration files
    :param provision_file: Name of the ansible playbook to use to provision the image
    :param s3_bucket: S3 bucket to push the image to
    :param base_image: Image name on the s3_bucket to use as base
    :param base_image_checksum: Checksum of the base image
    :param release_track: The main release track to use for naming, packages, etc
    :param release_label: Contains the release_track + the label for the most current version
    """

    click.echo(f'Building bare metal image with: {provision_file}', err=True)

    # Get path to the different files needed
    provision_file_path = find_package(package, 'playbooks/' + provision_file)
    template_path = find_package(package, 'image_recipes/bare_metal/bare_metal.json')
    cloud_cfg_path = find_package(package, 'image_recipes/bare_metal/cloud.cfg')
    cloud_img_path = '/tmp/cloud.cfg'

    os.environ['ANSIBLE_CONFIG'] = find_package(package, 'ansible.cfg')

    # Get base image
    s3_object = boto3.resource('s3')
    base_image_local_path = '/tmp/' + base_image
    base_image_key = release_track + '/images/' + base_image
    s3_object.Bucket(s3_bucket).download_file(base_image_key, base_image_local_path)

    # Generate cloud.img
    run_command(['cloud-localds', cloud_img_path, cloud_cfg_path])

    command = ['packer', 'build',
               '-var', f'vm_name={image_name}',
               '-var', f'playbook_file={provision_file_path}',
               '-var', f's3_bucket={s3_bucket}',
               '-var', f'cloud_image={cloud_img_path}',
               '-var', f'iso_url={base_image_local_path}',
               '-var', f'iso_checksum={base_image_checksum}',
               '-var', f'bundle_track={release_track}',
               '-var', f'bundle_version={release_label}',
               '-timestamp-ui',
               template_path]

    run_command(command)


def find_package(package_name: str, filename: str):
    package_path = find_in_workspaces(
        project=package_name,
        path=filename,
        first_match_only=True,
    )[0]

    return package_path


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
