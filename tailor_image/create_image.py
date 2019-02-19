#!/usr/bin/python3
import argparse
import base64
import boto3
import click
import docker
import os
import sys


def create_image(name: str, build_type: str, package: bool, provision_file: str, distribution: str, apt_repo: str,
                 release_track: str, flavour: str, organization: str, publish: bool = False):
    if build_type == 'docker':
        create_docker_image(name=name, dockerfile=provision_file, distribution=distribution, apt_repo=apt_repo,
                            release_track=release_track, flavour=flavour, organization=organization, publish=publish)

    elif build_type == 'bare_metal':
        create_bare_metal_image(provision_file)


def create_bare_metal_image(provision_file: str):
    click.echo(f'Building bare metal image with: {provision_file}', err=True)


def create_docker_image(name: str, dockerfile: str, distribution: str, apt_repo: str, release_track: str, flavour: str,
                        organization: str, publish: bool):

    click.echo(f'Building docker image with: {dockerfile}')
    docker_client = docker.from_env()

    ecr_client = boto3.client('ecr', region_name='us-east-1')
    token = ecr_client.get_authorization_token()
    username, password = base64.b64decode(token['authorizationData'][0]['authorizationToken']).decode().split(':')
    registry = token['authorizationData'][0]['proxyEndpoint']

    if not docker_client.login(username, password, registry=registry, reauth=True)['Status'] == 'Login Succeeded':
        click.echo(f'Failed to login to {registry}, verify credentianls.', err=True)
        return 1

    tag = 'tailor-image-' + distribution + '-' + name + '-image'
    full_tag = registry.replace('https://', '') + ':' + tag

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
    logs = None
    try:
        image, logs = docker_client.images.build(path='.',
                                                 dockerfile=dockerfile,
                                                 tag=full_tag,
                                                 nocache=True,
                                                 rm=True,
                                                 buildargs=buildargs)

        if publish:
            for line in docker_client.images.push(registry.replace('https://', ''), tag=tag, stream=True, decode=True):
                click.echo(line, err=True)

        click.echo(f'Image successfully built: {image}')
    except docker.errors.ImageNotFound as error:
        click.echo(f'Build failed, image not found: {error}', err=True)
    except docker.errors.APIError as error:
        click.echo(f'Docker API Error: {error}', err=True)
    except docker.errors.BuildError as error:
        click.echo(f'Error building docker image: {error}', err=True)

    if logs is not None:
        for log in logs:
            try:
                log_cleaned = log['stream'].replace('\n', '')
                click.echo(f'{log_cleaned}', err=True)
            except KeyError:
                pass

    return 0


def main():
    parser = argparse.ArgumentParser(description=create_image.__doc__)
    parser.add_argument('--name', type=str, required=True)
    parser.add_argument('--build-type', type=str, required=True)
    parser.add_argument('--package', type=str, required=True)
    parser.add_argument('--provision-file', type=str, required=True)
    parser.add_argument('--distribution', type=str)
    parser.add_argument('--apt-repo', type=str)
    parser.add_argument('--release_track', type=str)
    parser.add_argument('--flavour', type=str)
    parser.add_argument('--organization', type=str)
    parser.add_argument('--publish', action='store_true')

    args = parser.parse_args()

    sys.exit(create_image(**vars(args)))


if __name__ == '__main__':
    main()
