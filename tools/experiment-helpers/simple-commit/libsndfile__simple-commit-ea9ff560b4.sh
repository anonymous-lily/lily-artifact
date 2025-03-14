#!/usr/bin/env bash

# `BENCHMARK_*` variables are used by `experiment-helpers/run.sh`.
# shellcheck disable=SC2034

commit="ea9ff560b4"
name="libsndfile__simple-commit-${commit}"

BENCHMARK_TARGETS=(
    "backdoor.patch:harness.patch libsndfile $commit ${name}__backdoored"
    "harness.patch libsndfile $commit ${name}__safe"
    "backdoor.patch:harness.patch libsndfile $commit ${name}__backdoored__coverage"
    "ground-truth.patch:harness.patch libsndfile $commit ${name}__ground-truth"
)
BENCHMARK_NAME="$name"
BENCHMARK_PREVIOUS="${name}__safe"
BENCHMARK_CURRENT="${name}__backdoored"
BENCHMARK_COVERAGE="${name}__backdoored__coverage"
BENCHMARK_GROUND_TRUTH="${name}__ground-truth"
