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
generate_dictionary "tiff.dict"

pushd ./original/
    # Function defined in `common.sh`.
    apply_patches

    export CC=$CC
    export CXX=$CXX
    export CFLAGS="${COVERAGE_FLAGS[*]} -Wno-implicit-function-declaration"
    export AFL_LLVM_CMPLOG=1

    cmake . -DBUILD_SHARED_LIBS=off
    make -j"$(nproc)"

    $CXX "${COVERAGE_FLAGS[@]}" -Wno-implicit-function-declaration -fsanitize=fuzzer -std=c++11 \
        -I./libtiff ./contrib/oss-fuzz/tiff_read_rgba_fuzzer.cc -o tiff-read-rgba-fuzzer.cmplog \
        "$(find . -name "libtiffxx.a")" "$(find . -name "libtiff.a")" -lz -lzstd -ljpeg -ljbig \
        -llzma -ldeflate -lwebp -lLerc
popd
