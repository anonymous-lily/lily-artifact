#!/usr/bin/env bash

# `BENCHMARK_*` variables are used by `experiment-helpers/run.sh`.
# shellcheck disable=SC2034

commit_previous="c730aa26bd"
commit_current="046827a7e8"
prefix="php__simple-commit"

BENCHMARK_TARGETS=(
    "harness.patch php $commit_previous $prefix-$commit_previous"
    "harness.patch php $commit_current $prefix-$commit_current"
    "harness.patch php $commit_current $prefix-${commit_current}__coverage"
)
BENCHMARK_NAME="$prefix-$commit_current"
BENCHMARK_PREVIOUS="$prefix-$commit_previous"
BENCHMARK_CURRENT="$prefix-$commit_current"
BENCHMARK_COVERAGE="$prefix-${commit_current}__coverage"
BENCHMARK_GROUND_TRUTH="$prefix-$commit_current"
