#!/usr/bin/python3
import argparse
import click
import bisect
import sys

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Iterable, Dict, Set, Optional, Tuple

import boto3

from . import (
    ImageEntry,
    list_s3_images,
    delete_s3_images,
    read_index_file,
    update_index_file,
)


VERSION_DATE_FORMAT = "%Y%m%d.%H%M%S"


def build_deletion_list(images: Iterable[ImageEntry], num_to_keep: int = None, date_to_keep: datetime = None):
    """Filter a debian package list down to packages to be deleted given some rules.
    :param packages: packages to filter
    :param num_to_keep: number of packages of the same to keep
    :param date_to_keep: date before which to discard packages
    :return: list of package names to delete
    """
    image_versions: Dict[Tuple[str, str], Set[str]] = defaultdict(set)

    for image in images:
        version = image.version
        image_versions[(image.name, image.extension)].add(version)

    delete_packages = set()

    for (name, extension), version_set in image_versions.items():
        delete_versions = set()
        sorted_versions = sorted(version_set)

        if num_to_keep is not None:
            # pylint: disable=E1130
            delete_versions.update(sorted_versions[:-num_to_keep])
        if date_to_keep is not None:
            date_string = date_to_keep.strftime(VERSION_DATE_FORMAT)
            oldest_to_keep = bisect.bisect_left(sorted_versions, date_string)
            delete_versions.update(sorted_versions[:oldest_to_keep])

        delete_packages.update({ImageEntry(name, version, extension) for version in delete_versions})

    return delete_packages


def cleanup_index(image_index, keep_images) -> Dict[Any, Any]:
    """Cleanup index file."""
    versions_in_index = set(image_index)

    # Get list of image versions to keep
    versions_to_keep = set()
    for image in keep_images:
        versions_to_keep.add(image.version)

    # Remove image versions from index
    versions_to_remove = versions_in_index - versions_to_keep
    for version in versions_to_remove:
        image_index.pop(version)

    return image_index


def cleanup_images(
    organization: str,
    release_label: str,
    apt_repo: str,
    days_to_keep: int = None,
    num_to_keep: int = None,
    dry_run: bool = False,
) -> None:
    """Cleanup images according to a cleanup policy (days/number of packages to keep).
    :param organization: Name of the organization
    :param release_label: Release label of apt repo to target.
    :param apt_repo: S3 bucket where to publish release label.
    :param days_to_keep: (Optional) Age in days at which old images should be cleaned up.
    :param num_to_keep: (Optional) Quantity of old images to keep.
    """
    s3_client = boto3.client("s3")
    prefix = f"{release_label}/images"

    if days_to_keep is not None:
        date_to_keep: Optional[datetime] = datetime.now() - timedelta(days=days_to_keep)
    else:
        date_to_keep = None

    remote_images = list_s3_images(s3_client, apt_repo, prefix + f"/{organization}")
    to_delete = build_deletion_list(remote_images, num_to_keep, date_to_keep)
    if not dry_run:
        delete_s3_images(to_delete, apt_repo, prefix)
    else:
        click.echo("[DRY RUN] Would delete images from repo:")
        for image in to_delete:
            click.echo(image)

    # Calculate the list of images to keep
    keep_images = set(remote_images) - to_delete

    # Get index file with image versions
    index_key = release_label + "/images/index"
    image_index = read_index_file(s3_client, apt_repo, index_key)
    image_index = cleanup_index(image_index, keep_images)

    if not dry_run:
        click.echo("Updating index file")
        update_index_file(image_index, s3_client, apt_repo, index_key)
    else:
        click.echo("[DRY RUN] New version in index file:")
        for version in image_index.keys():
            click.echo(version)


def main():
    parser = argparse.ArgumentParser(description=cleanup_images.__doc__)
    parser.add_argument("--release-label", type=str, required=True)
    parser.add_argument("--apt-repo", type=str, required=True)
    parser.add_argument("--organization", type=str, required=True)
    parser.add_argument("--days-to-keep", type=int)
    parser.add_argument("--num-to-keep", type=int)
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    sys.exit(cleanup_images(**vars(args)))


if __name__ == "__main__":
    main()
