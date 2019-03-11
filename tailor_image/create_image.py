#!/usr/bin/python3
import base64
import os
import pathlib
import sys
import tarfile
from urllib.parse import urlsplit
from urllib import request

import argparse
import boto3
import click
import docker
import github
from jinja2 import Environment, BaseLoader
import rosdistro
import yaml

from . import run_command


def create_image(name: str, distribution: str, apt_repo: str, release_track: str, release_label: str, flavour: str,
                 organization: str, docker_registry: str, rosdistro_index: pathlib.Path, github_key: str,
                 ros_version: str, publish: bool = False):

    # Read configuration files
    recipe = yaml.safe_load(pathlib.Path('/rosdistro/config/images.yaml').open())['images']
    build_type = recipe[name]['build_type']
    package = recipe[name]['package']
    provision_file = recipe[name]['provision_file']

    if build_type == 'docker':
        create_docker_image(name=name, dockerfile=provision_file, distribution=distribution, apt_repo=apt_repo,
                            release_track=release_track, flavour=flavour, release_label=release_label,
                            organization=organization, publish=publish, docker_registry=docker_registry)

    # Only build bare_metal if we're on xenial
    elif build_type == 'bare_metal' and distribution == 'xenial':
        # Get package containing recipes to build images
        src_dir = pathlib.Path('/tmp')
        get_recipes_package(rosdistro_index=rosdistro_index, github_key=github_key, src_dir=src_dir, package=package,
                            ros_version=ros_version)

        create_bare_metal_image(image_name=name, provision_file=provision_file, s3_bucket=apt_repo, src_dir=src_dir,
                                publish=publish)


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


def create_bare_metal_image(image_name: str, provision_file: str, s3_bucket: str, src_dir: pathlib.Path, publish: bool):

    click.echo(f'Building bare metal image with: {provision_file}', err=True)

    # Get path to the different files needed
    ansible_config_path = find_file('ansible.cfg', src_dir)
    provision_file_path = find_file(provision_file, src_dir)
    template_path = find_file('bare_metal.json', src_dir)
    cloud_cfg_path = find_file('cloud.cfg', src_dir)
    cloud_img_path = cloud_cfg_path.replace('cfg', 'img')

    # TODO(gservin) Need to investigate a better way to avoid using locus_sentry
    with open(ansible_config_path) as file:
        text_to_replace = file.read().replace('locus_sentry, ', '')
    with open(ansible_config_path, "w") as file:
        file.write(text_to_replace)

    os.remove(pathlib.Path(find_file('locus_sentry.py', src_dir)))

    # Generate cloud.img
    run_command(['cloud-localds', cloud_img_path, cloud_cfg_path])

    command = ['packer', 'build',
               '-var', f"vm_name={image_name}",
               '-var', 'ansible_command=ansible-playbook',
               '-var', f"ansible_config_path={str(ansible_config_path)}",
               '-var', f"playbook_file={provision_file_path}",
               '-var', f"s3_bucket={s3_bucket}",
               '-var', f"cloud_image={cloud_img_path}",
               '-timestamp-ui',
               template_path]

    run_command(command, stdout=sys.stdout, stderr=sys.stderr)


def find_file(name: str, path: pathlib.Path):
    for root, _, files in os.walk(str(path)):
        for file in files:
            if file == name:
                return os.path.join(root, file)
    return None


def get_recipes_package(rosdistro_index: pathlib.Path, github_key: str, src_dir: pathlib.Path, package: str,
                        ros_version: str):

    # Get dependencies
    index = rosdistro.get_index(rosdistro_index.resolve().as_uri())

    github_client = github.Github(github_key)

    distro = rosdistro.get_distribution(index, ros_version)
    src_dir.mkdir(parents=True, exist_ok=True)

    if package not in distro.repositories:
        click.echo("Package not found")

    # release.url overrides source.url. In most cases they should be equivalent, but sometimes we want to
    # pull from a bloomed repository with patches
    try:
        url = distro.repositories[package].release_repository.url
    except AttributeError:
        url = distro.repositories[package].source_repository.url

    # We're fitting to the rosdistro standard here, release.tags.release is a template that can take
    # parameters, though in our case it's usually just '{{ version }}'.
    try:
        version_template = distro.repositories[package].release_repository.tags['release']
        context = {
            'package': package,
            'version': distro.repositories[package].release_repository.version
        }
        version = Environment(loader=BaseLoader()).from_string(version_template).render(**context)
    except (AttributeError, KeyError):
        version = distro.repositories[package].source_repository.version

    repo_dir = src_dir / package

    pull_repository(package, url, version, repo_dir, github_client)


def pull_repository(repo_name: str, url: str, version: str,
                    repo_dir: pathlib.Path, github_client: github.Github) -> None:
    """ Download and unpack a repository from github
    :param repo_name: Name of repository.
    :param url: Url of github repository.
    :param version: Ref in repository to pull.
    :param repo_dir: Directory where to unpack repostiory.
    :param github_client: Github client.
    """
    click.echo(f'Pulling repository {repo_name} ...', err=True)
    repo_dir.mkdir(parents=True, exist_ok=True)

    try:
        # TODO(pbovbel) Abstract interface away for github/bitbucket/gitlab
        gh_repo_name = urlsplit(url).path[len('/'):-len('.git')]
        gh_repo = github_client.get_repo(gh_repo_name, lazy=False)
        archive_url = gh_repo.get_archive_link('tarball', version)
    except Exception as error:
        click.echo(click.style(f"Failed to determine archive URL for {repo_name} from {url}: {error}",
                               fg="yellow"), err=True)
        raise

    try:
        archive_file = repo_dir / f'{repo_name}.tar.gz'
        with open(archive_file, 'wb') as tarball:
            tarball.write(request.urlopen(archive_url).read())

        with tarfile.open(archive_file) as tar:
            tar.extractall(path=repo_dir)
    except Exception as error:
        click.echo(click.style(f"Failed extract archive {archive_url} to {repo_dir}: {error}",
                               fg="yellow"), err=True)
        raise


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
    parser.add_argument('--ros-version', type=str)
    parser.add_argument('--rosdistro-index', type=pathlib.Path)
    parser.add_argument('--github-key', type=str)

    args = parser.parse_args()

    sys.exit(create_image(**vars(args)))


if __name__ == '__main__':
    main()
