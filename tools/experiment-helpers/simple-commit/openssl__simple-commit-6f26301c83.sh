#!/usr/bin/env bash

# `BENCHMARK_*` variables are used by `experiment-helpers/run.sh`.
# shellcheck disable=SC2034

commit="6f26301c83"
name="openssl__simple-commit-${commit}"

BENCHMARK_TARGETS=(
    "backdoor.patch:harness.patch openssl $commit ${name}__backdoored"
    "harness.patch openssl $commit ${name}__safe"
    "backdoor.patch:harness.patch openssl $commit ${name}__backdoored__coverage"
    "ground-truth.patch:harness.patch openssl $commit ${name}__ground-truth"
)
BENCHMARK_NAME="$name"
BENCHMARK_PREVIOUS="${name}__safe"
BENCHMARK_CURRENT="${name}__backdoored"
BENCHMARK_COVERAGE="${name}__backdoored__coverage"
BENCHMARK_GROUND_TRUTH="${name}__ground-truth"
