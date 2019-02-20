#!/usr/bin/python3
import base64
import json
import os
import sys

import argparse
import boto3
import click
import docker


def create_image(name: str, build_type: str, package: bool, provision_file: str, distribution: str, apt_repo: str,
                 release_track: str, flavour: str, organization: str, docker_registry: str, publish: bool = False):
    if build_type == 'docker':
        create_docker_image(name=name, dockerfile=provision_file, distribution=distribution, apt_repo=apt_repo,
                            release_track=release_track, flavour=flavour, organization=organization, publish=publish,
                            docker_registry=docker_registry)

    elif build_type == 'bare_metal':
        create_bare_metal_image(provision_file)


def create_bare_metal_image(provision_file: str):
    click.echo(f'Building bare metal image with: {provision_file}', err=True)


def create_docker_image(name: str, dockerfile: str, distribution: str, apt_repo: str, release_track: str, flavour: str,
                        organization: str, docker_registry: str, publish: bool):

    click.echo(f'Building docker image with: {dockerfile}')
    docker_client = docker.APIClient(base_url='unix://var/run/docker.sock')

    ecr_client = boto3.client('ecr', region_name='us-east-1')
    token = ecr_client.get_authorization_token()
    username, password = base64.b64decode(token['authorizationData'][0]['authorizationToken']).decode().split(':')

    tag = 'tailor-image-' + distribution + '-' + name + '-image'
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
        for line in docker_client.build(path='.',
                                        dockerfile=dockerfile,
                                        tag=full_tag,
                                        nocache=True,
                                        rm=True,
                                        buildargs=buildargs):
            process_docker_api_line(line)

        if publish:
            for line in docker_client.push(docker_registry.replace('https://', ''),
                                           tag=tag,
                                           stream=True,
                                           decode=True,
                                           auth_config={'username': username, 'password': password}):
                click.echo(line, err=True)

        click.echo(f'Image successfully built: {full_tag}')
    except docker.errors.APIError as error:
        click.echo(f'Docker API Error: {error}', err=True)

    return 0


def process_docker_api_line(payload):
    """ Process the output from API stream, throw an Exception if there is an error """
    # Sometimes Docker sends to "{}\n" blocks together...
    for segment in payload.split(b'\n'):
        line = segment.strip()
        if line:
            try:
                line_payload = json.loads(line)
            except ValueError as err:
                click.echo(f'Could not decipher payload from API: {err}', err=True)

            if line_payload:
                if 'errorDetail'in line_payload:
                    error = line_payload["errorDetail"]
                    click.echo(f'Error on build: {error["message"]}', err=True)
                elif 'stream' in line_payload:
                    if line_payload['stream'].endswith('\n'):
                        line_payload['stream'] = line_payload['stream'][:-1]

                    if line_payload['stream'] != '':
                        click.echo(line_payload["stream"], err=True)


def main():
    parser = argparse.ArgumentParser(description=create_image.__doc__)
    parser.add_argument('--name', type=str, required=True)
    parser.add_argument('--build-type', type=str, required=True)
    parser.add_argument('--package', type=str, required=True)
    parser.add_argument('--provision-file', type=str, required=True)
    parser.add_argument('--distribution', type=str)
    parser.add_argument('--apt-repo', type=str)
    parser.add_argument('--release-track', type=str)
    parser.add_argument('--flavour', type=str)
    parser.add_argument('--organization', type=str)
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--docker-registry', type=str)

    args = parser.parse_args()

    sys.exit(create_image(**vars(args)))


if __name__ == '__main__':
    main()
