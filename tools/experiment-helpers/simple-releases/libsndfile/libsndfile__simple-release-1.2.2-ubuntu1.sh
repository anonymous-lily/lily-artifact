#!/usr/bin/env bash

# `BENCHMARK_*` variables are used by `experiment-helpers/run.sh`.
# shellcheck disable=SC2034

# This is based on `safe-releases.toml`, with the addition of a backdoor on top of the "current"
# release.

ref_previous="1.0.31"
ref_current="1.2.2"
prefix="libsndfile__simple-release"

BENCHMARK_TARGETS=(
    "harness-1998691e56.patch libsndfile $ref_previous $prefix-$ref_previous"
    "backdoor.patch:harness.patch libsndfile $ref_current $prefix-${ref_current}__backdoored"
    "backdoor.patch:harness.patch libsndfile $ref_current $prefix-${ref_current}__backdoored__coverage"
    "ground-truth.patch:harness.patch libsndfile $ref_current $prefix-${ref_current}__ground-truth"
)
BENCHMARK_NAME="$prefix-$ref_current-ubuntu1"
BENCHMARK_PREVIOUS="$prefix-$ref_previous"
BENCHMARK_CURRENT="$prefix-${ref_current}__backdoored"
BENCHMARK_COVERAGE="$prefix-${ref_current}__backdoored__coverage"
BENCHMARK_GROUND_TRUTH="$prefix-${ref_current}__ground-truth"
