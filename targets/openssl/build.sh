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
generate_dictionary "openssl-bignum.dict"

pushd ./original/
    # Function defined in `common.sh`.
    apply_patches

    export CC=$CC
    export CXX=$CXX
    export CFLAGS="${COVERAGE_FLAGS[*]}"
    export AFL_LLVM_CMPLOG=1

    # See https://stackoverflow.com/a/79147146/30291490.
    grep -alR "'File::Glob' => qw/glob/" | \
        xargs sed -i "s/'File::Glob' => qw\/glob\//'File::Glob' => qw\/:glob\//g" || true;

    # Remove obsolete `-fsanitize-coverage` flags.
    grep -alR -- "-fsanitize-coverage=edge,indirect-calls" | \
        xargs sed -i "s/-fsanitize-coverage=edge,indirect-calls//g" || true;

    ./config --debug enable-fuzz-libfuzzer -DPEDANTIC -DFUZZING_BUILD_MODE_UNSAFE_FOR_PRODUCTION \
        no-shared enable-tls1_3 enable-rc5 enable-md2 enable-ssl3 enable-ssl3-method \
        enable-nextprotoneg enable-weak-ssl-ciphers --with-fuzzer-lib="$LIBAFL_DRIVER" \
        -fno-sanitize=alignment
    # In some versions, the CFLAGS do not "take" in the Makefile for some reason (`./config`
    # probably overwrites them with default ones). To make sure they're present, set them manually
    # here (in the worst case, they'll just be duplicated).
    sed -i -E "s/CFLAGS=(.+)/CFLAGS=\1 $CFLAGS/g" ./Makefile

    make -j"$(nproc)" LDCMD="$CXX $CXXFLAGS ${COVERAGE_FLAGS[*]}"

    # In some cases, the `test/` directory is *huge*. We don't seem to need it, so it's best to
    # remove it.
    rm -rf "./test/"

    mv ./fuzz/bignum ./fuzz/bignum.cmplog
popd
