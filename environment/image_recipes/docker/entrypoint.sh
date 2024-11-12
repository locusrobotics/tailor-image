#!/bin/bash

source /etc/locus/setup.bash

if [[ -v ROS1_WORKSPACE ]]; then
  source $ROS1_WORKSPACE
fi

exec "$@"
