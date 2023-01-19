__version__ = '0.0.0'

import json
import random
import sys
import subprocess
import time

from datetime import datetime

import boto3
import botocore


def find_package(package: str, path: str, env):
    if package == '/tailor-image':
        path = f'{package}/environment/{path}'
    else:
        path = run_command(['catkin_find', package, path, '--first-only'],
                           stdout=subprocess.PIPE,
                           env=env).stdout.decode().replace('\n', '')
    return path


def run_command(cmd, check=True, *args, **kwargs):
    print(' '.join(cmd), file=sys.stderr)
    return subprocess.run(cmd, check=check, *args, **kwargs)


def source_file(path):
    dump = '/usr/bin/python3 -c "import os, json; print(json.dumps(dict(os.environ)))"'
    pipe = subprocess.Popen(['/bin/bash', '-c', f'source {path} && {dump}'], stdout=subprocess.PIPE)
    return json.loads(pipe.stdout.read())


def tag_file(client, bucket, key, tag_key, tag_value):
    tagset = {'TagSet': [{'Key': tag_key, 'Value': tag_value}]}
    client.put_object_tagging(Bucket=bucket,
                              Key=key,
                              Tagging=tagset)


def wait_for_index(client, bucket, key):
    # Wait until file is not locket to avoid race condition
    start_time = datetime.now()
    random.seed(start_time)
    timeout = 300 + random.random() * 300  # random timeout from 5 to 10 minutes
    while True:
        try:
            time.sleep(random.random()*5.0)
            tags = client.get_object_tagging(Bucket=bucket, Key=key)
            for tag in tags['TagSet']:
                print(f'Checking tag: {tag["Key"]}:{tag["Value"]}')
                if tag['Key'] == 'Lock' and tag['Value'] == 'False':
                    print("Locking file")
                    tag_file(client, bucket, key, 'Lock', 'True')
                    break
                elif tag['Key'] == 'Lock' and tag['Value'] == 'True':
                    # If timeout is reached, allow writing to index
                    time_delta = datetime.now() - start_time
                    if time_delta.total_seconds() >= timeout:
                        break
                    time.sleep(2.)
            else:
                continue
            break
        except botocore.exceptions.ClientError as error:
            if error.response['Error']['Code'] == 'NoSuchKey':
                # Index file doesn't exists, create an empty one
                print(f'{bucket}/{key} doesn\'t exist, creating...')
                client.put_object(Bucket=bucket,
                                  Key=key,
                                  Body='{}',
                                  Tagging='Lock=True')
                break


def invalidate_file_cloudfront(distribution_id, key):
    client = boto3.client('cloudfront')
    client.create_invalidation(DistributionId=distribution_id,
                               InvalidationBatch={
                                   'Paths': {
                                       'Quantity': 1,
                                       'Items': [
                                           f'/{key}',
                                       ]
                                   },
                                   'CallerReference':  datetime.now().strftime('%Y%m%d%H%M%S')
                               })


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
                raise Exception('Conflict at %s' % '.'.join(path + [str(key)]))
        else:
            dict_a[key] = dict_b[key]
    return dict_a
