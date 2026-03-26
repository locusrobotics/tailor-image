#!/usr/bin/python3
import argparse
import bisect
import sys

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Iterable, Dict, Set, Optional, Tuple

import boto3
import click


from . import (
    ImageEntry,
    list_s3_images,
    list_s3_directories,
    delete_s3_images,
    delete_s3_change_log,
    read_index_file,
    unlock_index_file,
    wait_for_index,
    write_index_file,
)


VERSION_DATE_FORMAT = "%Y%m%d.%H%M%S"


def build_directories_deletion_list(directories: Iterable[str], num_to_keep: int = None, date_to_keep: datetime = None) -> Set[str]:
    """Return the directories to delete given retention rules."""
    sorted_directories = sorted(set(directories))
    delete_directories = set()

    if num_to_keep is not None:
        delete_directories.update(sorted_directories[:-num_to_keep])

    if date_to_keep is not None:
        date_string = date_to_keep.strftime(VERSION_DATE_FORMAT)
        oldest_to_keep = bisect.bisect_left(sorted_directories, date_string)
        delete_directories.update(sorted_directories[:oldest_to_keep])

    return delete_directories


def build_image_deletion_list(images: Iterable[ImageEntry], num_to_keep: int = None, date_to_keep: datetime = None):
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

    delete_images = set()

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

        delete_images.update({ImageEntry(name, version, extension) for version in delete_versions})

    return delete_images


def is_valid_directory(directory_name: str) -> bool:
    """Return true if an S3 directory matches the configured version timestamp format."""
    try:
        datetime.strptime(directory_name, VERSION_DATE_FORMAT)
        return True
    except ValueError:
        return False


def cleanup_change_logs(
    s3_client,
    organization: str,
    apt_repo: str,
    release_label: str,
    days_to_keep: int = None,
    num_to_keep: int = None,
    dry_run: bool = False,
) -> None:
    """Cleanup change logs under {release_label}/changes according to retention rules.
    :param s3_client: S3 client to use for S3 operations.
    :param organization: Name of the organization
    :param release_label: Release label of apt repo to target.
    :param apt_repo: S3 bucket where to publish release label.
    :param days_to_keep: (Optional) Age in days at which old images should be cleaned up.
    :param num_to_keep: (Optional) Quantity of old images to keep.
    :param dry_run: If true, only print the images that would be deleted without actually deleting them.
    """
    changes_prefix = f"{release_label}/changes"
    changes_directories = list_s3_directories(s3_client, apt_repo, changes_prefix)

    valid_directories = set()
    for directory_name in changes_directories:
        if is_valid_directory(directory_name):
            valid_directories.add(directory_name)
        else:
            click.echo(f"Skipping invalid directory name: {changes_prefix}/{directory_name}/")

    if days_to_keep is not None:
        date_to_keep: Optional[datetime] = datetime.now() - timedelta(days=days_to_keep)
    else:
        date_to_keep = None

    versions_to_delete = build_directories_deletion_list(valid_directories, num_to_keep, date_to_keep)
    changes_directories_to_delete = {f"{changes_prefix}/{version}/" for version in versions_to_delete}

    if not dry_run:
        delete_s3_change_log(changes_directories_to_delete, apt_repo)
    else:
        click.echo("[DRY RUN] Would delete change logs from repo:")
        for prefix in sorted(changes_directories_to_delete):
            click.echo(prefix)


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
    s3_client,
    organization: str,
    release_label: str,
    apt_repo: str,
    days_to_keep: int = None,
    num_to_keep: int = None,
    dry_run: bool = False,
) -> None:
    """Cleanup images according to a cleanup policy (days/number of packages to keep).
    :param s3_client: S3 client to use for S3 operations.
    :param organization: Name of the organization
    :param release_label: Release label of apt repo to target.
    :param apt_repo: S3 bucket where to publish release label.
    :param days_to_keep: (Optional) Age in days at which old images should be cleaned up.
    :param num_to_keep: (Optional) Quantity of old images to keep.
    :param dry_run: If true, only print the images that would be deleted without actually deleting them.
    """
    prefix = f"{release_label}/images"

    if days_to_keep is not None:
        date_to_keep: Optional[datetime] = datetime.now() - timedelta(days=days_to_keep)
    else:
        date_to_keep = None

    remote_images = list_s3_images(s3_client, apt_repo, prefix + f"/{organization}")
    to_delete = build_image_deletion_list(remote_images, num_to_keep, date_to_keep)
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

    # Wait until index file is unlocked and lock it while we update it
    wait_for_index(s3_client, apt_repo, index_key)

    try:
        image_index = read_index_file(s3_client, apt_repo, index_key)
        image_index = cleanup_index(image_index, keep_images)

        if not dry_run:
            click.echo("Updating index file")
            write_index_file(image_index, s3_client, apt_repo, index_key)
        else:
            click.echo("[DRY RUN] New version in index file:")
            for version in image_index.keys():
                click.echo(version)

    finally:
        unlock_index_file(s3_client, apt_repo, index_key)


def main():
    parser = argparse.ArgumentParser(description=cleanup_images.__doc__)
    parser.add_argument("--release-label", type=str, required=True)
    parser.add_argument("--apt-repo", type=str, required=True)
    parser.add_argument("--organization", type=str, required=True)
    parser.add_argument("--days-to-keep", type=int)
    parser.add_argument("--num-to-keep", type=int)
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    s3_client=boto3.client("s3")

    image_cleanup_result = cleanup_images(s3_client, **vars(args))
    change_logs_cleanup_result = cleanup_change_logs(s3_client, **vars(args))

    sys.exit(image_cleanup_result or change_logs_cleanup_result)

if __name__ == "__main__":
    main()
