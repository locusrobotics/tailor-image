#!/usr/bin/env python3
"""
List and optionally terminate EC2 instances that have a security group whose
name contains the word 'packer', and have been running for more than a
specified number of days. Optionally also delete their 'packer' security
groups and key pairs after termination.

Usage:
    python ec2_list_terminate_packer.py [--days DAYS] [--terminate] [--dry-run]
                                        [--delete-related] [--yes]
                                        [--profile PROFILE] [--region REGION]

Examples:
    # List instances running for more than 1 day
    python ec2_list_terminate_packer.py --days 1

    # Interactively select instances to terminate
    python ec2_list_terminate_packer.py --days 1 --terminate

    # Terminate all matching instances without prompting (dry-run first)
    python ec2_list_terminate_packer.py --days 1 --terminate --dry-run

    # Also delete related 'packer' security groups/key pairs after terminating
    python ec2_list_terminate_packer.py --days 1 --terminate --delete-related

    # Non-interactive: terminate all matches and delete related resources
    # without prompting (e.g. for use in CI)
    python ec2_list_terminate_packer.py --days 1 --terminate --delete-related --yes
"""

import argparse
import sys
from datetime import datetime, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError


def non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0 (use 0 to select all uptimes): {value}")
    return parsed


def parse_args():
    parser = argparse.ArgumentParser(
        description="List/terminate long-running EC2 instances with a 'packer' security group."
    )
    parser.add_argument(
        "--days",
        type=non_negative_float,
        default=1.0,
        help="Minimum uptime in days to include an instance (default: 1; use 0 to select all uptimes)",
    )
    parser.add_argument(
        "--terminate",
        action="store_true",
        help="Prompt to terminate matching instances after listing them",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Show what would be terminated without actually doing it",
    )
    parser.add_argument(
        "--delete-related",
        action="store_true",
        dest="delete_related",
        help=(
            "After terminating instances, also delete their 'packer' security "
            "groups and key pairs (only ones with 'packer' in the name). "
            "Prompts for confirmation before deleting."
        ),
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        dest="assume_yes",
        help=(
            "Skip interactive prompts: terminate all matching instances "
            "(and delete related resources, if --delete-related is set) "
            "without asking for confirmation. Useful for non-interactive/CI runs."
        ),
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="AWS credentials profile to use",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="AWS region (defaults to profile/env default)",
    )
    return parser.parse_args()


def get_instance_name(instance) -> str:
    for tag in instance.get("Tags", []):
        if tag["Key"] == "Name":
            return tag["Value"]
    return "<no name>"


def get_security_group_names(instance) -> str:
    return ", ".join(sg["GroupName"] for sg in instance.get("SecurityGroups", []))


def format_uptime(launch_time: datetime) -> str:
    delta = datetime.now(timezone.utc) - launch_time
    total_hours = int(delta.total_seconds() // 3600)
    days, hours = divmod(total_hours, 24)
    return f"{days}d {hours}h"


def find_packer_instances(ec2_client, min_days: float) -> list:
    """Return running instances with a 'packer' security group and uptime > min_days."""
    paginator = ec2_client.get_paginator("describe_instances")
    pages = paginator.paginate(
        Filters=[
            {"Name": "instance-state-name", "Values": ["running"]},
        ]
    )

    matches = []
    now = datetime.now(timezone.utc)
    for page in pages:
        for reservation in page["Reservations"]:
            for inst in reservation["Instances"]:
                # Match client-side since the EC2 group-name filter is
                # case-sensitive and would miss groups like "Packer Builder".
                if not any(
                    "packer" in sg.get("GroupName", "").lower()
                    for sg in inst.get("SecurityGroups", [])
                ):
                    continue
                launch_time = inst["LaunchTime"]
                uptime_days = (now - launch_time).total_seconds() / 86400
                if uptime_days >= min_days:
                    matches.append(inst)

    matches.sort(key=lambda i: i["LaunchTime"])
    return matches


def print_table(instances: list) -> None:
    header = (
        f"{'#':<4} {'Instance ID':<21} {'Name':<20} {'Type':<15} {'Security Groups':<30} "
        f"{'Uptime':<12} {'Launch Time (UTC)'}"
    )
    print(header)
    print("-" * len(header))
    for idx, inst in enumerate(instances, start=1):
        name = get_instance_name(inst)
        sgs = get_security_group_names(inst)
        uptime = format_uptime(inst["LaunchTime"])
        launch = inst["LaunchTime"].strftime("%Y-%m-%d %H:%M")
        print(
            f"{idx:<4} {inst['InstanceId']:<21} {name:<20} {inst['InstanceType']:<15} {sgs:<30} "
            f"{uptime:<12} {launch}"
        )


def prompt_selection(instances: list) -> list:
    """Ask user which instances to terminate; return selected subset."""
    print(
        "\nEnter instance numbers to terminate (comma-separated), "
        "'all' to terminate all, or 'none' to cancel:"
    )
    choice = input("> ").strip().lower()

    if choice in ("none", ""):
        return []
    if choice == "all":
        return instances

    selected = []
    for part in choice.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            idx = int(part)
            if 1 <= idx <= len(instances):
                selected.append(instances[idx - 1])
            else:
                print(f"  Warning: index {idx} out of range, skipping.")
        except ValueError:
            print(f"  Warning: '{part}' is not a valid number, skipping.")
    return selected


def terminate_instances(ec2_client, instances: list, dry_run: bool) -> None:
    ids = [i["InstanceId"] for i in instances]
    if dry_run:
        print(f"\n[DRY RUN] Would terminate: {', '.join(ids)}")
        return

    print(f"\nTerminating {len(ids)} instance(s)...")
    try:
        response = ec2_client.terminate_instances(InstanceIds=ids)
        for change in response["TerminatingInstances"]:
            prev = change["PreviousState"]["Name"]
            curr = change["CurrentState"]["Name"]
            print(f"  {change['InstanceId']}: {prev} → {curr}")
    except ClientError as exc:
        print(f"Error terminating instances: {exc}", file=sys.stderr)
        sys.exit(1)


def collect_packer_related_resources(instances: list) -> tuple:
    """Return (security_group_ids, key_names) with 'packer' in their name."""
    sg_ids = {}
    key_names = set()
    for inst in instances:
        for sg in inst.get("SecurityGroups", []):
            if "packer" in sg.get("GroupName", "").lower():
                sg_ids[sg["GroupId"]] = sg["GroupName"]
        key_name = inst.get("KeyName")
        if key_name and "packer" in key_name.lower():
            key_names.add(key_name)
    return sg_ids, key_names


def delete_related_resources(ec2_client, instances: list, dry_run: bool, assume_yes: bool = False) -> bool:
    """Delete 'packer' security groups and key pairs used by the given instances.

    Waits for the instances to fully terminate first, since security groups
    can't be deleted while still attached to a (even shutting-down) instance.

    :return: True if termination was confirmed and all related resources were
        deleted successfully (or there was nothing to do); False otherwise.
    """
    sg_ids, key_names = collect_packer_related_resources(instances)
    if not sg_ids and not key_names:
        print("\nNo 'packer' security groups or key pairs found to delete.")
        return True

    print("\nThe following related resources will be deleted:")
    for gid, gname in sg_ids.items():
        print(f"  Security group: {gname} ({gid})")
    for key_name in key_names:
        print(f"  Key pair: {key_name}")

    if dry_run:
        print("[DRY RUN] Skipping deletion.")
        return True

    if not assume_yes:
        confirm = input("\nProceed with deleting these resources? [y/N]: ").strip().lower()
        if confirm not in ("y", "yes"):
            print("Skipped deleting related resources.")
            return True

    print("\nWaiting for instances to fully terminate before cleanup...")
    try:
        waiter = ec2_client.get_waiter("instance_terminated")
        waiter.wait(InstanceIds=[i["InstanceId"] for i in instances])
    except (ClientError, BotoCoreError) as exc:
        print(f"Warning: error waiting for termination: {exc}", file=sys.stderr)
        print("Skipping deletion of related resources since termination could not be confirmed.", file=sys.stderr)
        return False

    success = True

    for gid, gname in sg_ids.items():
        try:
            ec2_client.delete_security_group(GroupId=gid)
            print(f"  Deleted security group {gname} ({gid})")
        except ClientError as exc:
            print(f"  Warning: could not delete security group {gname} ({gid}): {exc}", file=sys.stderr)
            success = False

    for key_name in key_names:
        try:
            ec2_client.delete_key_pair(KeyName=key_name)
            print(f"  Deleted key pair {key_name}")
        except ClientError as exc:
            print(f"  Warning: could not delete key pair {key_name}: {exc}", file=sys.stderr)
            success = False

    return success


def main():
    args = parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    ec2 = session.client("ec2")

    try:
        instances = find_packer_instances(ec2, args.days)
    except NoCredentialsError:
        print(
            "No AWS credentials found. Configure them via env vars, ~/.aws/credentials, or --profile.",
            file=sys.stderr,
        )
        sys.exit(1)
    except ClientError as exc:
        print(f"AWS error: {exc}", file=sys.stderr)
        sys.exit(1)

    if not instances:
        print(f"No running instances with a 'packer' security group and uptime ≥ {args.days} day(s) found.")
        return

    print(
        f"\nFound {len(instances)} running instance(s) with a 'packer' security group "
        f"and uptime ≥ {args.days} day(s):\n"
    )
    print_table(instances)

    if not args.terminate:
        return

    if args.assume_yes:
        to_terminate = instances
    else:
        to_terminate = prompt_selection(instances)
    if not to_terminate:
        print("No instances selected. Exiting.")
        return

    terminate_instances(ec2, to_terminate, args.dry_run)

    if args.delete_related:
        if not delete_related_resources(ec2, to_terminate, args.dry_run, args.assume_yes):
            sys.exit(1)


if __name__ == "__main__":
    main()
