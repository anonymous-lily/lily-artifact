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
generate_dictionary "wav.dict"

pushd ./original/
    # Function defined in `common.sh`.
    apply_patches

    export CC="$CC"
    export CXX="$CXX"
    export CFLAGS="${COVERAGE_FLAGS[*]}"
    export CXXFLAGS="$CFLAGS"
    export LD="lld-21"
    export LIB_FUZZING_ENGINE="-fsanitize=fuzzer"
    export AFL_LLVM_CMPLOG=1

    autoreconf -vif
    ./configure --disable-shared --enable-ossfuzzers
    make -j"$(nproc)" V=1
    mv ./ossfuzz/sndfile_fuzzer ./ossfuzz/sndfile-fuzzer.cmplog
popd
