#!/usr/bin/env bash

# `BENCHMARK_*` variables are used by `experiment-helpers/run.sh`.
# shellcheck disable=SC2034

# This is based on `safe-releases.toml`, with the addition of a backdoor on top of the "current"
# release.

ref_previous="v5.4.6"
ref_current="v5.4.7"
prefix="lua__simple-release"

BENCHMARK_TARGETS=(
    "harness.patch lua $ref_previous $prefix-$ref_previous"
    "backdoor.patch:harness.patch lua $ref_current $prefix-${ref_current}__backdoored"
    "backdoor.patch:harness.patch lua $ref_current $prefix-${ref_current}__backdoored__coverage"
    "ground-truth.patch:harness.patch lua $ref_current $prefix-${ref_current}__ground-truth"
)
BENCHMARK_NAME="$prefix-$ref_current-ubuntu"
BENCHMARK_PREVIOUS="$prefix-$ref_previous"
BENCHMARK_CURRENT="$prefix-${ref_current}__backdoored"
BENCHMARK_COVERAGE="$prefix-${ref_current}__backdoored__coverage"
BENCHMARK_GROUND_TRUTH="$prefix-${ref_current}__ground-truth"
