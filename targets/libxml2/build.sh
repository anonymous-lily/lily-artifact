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
generate_dictionary "xml.dict"

pushd ./original/
    # Function defined in `common.sh`.
    apply_patches

    export CC="$CC"
    export CFLAGS="${COVERAGE_FLAGS[*]} -DFUZZING_BUILD_MODE_UNSAFE_FOR_PRODUCTION"
    export CXX="$CXX"
    export CXXFLAGS="$CFLAGS"
    export AFL_LLVM_CMPLOG=1

    ./autogen.sh --with-http=no --with-python=no --with-lzma=yes --with-threads=no --disable-shared

    make clean
    make -j"$(nproc)" all

    # LibXML2 changed fuzzer harnesses at some point, so we need to be able to support both.
    # Note that the "old" fuzzing harness (`libxml2_reader_for_file_fuzzer.cc`) is taken from MAGMA,
    # and is not present in the LibXML2 repository (see `patches/magma-harness.patch`).
    if [[ -f fuzz/reader.c ]]
    then
        make -C fuzz fuzz.o reader.o

        $CXX "${COVERAGE_FLAGS[@]}" -DFUZZING_BUILD_MODE_UNSAFE_FOR_PRODUCTION \
            -fsanitize=fuzzer fuzz/reader.o fuzz/fuzz.o \
            -o fuzz/reader.cmplog .libs/libxml2.a -Wl,-Bstatic -lz -llzma -Wl,-Bdynamic
    else
        $CXX "${COVERAGE_FLAGS[@]}" -DFUZZING_BUILD_MODE_UNSAFE_FOR_PRODUCTION \
            -fsanitize=fuzzer -std=c++11 -Iinclude/ -Ifuzz/ \
            fuzz/libxml2_xml_reader_for_file_fuzzer.cc -o fuzz/reader.cmplog \
            .libs/libxml2.a -Wl,-Bstatic -lz -llzma -Wl,-Bdynamic
    fi
popd
