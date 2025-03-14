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
generate_dictionary "php-unserialize.dict"

pushd ./original/
    # Function defined in `common.sh`.
    apply_patches

    export CC="$CC"
    export CFLAGS="${COVERAGE_FLAGS[*]} -Wno-implicit-function-declaration"
    export AFL_LLVM_CMPLOG=1

    # Some versions of PHP activate UBSAN for the fuzzer harnesses (`-fsanitize=undefined`). This in
    # turn can produce `ud1` instructions (https://www.felixcloutier.com/x86/ud), which obviously
    # lead to crashes (also see https://github.com/AFLplusplus/AFLplusplus/issues/2291). We manually
    # remove any activation of UBSAN, as it is not needed at all by Rosa/Lily.
    grep -alR -- "-fsanitize=undefined" | xargs sed -i -E 's/-fsanitize=undefined//g'

    # In older versions of PHP, they restrict the versions of Bison that can be used. The default
    # version which comes with Ubuntu 24.04, version 3.8.2, is good enough to build, so we overwrite
    # the accepted versions list.
    if [[ -f ./Zend/acinclude.m4 ]]
    then
        sed -i -E 's/bison_version_list="(.+)"/bison_version_list="\1 3.8.2"/g' ./Zend/acinclude.m4
    fi
    ./buildconf --force
    ./configure --disable-all --enable-fuzzer --without-pcre-jit --disable-phpdbg --disable-cgi \
        --with-pic

    # Sometimes, the configure script doesn't work properly, and activates or deactivates some
    # options when it shouldn't. In order to avoid patching this manually for every commit, we will
    # make sure that the right `#define`s have been applied here, before running `make`.
    sed -i -E '/^#define HAVE_OLD_READDIR_R 1/d' main/php_config.h

    export CFLAGS="${COVERAGE_FLAGS[*]} -fsanitize=fuzzer"
    make -j"$(nproc)"

    mv ./sapi/fuzzer/php-fuzz-unserialize ./sapi/fuzzer/php-fuzz-unserialize.cmplog
popd
