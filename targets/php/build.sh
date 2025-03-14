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
generate_dictionary "http.dict"

pushd ./original/
    # Function defined in `common.sh`.
    apply_patches

    export CC="$CC"
    export CFLAGS="${COVERAGE_FLAGS[*]} -Wno-implicit-function-declaration"
    export AFL_LLVM_CMPLOG=1

    # In older versions of PHP, they restrict the versions of Bison that can be used. The default
    # version which comes with Ubuntu 24.04, version 3.8.2, is good enough to build, so we overwrite
    # the accepted versions list.
    if [[ -f ./Zend/acinclude.m4 ]]
    then
        sed -i -E 's/bison_version_list="(.+)"/bison_version_list="\1 3.8.2"/g' ./Zend/acinclude.m4
    fi
    ./buildconf --force
    ./configure --disable-all --disable-phpdbg --disable-cgi --with-zlib

    # Sometimes, the configure script doesn't work properly, and activates or deactivates some
    # options when it shouldn't. In order to avoid patching this manually for every commit, we will
    # make sure that the right `#define`s have been applied here, before running `make`.
    sed -i -E '/^#define HAVE_OLD_READDIR_R 1/d' main/php_config.h

    make -j"$(nproc)"

    mv ./sapi/cli/php ./sapi/cli/php.cmplog
popd
