#!/usr/bin/env bash

# `BENCHMARK_*` variables are used by `experiment-helpers/run.sh`.
# shellcheck disable=SC2034

# This is based on `safe-releases.toml`, with the addition of a backdoor on top of the "current"
# release.

ref_previous="v1.3.7c"
ref_current="v1.3.8b"
prefix="proftpd__simple-release"

BENCHMARK_TARGETS=(
    "harness-e2d1c480f2.patch proftpd $ref_previous $prefix-$ref_previous"
    "backdoor-v1.3.8b.patch:harness-e2d1c480f2.patch proftpd $ref_current $prefix-${ref_current}__backdoored"
    "backdoor-v1.3.8b.patch:harness-e2d1c480f2.patch proftpd $ref_current $prefix-${ref_current}__backdoored__coverage"
    "ground-truth-v1.3.8b.patch:harness-e2d1c480f2.patch proftpd $ref_current $prefix-${ref_current}__ground-truth"
)
BENCHMARK_NAME="$prefix-$ref_current"
BENCHMARK_PREVIOUS="$prefix-$ref_previous"
BENCHMARK_CURRENT="$prefix-${ref_current}__backdoored"
BENCHMARK_COVERAGE="$prefix-${ref_current}__backdoored__coverage"
BENCHMARK_GROUND_TRUTH="$prefix-${ref_current}__ground-truth"
