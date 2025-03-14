#!/usr/bin/env bash


## Build a target program to fuzz with AFL++.
##
## The target is expected to exist in `$TARGETS_DIR`, and a build recipe (`build.sh`) is expected to
## be provided for it.

set -e


# `LOG_HEADER` is used in `$COMMON`.
# shellcheck disable=SC2034
LOG_HEADER="build-target"
COMMON="/root/artifact/tools/common.sh"
# Ignore `source` check here, it will be checked independently.
# shellcheck source=/dev/null
source "$COMMON"

if [[ $# -lt 2 ]] || [[ $# -gt 3 ]]
then
    error "usage: $0 <TARGET> <REF> [NAME]"
fi

target="$1"
ref="$2"
name="$3"
target_dir="$TARGETS_DIR/$target"
build_dir="$BUILDS_DIR/$target-$ref"
if [[ $name != "" ]]
then
    build_dir="$BUILDS_DIR/$name"
fi
original_ref="master"

mkdir -p "$BUILDS_DIR"

if [[ -d $build_dir ]] && [[ "${ALWAYS_BUILD:-0}" == "0" ]]
then
    info "Build dir $build_dir exists. Skipping build." \
        "(Set ALWAYS_BUILD=1 to disable this behavior.)"
    exit 0
fi
rm -rf "${build_dir:?}/"

info "Checking out $ref for $target..."
pushd . >/dev/null 2>&1
    cd "$target_dir/" || error "target directory '$target_dir' not found"

    # Sometimes, alternative versions (e.g., decompressed release tarballs) exist as separate
    # directories.
    if [[ -d "$ref" ]]
    then
        cp -r . "$build_dir/"
        # Make sure to not overwrite the "original" directory if it exists.
        if [[ -d "$build_dir/original" ]]
        then
            mv "$build_dir/original" "$build_dir/original.unused"
        fi
        mv "$build_dir/$ref" "$build_dir/original"
    else
        # If `$ref` was not a directory, then it's an *actual* Git ref we need to checkout.
        pushd . >/dev/null 2>&1
            cd ./original || error "target $target_dir missing directory 'original'"
            original_ref="$(git rev-parse HEAD)"
            git checkout --force "$ref" >/dev/null 2>&1 || error "failed to checkout $ref"
        popd >/dev/null 2>&1
        cp -r . "$build_dir/"
        # Reset the original repo for subsequent builds.
        pushd . >/dev/null 2>&1
            cd ./original
            git checkout --force "$original_ref" >/dev/null 2>&1 \
                || error "failed to reset checkout to original ref"
        popd >/dev/null 2>&1
    fi
popd >/dev/null 2>&1

info "Building $target ($ref) in $build_dir..."
pushd "$build_dir/" >/dev/null 2>&1
    # Remove everything Git-related to avoid any risk of messing up the original repo.
    rm -rf ./original/.git*
    # Build the target.
    export COMMON="$COMMON"
    bash ./build.sh >./build.log 2>&1 || error "build failed, see $build_dir/build.log"
    # Remove duplicate entries from the autodict (if any).
    if [[ -f ./autodict.dict ]]
    then
        cp ./autodict.dict ./autodict.dict.orig
        sort ./autodict.dict.orig | uniq > ./autodict.dict
        rm ./autodict.dict.orig
    fi
    # Build the final configuration file.
    sed -E "s/__TARGET_DIR__/${build_dir//\//\\/}/g" ./config.toml.template > ./config.toml
    rm ./config.toml.template
popd >/dev/null 2>&1

info "Build ready at $build_dir/, ROSA config at $build_dir/config.toml"
