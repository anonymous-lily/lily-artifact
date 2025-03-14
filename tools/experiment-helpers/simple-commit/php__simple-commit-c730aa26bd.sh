#!/usr/bin/env bash

# `BENCHMARK_*` variables are used by `experiment-helpers/run.sh`.
# shellcheck disable=SC2034

commit_previous="92aeda524b"
commit_current="c730aa26bd"
prefix="php__simple-commit"

BENCHMARK_TARGETS=(
    "harness.patch php $commit_previous $prefix-$commit_previous"
    "harness.patch php $commit_current $prefix-$commit_current"
    "harness.patch php $commit_current $prefix-${commit_current}__coverage"
    "ground-truth-$commit_current.patch:harness.patch php $commit_current $prefix-${commit_current}__ground-truth"
)
BENCHMARK_NAME="$prefix-$commit_current"
BENCHMARK_PREVIOUS="$prefix-$commit_previous"
BENCHMARK_CURRENT="$prefix-$commit_current"
BENCHMARK_COVERAGE="$prefix-${commit_current}__coverage"
BENCHMARK_GROUND_TRUTH="$prefix-${commit_current}__ground-truth"
