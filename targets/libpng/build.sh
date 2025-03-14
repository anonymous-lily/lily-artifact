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
generate_dictionary "png.dict"

pushd ./original/
    # Function defined in `common.sh`.
    apply_patches

    export CC=$CC
    export CXX=$CXX
    export CFLAGS="${COVERAGE_FLAGS[*]}"
    export AFL_LLVM_CMPLOG=1

    sed -e "s/option STDIO/option STDIO disabled/" \
        -e "s/option WARNING /option WARNING disabled/" \
        -e "s/option WRITE enables WRITE_INT_FUNCTIONS/option WRITE disabled/" \
        ./scripts/pnglibconf.dfa \
        > ./scripts/pnglibconf.dfa.temp
    mv ./scripts/pnglibconf.dfa.temp ./scripts/pnglibconf.dfa

    autoreconf -f -i
    ./configure
    make -j"$(nproc)" clean
    make -j"$(nproc)" libpng16.la

    $CXX "${COVERAGE_FLAGS[@]}" -fsanitize=fuzzer -std=c++11 -I. \
        ./contrib/oss-fuzz/libpng_read_fuzzer.cc \
        -o ./libpng-read-fuzzer.cmplog ./.libs/libpng16.a -lz
popd
