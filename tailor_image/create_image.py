#!/usr/bin/python3
import base64
import json
import os
import pathlib
import subprocess
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
                 organization: str, docker_registry: str, rosdistro_path: pathlib.Path, github_token: str,
                 ros_version: str, publish: bool = False):

    # Read configuration files
    recipe = yaml.safe_load(pathlib.Path(find_in_path('images.yaml', rosdistro_path)).open())['images']
    build_type = recipe[name]['build_type']
    package = recipe[name]['package']
    provision_file = recipe[name]['provision_file']

    # Get and build package containing recipes to build images
    src_dir = pathlib.Path('/home/tailor/tools_ws/src')
    get_recipes_package(rosdistro_path=rosdistro_path, github_token=github_token, src_dir=src_dir,
                        package=package, ros_version=ros_version)
    run_command(['catkin', 'build', package, '--workspace', str(src_dir.parent)])
    env = env_from_sourcing(str(src_dir.parent / 'install/setup.bash'))

    if build_type == 'docker':
        create_docker_image(name=name, dockerfile=provision_file, distribution=distribution, apt_repo=apt_repo,
                            release_track=release_track, flavour=flavour, release_label=release_label,
                            organization=organization, publish=publish, docker_registry=docker_registry)

    # Building takes around 1,5 hours, build only if publish is set to true
    # TODO(gservin): Only build bare_metal if we're on xenial for now, add a better check
    elif build_type == 'bare_metal' and publish and distribution == 'xenial':
        # Get information about base image
        base_image_link = recipe[name]['base_image_link']
        base_image_checksum = recipe[name]['base_image_checksum']
        create_bare_metal_image(image_name=name, provision_file=provision_file, s3_bucket=apt_repo, src_dir=src_dir,
                                base_image_link=base_image_link, base_image_checksum=base_image_checksum, env=env)


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


def create_bare_metal_image(image_name: str, provision_file: str, s3_bucket: str, src_dir: pathlib.Path,
                            base_image_link: str, base_image_checksum: str, env: dict):

    click.echo(f'Building bare metal image with: {provision_file}', err=True)

    # Get path to the different files needed
    provision_file_path = find_in_path(provision_file, src_dir)
    template_path = find_in_path('bare_metal.json', src_dir)
    cloud_img_path = find_in_path('cloud.cfg', src_dir).replace('cfg', 'img')

    env['ANSIBLE_CONFIG'] = find_in_path('ansible.cfg', src_dir)

    # Generate cloud.img
    run_command(['cloud-localds', cloud_img_path, find_in_path('cloud.cfg', src_dir)])

    command = ['packer', 'build',
               '-var', f'vm_name={image_name}',
               '-var', f'playbook_file={provision_file_path}',
               '-var', f's3_bucket={s3_bucket}',
               '-var', f'cloud_image={cloud_img_path}',
               '-var', f'iso_url={base_image_link}',
               '-var', f'iso_checksum={base_image_checksum}',
               '-timestamp-ui',
               template_path]

    run_command(command, env=env, stdout=sys.stdout, stderr=sys.stderr)


def env_from_sourcing(file_to_source_path, include_unexported_variables=False):
    # returns a dictionary of the environment variables resulting from sourcing a file
    source = '%ssource %s' % ("set -a && " if include_unexported_variables else "", file_to_source_path)
    dump = '/usr/bin/python -c "import os, json; print json.dumps(dict(os.environ))"'
    pipe = subprocess.Popen(['/bin/bash', '-c', '%s && %s' % (source, dump)], stdout=subprocess.PIPE)
    return json.loads(pipe.stdout.read())


def find_in_path(name: str, path: pathlib.Path):
    result = list(path.glob('**/' + name))
    if result:
        return str(result[0])
    return None


def get_recipes_package(rosdistro_path: pathlib.Path, github_token: str, src_dir: pathlib.Path, package: str,
                        ros_version: str):

    # Get dependencies
    index = rosdistro.get_index(pathlib.Path(find_in_path('index.yaml', rosdistro_path)).resolve().as_uri())

    github_client = github.Github(github_token)

    distro = rosdistro.get_distribution(index, ros_version)
    src_dir.mkdir(parents=True, exist_ok=True)

    if package not in distro.repositories:
        click.echo('Package not found')

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
        click.echo(click.style(f'Failed to determine archive URL for {repo_name} from {url}: {error}',
                               fg='yellow'), err=True)
        raise

    try:
        archive_file = repo_dir / f'{repo_name}.tar.gz'
        with open(archive_file, 'wb') as tarball:
            tarball.write(request.urlopen(archive_url).read())

        with tarfile.open(archive_file) as tar:
            tar.extractall(path=repo_dir)
    except Exception as error:
        click.echo(click.style(f'Failed extract archive {archive_url} to {repo_dir}: {error}',
                               fg='yellow'), err=True)
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
    parser.add_argument('--rosdistro-path', type=pathlib.Path)
    parser.add_argument('--github-token', type=str)

    args = parser.parse_args()

    sys.exit(create_image(**vars(args)))


if __name__ == '__main__':
    main()
