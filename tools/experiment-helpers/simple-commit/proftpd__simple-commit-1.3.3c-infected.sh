#!/usr/bin/env bash

# `BENCHMARK_*` variables are used by `experiment-helpers/run.sh`.
# shellcheck disable=SC2034

commit_previous="1.3.3c"
commit_current="1.3.3c-infected"
prefix="proftpd__simple-commit"

BENCHMARK_TARGETS=(
    "harness-1.3.3c.patch proftpd $commit_previous $prefix-$commit_previous"
    "harness-1.3.3c.patch proftpd $commit_current $prefix-$commit_current"
    "harness-1.3.3c.patch proftpd $commit_current $prefix-${commit_current}__coverage"
    "ground-truth-1.3.3c.patch:harness-1.3.3c.patch proftpd $commit_current $prefix-${commit_current}__ground-truth"
)
BENCHMARK_NAME="$prefix-$commit_current"
BENCHMARK_PREVIOUS="$prefix-$commit_previous"
BENCHMARK_CURRENT="$prefix-$commit_current"
BENCHMARK_COVERAGE="$prefix-${commit_current}__coverage"
BENCHMARK_GROUND_TRUTH="$prefix-${commit_current}__ground-truth"
