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
generate_dictionary "sql.dict"

pushd ./original/
    # Function defined in `common.sh`.
    apply_patches

    CFLAGS_ARRAY=(
        "${COVERAGE_FLAGS[@]}"
        "-DSQLITE_MAX_LENGTH=128000000"
        "-DSQLITE_MAX_SQL_LENGTH=128000000"
        "-DSQLITE_MAX_MEMORY=25000000"
        "-DSQLITE_PRINTF_PRECISION_LIMIT=1048576"
        "-DSQLITE_DEBUG=1"
        "-DSQLITE_MAX_PAGE_COUNT=1638"
    )

    export CC="$CC"
    export CXX="$CXX"
    export CFLAGS="${CFLAGS_ARRAY[*]}"
    export CXXFLAGS="$CFLAGS"
    export LDFLAGS="${COVERAGE_FLAGS[*]}"
    export AFL_LLVM_CMPLOG=1
    export USE_AMALGAMATION=0

    mkdir bld/
    pushd ./bld/
        ../configure --disable-shared --enable-rtree --enable-debug
        make clean
        make -j"$(nproc)"
        make sqlite3.c

        $CC "${CFLAGS_ARRAY[@]}" -I. -c "../test/ossfuzz.c" -o "../test/ossfuzz.o"
        $CXX "${CFLAGS_ARRAY[@]}" -fsanitize=fuzzer "../test/ossfuzz.o" \
            "$(find .. -name "libsqlite3.a")" -o "../sqlite3-fuzz.cmplog" -pthread -ldl -lm
    popd
popd
