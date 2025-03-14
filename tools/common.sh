#!/usr/bin/env bash
# shellcheck disable=SC2034

CC="/root/rosa/fuzzers/aflpp/aflpp/afl-cc"
CXX="/root/rosa/fuzzers/aflpp/aflpp/afl-c++"
LIBAFL_DRIVER="/root/rosa/fuzzers/aflpp/aflpp/libAFLDriver.a"

if [[ ${TRACK_COVERAGE:-0} -eq 1 ]]
then
    COVERAGE_FLAGS=("-fprofile-instr-generate" "-fcoverage-mapping")
else
    COVERAGE_FLAGS=()
fi

DICTIONARIES_DIR="/root/artifact/dictionaries"
EXPERIMENTS_DIR="/root/experiments"
TARGETS_DIR="/root/artifact/targets"
TOOLS_DIR="/root/artifact/tools"
HELPERS_DIR="$TOOLS_DIR/experiment-helpers"
STARTUP_DIR="$TOOLS_DIR/startup"
EVALUATION_DIR="$TOOLS_DIR/evaluation"
BUILDS_DIR="$EXPERIMENTS_DIR/builds"


header="${LOG_HEADER:-*}"

error() {
    echo -e "\e[1m[$header]\e[0m  \e[31mERROR: $*\e[0m" 1>&2
    exit 1
}

info() {
    echo -e "\e[1m[$header]\e[0m  \e[32m$*\e[0m" 1>&2
}

apply_patches() {
    patches="${PATCHES:-}"
    patches=${patches//:/ }

    for patch in $patches
    do
        if [[ $patch != "" ]]
        then
            echo "Patching with $patch ..."
            patch -p1 < "$patch"
        fi
    done
}

generate_dictionary() {
    if [[ $# -ne 1 ]]
    then
        error "INTERNAL ERROR: usage: generate_dictionary <DICT FILE>"
    fi

    dict_file=$1

    if [[ -f $DICTIONARIES_DIR/$dict_file ]]
    then
        cp "$DICTIONARIES_DIR/$dict_file" .
    else
        touch "$dict_file"
    fi

    export AFL_LLVM_DICT2FILE="$PWD/autodict.dict"
    export AFL_LLVM_DICT2FILE_NO_MAIN=1
}
