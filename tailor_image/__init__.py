__version__ = '0.0.0'

import json
import sys
import subprocess


def find_package(package: str, path: str, env):
    path = run_command(['catkin_find', package, path, '--first-only'],
                       stdout=subprocess.PIPE,
                       env=env).stdout.decode().replace('\n', '')
    return path


def run_command(cmd, *args, **kwargs):
    print(' '.join(cmd), file=sys.stderr)
    return subprocess.run(cmd, check=True, *args, **kwargs)


def source_file(path):
    dump = '/usr/bin/python -c "import os, json; print json.dumps(dict(os.environ))"'
    pipe = subprocess.Popen(['/bin/bash', '-c', f'source {path} && {dump}'], stdout=subprocess.PIPE)
    return json.loads(pipe.stdout.read())
