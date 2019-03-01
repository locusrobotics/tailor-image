#!/usr/bin/python3
import base64
import os
import sys

import argparse
import boto3
import click
import docker


def create_image(name: str, build_type: str, package: bool, provision_file: str, distribution: str, apt_repo: str,
                 release_track: str, release_label: str, flavour: str, organization: str, docker_registry: str,
                 publish: bool = False):
    if build_type == 'docker':
        create_docker_image(name=name, dockerfile=provision_file, distribution=distribution, apt_repo=apt_repo,
                            release_track=release_track, flavour=flavour, release_label=release_label,
                            organization=organization, publish=publish, docker_registry=docker_registry)

    elif build_type == 'bare_metal':
        create_bare_metal_image(provision_file)


def create_bare_metal_image(provision_file: str):
    # TODO(gservin): Add steps to create bare metal on CI [RST-1668]
    click.echo(f'Building bare metal image with: {provision_file}', err=True)


def create_docker_image(name: str, dockerfile: str, distribution: str, apt_repo: str, release_track: str, flavour: str,
                        release_label: str, organization: str, docker_registry: str, publish: bool):

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


def main():
    parser = argparse.ArgumentParser(description=create_image.__doc__)
    parser.add_argument('--name', type=str, required=True)
    parser.add_argument('--build-type', type=str, required=True)
    parser.add_argument('--package', type=str, required=True)
    parser.add_argument('--provision-file', type=str, required=True)
    parser.add_argument('--distribution', type=str)
    parser.add_argument('--apt-repo', type=str)
    parser.add_argument('--release-track', type=str)
    parser.add_argument('--release-label', type=str)
    parser.add_argument('--flavour', type=str)
    parser.add_argument('--organization', type=str)
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--docker-registry', type=str)

    args = parser.parse_args()

    sys.exit(create_image(**vars(args)))


if __name__ == '__main__':
    main()
