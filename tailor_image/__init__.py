__version__ = "0.0.0"

import json
import os
import pathlib
import random
import re
import sys
import subprocess
import time

from collections import namedtuple
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List

import boto3
import botocore
import click


IMAGE_REGEX = r"([\w.-]+)_(\d{8}.\d{6}).(.*)"


@dataclass
class ImageEntry:
    name: str
    version: str
    extension: str

    def __str__(self):
        return f"{self.name}_{self.version}.{self.extension}"

    def __hash__(self):
        return hash((self.name, self.version, self.extension))


def find_package(package: str, path: str, env):
    if package == "/tailor-image":
        path = f"{package}/environment/{path}"
    else:
        path = (
            run_command(["catkin_find", package, path, "--first-only"], stdout=subprocess.PIPE, env=env)
            .stdout.decode()
            .replace("\n", "")
        )
    return path


def run_command(cmd, check=True, *args, **kwargs):
    click.echo(" ".join(cmd), file=sys.stderr)
    return subprocess.run(cmd, check=check, *args, **kwargs)


def source_file(path):
    dump = '/usr/bin/python3 -c "import os, json; print(json.dumps(dict(os.environ)))"'
    pipe = subprocess.Popen(["/bin/bash", "-c", f"source {path} && {dump}"], stdout=subprocess.PIPE)
    return json.loads(pipe.stdout.read())


def tag_file(client, bucket, key, tag_key, tag_value):
    tagset = {"TagSet": [{"Key": tag_key, "Value": tag_value}]}
    click.echo(f"Setting Lock on {key} to: {tag_value}")
    client.put_object_tagging(Bucket=bucket, Key=key, Tagging=tagset)


def wait_for_index(client, bucket, key):
    # Wait until file is not locked to avoid race condition
    now = datetime.now()
    start_time = now
    random.seed(int(now.strftime("%Y%m%d%H%M%S")))
    timeout = 300 + random.random() * 300  # random timeout from 5 to 10 minutes
    stop_checking = False
    while True:
        if stop_checking:
            break
        try:
            time.sleep(random.random() * 5.0)
            tags = client.get_object_tagging(Bucket=bucket, Key=key)
            for tag in tags["TagSet"]:
                time_delta = datetime.now() - start_time
                click.echo(
                    f'Checking tag: {tag["Key"]}:{tag["Value"]}'
                )
                if tag["Key"] == "Lock" and tag["Value"] == "False":
                    tag_file(client, bucket, key, "Lock", "True")
                    break
                if tag["Key"] == "Lock" and tag["Value"] == "True":
                    # If timeout is reached, allow writing to index
                    time_delta = datetime.now() - start_time
                    if time_delta.total_seconds() >= timeout:
                        stop_checking = True
                        break
                    time.sleep(2.0)
            else:
                continue
            break
        except botocore.exceptions.ClientError as error:
            if error.response["Error"]["Code"] in ["NoSuchKey", "MethodNotAllowed"]:
                # Index file doesn't exists, create an empty one
                click.echo(f"{bucket}/{key} doesn't exist, creating...")
                client.put_object(Bucket=bucket, Key=key, Body="{}", Tagging="Lock=True")
                break


def invalidate_file_cloudfront(distribution_id, key):
    client = boto3.client("cloudfront")
    client.create_invalidation(
        DistributionId=distribution_id,
        InvalidationBatch={
            "Paths": {
                "Quantity": 1,
                "Items": [
                    f"/{key}",
                ],
            },
            "CallerReference": datetime.now().strftime("%Y%m%d%H%M%S"),
        },
    )


def merge_dicts(dict_a, dict_b, path=None):
    "Merges dictionary b into dictionary a"
    if path is None:
        path = []
    for key in dict_b:
        if key in dict_a:
            if isinstance(dict_a[key], dict) and isinstance(dict_b[key], dict):
                merge_dicts(dict_a[key], dict_b[key], path + [str(key)])
            elif dict_a[key] == dict_b[key]:
                pass  # same leaf value
            else:
                raise Exception("Conflict at %s" % ".".join(path + [str(key)]))
        else:
            dict_a[key] = dict_b[key]
    return dict_a


def parse_image_name(image_path: str) -> ImageEntry:
    match = re.search(IMAGE_REGEX, image_path)
    return ImageEntry(*match.groups())


def list_s3_images(client, bucket, prefix) -> List[ImageEntry]:
    """List S3 images."""
    files = []

    objects = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    if "Contents" in objects:
        for obj in objects["Contents"]:
            files.append(parse_image_name(obj["Key"]))

    return files


def delete_s3_images(images: Iterable[ImageEntry], bucket: str, prefix: str):
    """
    Delete files from s3, including all versions if versioning is enabled.
    """
    s3_resource = boto3.resource("s3")
    bucket = s3_resource.Bucket(bucket)

    for image in images:
        key = f"{prefix}/{image}"

        click.echo(f"Deleting {image}")

        # Delete all versions if versioning is enabled
        object_versions = bucket.object_versions.filter(Prefix=key)
        for version in object_versions:
            version.delete()

        # Also delete the current object (in case versioning is not enabled)
        bucket.Object(key).delete()


def read_index_file(client, bucket, index_key):
    # Helper method
    json.load_s3 = lambda f: json.load(client.get_object(Bucket=bucket, Key=f)["Body"])

    data = {}
    try:
        # Wait for file to be ready to write
        wait_for_index(client, bucket, index_key)
        data = json.load_s3(index_key)
        tag_file(client, bucket, index_key, "Lock", "False")
    except botocore.exceptions.ClientError as error:
        # If file doesn't exists, we'll create a new one
        if error.response["Error"]["Code"] == "NoSuchKey":
            click.echo("Index file doesn't exist, creating a new one")

    return data


def update_index_file(data, client, bucket, index_key):
    """Updates image index file."""
    json.dump_s3 = lambda obj, f: client.put_object(Bucket=bucket, Key=f, Body=json.dumps(obj, indent=2))

    # Write data to index file
    wait_for_index(client, bucket, index_key)
    json.dump_s3(data, index_key)
    tag_file(client, bucket, index_key, "Lock", "False")
