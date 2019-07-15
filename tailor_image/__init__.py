__version__ = '0.0.0'

import sys
import subprocess


def run_command(cmd, *args, **kwargs):
    print(' '.join(cmd), file=sys.stderr)
    return subprocess.run(cmd, check=True, *args, **kwargs)
