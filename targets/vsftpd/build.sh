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
generate_dictionary "ftp.dict"

pushd ./original/
    # Function defined in `common.sh`.
    apply_patches

    CFLAGS="${COVERAGE_FLAGS[*]} -Wno-implicit-function-declaration"
    export AFL_LLVM_CMPLOG=1

    # vsFTPd hardcodes `CC` and `CFLAGS` for some reason...
    sed -i -E "s/^CC[[:space:]]*=.+$/CC = ${CC//$'/'/\\/}/g" Makefile
    sed -i -E "s/^CFLAGS[[:space:]]*=(.+)$/CFLAGS = $CFLAGS \1/g" Makefile

    # Force disable -Werror, as it causes problems with some versions.
    sed -i -E "s/-Werror//g" Makefile

    # Some older versions look for libraries in the wrong places (at least for modern OSes). In
    # order to ensure everything is always provided, we will simply hardcode the libraries in the
    # Makefile.
    #
    # We will also inject the coverage flags here (if there are any).
    sed -i -E "s/^LINK[[:space:]]*=(.+)$/LINK = $CFLAGS \1 -lpam -lpam_misc -lcap -lcrypt/g" \
        Makefile

    make -j"$(nproc)" vsftpd

    mv ./vsftpd ./vsftpd.cmplog
popd
