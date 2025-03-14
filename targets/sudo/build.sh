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
generate_dictionary "sudo.dict"

pushd ./original/
    # Function defined in `common.sh`.
    apply_patches

    # For some reason, Sudo seems to have linking issues with AFL++ and LLVM 21. I'm not sure why,
    # but it seems to be using GNU ld to link instead of the appropriate LLVM linker. Also,
    # `./configure` seems to ignore/mishandle the `LD` env var, so there seems to be no good way to
    # "correct" it (if we pass `LD=lld` then we get uninstrumented binaries).
    #
    # Experimentally, the only way I have managed to get it to work is with LTO mode, so we will use
    # that instead on this target. Compile times are still short for Sudo, so using LTO mode would
    # not affect the CI pipeline times.
    export CC=/root/rosa/fuzzers/aflpp/aflpp/afl-clang-lto
    export CXX=/root/rosa/fuzzers/aflpp/aflpp/afl-clang-lto++
    export LD=/root/rosa/fuzzers/aflpp/aflpp/afl-clang-lto
    export AR=llvm-ar-21
    export RANLIB=llvm-ranlib-21
    export AS=llvm-as-21
    # We need to define `HAVE___FUNC__` because it steps over some problematic macros that tend to
    # lead to build issues in older versions. Similarly, sometimes defining `AUTH_STANDALONE`
    # resolves build issues.
    export CFLAGS="${COVERAGE_FLAGS[*]} -DHAVE___FUNC__ -DAUTH_STANDALONE"
    export LDFLAGS="$CFLAGS"
    export AFL_LLVM_CMPLOG=1

    ./configure --prefix="$PWD/build" --without-pam --disable-shared

    # As part of the pre-install, Sudo tries to check if the syntax of `/etc/sudoers` is valid.
    # However, since that syntax has evolved with time, older versions will fail. Manually disable
    # this check here.
    #
    # Shellcheck: we are not trying to expand expressions here.
    # shellcheck disable=SC2016
    sed -i '/.\/visudo -c -f $(DESTDIR)$(sudoersdir)\/sudoers;/d' ./plugins/sudoers/Makefile

    make -j"$(nproc)"
    make install
    mv ./build/bin/sudo ./build/bin/sudo.cmplog
popd
