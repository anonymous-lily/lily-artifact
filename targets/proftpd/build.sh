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

    export CC="$CC"
    # Some older commits have inconsistencies when activating/deactivating IPV6 support. Defining
    # `PR_USE_IPV6` seems to solve that.
    export CFLAGS="${COVERAGE_FLAGS[*]}"
    export LDFLAGS="$CFLAGS"
    export AFL_LLVM_CMPLOG=1
    ./configure --disable-shared --enable-static --enable-devel=nofork:nodaemon --disable-ipv6
    make -j"$(nproc)"

    mv ./proftpd ./proftpd.cmplog
popd
