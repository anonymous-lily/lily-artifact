#!/usr/bin/env bash

## Run a simple experiment as a sanity check.

set -e


OUTPUT_DIR="/root/evaluation/sanity-check"
EXPERIMENT_DIR="/root/experiments/vsftpd__simple-commit-2.3.4-infected__$(date --iso-8601)"

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

rm -rf "${EXPERIMENT_DIR:?}/"

RUNS=1 SECONDS_PER_RUN=10 "/root/artifact/tools/experiment-helpers/run.sh" \
    "/root/artifact/tools/experiment-helpers/simple-commit/vsftpd__simple-commit-2.3.4-infected.sh"

"/root/artifact/tools/analysis/extract-results.py" \
    "$EXPERIMENT_DIR.zip" > "$OUTPUT_DIR/results.json"

# TODO: reproduce tables from paper in PDF form
