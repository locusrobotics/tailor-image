#!/usr/bin/python3
import datetime
import os
import pathlib
import sys

from typing import Any, List

import argparse
import boto3
import click
import psutil
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
    template_path = find_package(package, f'image_recipes/{name}/{name}.json')
    extra_vars = []  # type: List[Any]

    if build_type == 'docker':
        image_name = f'tailor-image-{name}-{distribution}-{release_label}'
        docker_registry_data = docker_registry.replace('https://', '').split('/')
        ecr_server = docker_registry_data[0]
        ecr_repository = docker_registry_data[1]
        extra_vars = [
            '-var', f'bundle_flavour={flavour}',
            '-var', f'image_name={image_name}',
            '-var', f'organization={organization}',
            '-var', f'ecr_server={ecr_server}',
            '-var', f'ecr_repository={ecr_repository}',
            '-var', f'aws_access_key={os.environ["AWS_ACCESS_KEY_ID"]}',
            '-var', f'aws_secret_key={os.environ["AWS_SECRET_ACCESS_KEY"]}'
        ]

        if not publish:
            extra_vars += ['-except', 'publish']

    # Building takes around 1,5 hours, build only if publish is set to true
    # TODO(gservin): Only build bare_metal if we're on xenial for now, add a better check
    elif build_type == 'bare_metal' and publish and distribution == 'xenial':
        # Get information about base image
        base_image = recipe[name]['base_image']
        base_image_checksum = recipe[name]['base_image_checksum']

        cloud_cfg_path = find_package(package, f'image_recipes/{name}/cloud.cfg')
        cloud_img_path = '/tmp/cloud.cfg'

        # Get base image
        s3_object = boto3.resource('s3')
        base_image_local_path = '/tmp/' + base_image
        base_image_key = release_track + '/images/' + base_image
        s3_object.Bucket(apt_repo).download_file(base_image_key, base_image_local_path)

        # Generate cloud.img
        run_command(['cloud-localds', cloud_img_path, cloud_cfg_path])

        # Generate image name
        today = datetime.date.today().strftime('%Y%m%d')
        image_name = f'{organization}_{name}_{release_label}_{today}'

        extra_vars = [
            '-var', f'vm_name={image_name}',
            '-var', f's3_bucket={apt_repo}',
            '-var', f'cloud_image={cloud_img_path}',
            '-var', f'iso_url={base_image_local_path}',
            '-var', f'iso_checksum={base_image_checksum}',
            '-var', f'cpu_count={psutil.cpu_count()}',
            '-var', f'memory={psutil.virtual_memory().available>>20}',
        ]
    else:
        return 0

    click.echo(f'Building {build_type} image with: {provision_file}', err=True)

    # Get path to the different files needed
    provision_file_path = find_package(package, 'playbooks/' + provision_file)

    os.environ['ANSIBLE_CONFIG'] = find_package(package, 'ansible.cfg')

    command = ['packer', 'build',
               '-var', f'playbook_file={provision_file_path}',
               '-var', f'bundle_track={release_track}',
               '-var', f'bundle_version={release_label}'] + extra_vars + ['-timestamp-ui', template_path]

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
