#!/usr/bin/env bash

## Startup script for the rosa-diff artifact.
set -e


# `LOG_HEADER` is used in `$COMMON`.
# shellcheck disable=SC2034
LOG_HEADER="startup"
COMMON="/root/artifact/tools/common.sh"
# Ignore `source` check here, it will be checked independently.
# shellcheck source=/dev/null
source "$COMMON"


# Older versions of Sudo (such as commit `387672583e`) do not like this line in the sudoers file,
# so we delete it.
chmod a+w /etc/sudoers
sed -i "/@includedir \/etc\/sudoers.d/d" /etc/sudoers
chmod a-w /etc/sudoers

# Generate the ROSA configs.
uv run --with "tomlkit==0.13.2" "$STARTUP_DIR"/generate-configs.py

# Generate the experiment helper files.
uv run --with "tomlkit==0.13.2" "$STARTUP_DIR"/generate-experiment-files.py \
    "$TARGETS_DIR"/*/safe-commits.toml \
    "$TARGETS_DIR"/*/safe-code-commits.toml \
    "$TARGETS_DIR"/*/safe-releases.toml
