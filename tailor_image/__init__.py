__version__ = '0.0.0'

import sys
import subprocess

from catkin.find_in_workspaces import find_in_workspaces


def find_package(package_name: str, filename: str):
    package_path = find_in_workspaces(
        project=package_name,
        path=filename,
        first_match_only=True,
    )[0]

    return package_path


def run_command(cmd, *args, **kwargs):
    print(' '.join(cmd), file=sys.stderr)
    return subprocess.run(cmd, check=True, *args, **kwargs)
