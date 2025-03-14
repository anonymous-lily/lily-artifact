#!/usr/bin/env bash

set -e

if [[ $COMMON == "" ]]
then
    echo "INTERNAL ERROR: \$COMMON is undefined" 1>&2
    exit 1
fi
# Ignore `source` check here, it will be checked independently.
# shellcheck source=/dev/null
source "$COMMON"

# Function defined in `common.sh`.
generate_dictionary "lua.dict"

pushd ./original/
    # Function defined in `common.sh`.
    apply_patches

    CFLAGS="${COVERAGE_FLAGS[*]}"
    export AFL_LLVM_CMPLOG=1

    # Lua's Makefile hardcodes values for CC and CFLAGS.
    sed -i -E "s/^CC ?=.+$/CC=${CC//\//\\\/}/g" makefile
    sed -i -E "s/^CFLAGS ?=(.+)$/CFLAGS=$CFLAGS \1/g" makefile

    rm -rf ./*.o
    make -j"$(nproc)" liblua.a
    make -j"$(nproc)" lua
    $CC "${COVERAGE_FLAGS[@]}" -fsanitize=fuzzer -I. ./fuzz_lua.c -o ./fuzz-lua.cmplog ./liblua.a \
        -lm
popd
