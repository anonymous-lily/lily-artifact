#!/usr/bin/env bash

## Run a Docker container with the <TODO name & conf> artifact image.
## The name of the Docker image is specified by the IMAGE file.
## The version of the Docker image is specified by the VERSION file.


set -e

host_shared_dir="$1"
container_shared_dir="/root/experiments"
name="$USER-$(date +%d.%m.%y-%Hh%Mm%Ss)__rosa-diff-artifact"
extra_args=()
tmpfs_size="${TMPFS_SIZE:-50g}"

if [[ $host_shared_dir != "" ]]
then
    extra_args=("-v" "$host_shared_dir:$container_shared_dir")
    echo "Using $host_shared_dir as a shared volume (mapped to $container_shared_dir)"
fi

if [[ $CPUS_BOUND != "" ]]
then
    extra_args=("${extra_args[@]}" "--cpuset-cpus=$CPUS_BOUND")
    name="${name}__${CPUS_BOUND//,/-}"
    echo "Binding to CPUs $CPUS_BOUND"
fi

if [[ $MEMS_BOUND != "" ]]
then
    extra_args=("${extra_args[@]}" "--cpuset-mems=$MEMS_BOUND")
    name="${name}__${MEMS_BOUND//,/-}"
    echo "Binding to MEMs $MEMS_BOUND"
fi

echo "Mounting $tmpfs_size tmpfs at /root/scratch"
echo "Starting container named '$name', version $(cat VERSION)"
sleep 2
docker run -ti --rm --name "$name" --security-opt seccomp=unconfined \
    --tmpfs /root/scratch:size="$tmpfs_size" "${extra_args[@]}" "$(cat IMAGE):$(cat VERSION)"
