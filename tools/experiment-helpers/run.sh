#!/usr/bin/env bash

set -e


RUNS="${RUNS:-20}"
SECONDS_PER_RUN="${SECONDS_PER_RUN:-600}"

# `LOG_HEADER` is used in `$COMMON`.
# shellcheck disable=SC2034
LOG_HEADER="experiment-helper"
COMMON="/root/artifact/tools/common.sh"
# Ignore `source` check here, it will be checked independently.
# shellcheck source=/dev/null
source "$COMMON"


if [[ $# -ne 1 ]]
then
    error "usage: $0 <EXPERIMENT_FILE> \n" \
        "      (see $HELPERS_DIR) for a list of experiment files"
fi

experiment_file="$1"
# Ignore `source` check here, it will be checked independently.
# shellcheck source=/dev/null
source "$experiment_file"

if [[ -z $BENCHMARK_TARGETS ]]
then
    error "INTERNAL: missing BENCHMARK_TARGETS definition in '$experiment_file'."
fi
if [[ -z $BENCHMARK_NAME ]]
then
    error "INTERNAL: missing BENCHMARK_NAME definition in '$experiment_file'."
fi
if [[ -z $BENCHMARK_PREVIOUS ]]
then
    error "INTERNAL: missing BENCHMARK_PREVIOUS definition in '$experiment_file'."
fi
if [[ -z $BENCHMARK_CURRENT ]]
then
    error "INTERNAL: missing BENCHMARK_CURRENT definition in '$experiment_file'."
fi
if [[ -z $BENCHMARK_COVERAGE ]]
then
    error "INTERNAL: missing BENCHMARK_COVERAGE definition in '$experiment_file'."
if [[ -z $BENCHMARK_CURRENT ]]
then
    error "INTERNAL: missing BENCHMARK_CURRENT definition in '$experiment_file'."
fi
fi
if [[ -z $BENCHMARK_GROUND_TRUTH ]]
then
    error "INTERNAL: missing BENCHMARK_GROUND_TRUTH definition in '$experiment_file'."
fi

experiment_dir="$EXPERIMENTS_DIR/${BENCHMARK_NAME}__$(date --iso-8601)"

if [[ ! -d "$EXPERIMENTS_DIR" ]]
then
    error "'$EXPERIMENTS_DIR' does not exist." \
        "It should be mapped to a directory on the host machine to avoid running out of disk space."
fi

if [[ -d "$experiment_dir" ]]
then
    error "'$experiment_dir' already exists. Stopping to avoid overwriting precious data."
fi

mkdir "$experiment_dir"
# Save the version of both containers in the experiment directory.
echo -e "rosa: $(cat "/root/rosa/VERSION")\nartifact: $(cat "/root/artifact/VERSION")" \
    > "$experiment_dir/VERSION"

# Build the targets.
for target_info in "${BENCHMARK_TARGETS[@]}"
do
    IFS=" " read -r patches target commit name <<< "$target_info"

    # Append the right directories to the patch files.
    IFS=":" read -ra patches <<< "$patches"
    full_patches=""
    for patch in "${patches[@]}"
    do
        full_patches="$full_patches:$TARGETS_DIR/$target/patches/$patch"
    done

    if [[ $name == "$BENCHMARK_COVERAGE" ]]
    then
        export TRACK_COVERAGE=1
    else
        export TRACK_COVERAGE=0
    fi

    PATCHES="$full_patches" "$EVALUATION_DIR"/build-target.sh "$target" "$commit" "$name"
done

# Produce the full diff between the two commits.
info "Computing diff between versions..."
git diff --no-index --relative \
    "$BUILDS_DIR/$BENCHMARK_PREVIOUS/original" "$BUILDS_DIR/$BENCHMARK_COVERAGE/original" \
    > "$BUILDS_DIR/$BENCHMARK_COVERAGE/full-diff.patch" || true
info "Full diff stored in '$BUILDS_DIR/$BENCHMARK_COVERAGE/full-diff.patch'."

# Run and evaluate the benchmark.
raw_data_dir="$experiment_dir/raw-data"
results_dir="$experiment_dir/results"
mkdir -p "$raw_data_dir" "$results_dir"

info "Running experiment..."

"$EVALUATION_DIR/run-benchmark.py" --verbose \
    "$BUILDS_DIR/$BENCHMARK_CURRENT" "$BUILDS_DIR/$BENCHMARK_PREVIOUS" \
    "$BUILDS_DIR/$BENCHMARK_COVERAGE" "$raw_data_dir" "$SECONDS_PER_RUN" "$RUNS"

info "Evaluating results..."

"$EVALUATION_DIR/evaluate-benchmark.py" --verbose \
    "$raw_data_dir" "$BUILDS_DIR/$BENCHMARK_GROUND_TRUTH" "$BUILDS_DIR/$BENCHMARK_COVERAGE" \
    "$results_dir"


if [[ ${PACKAGE_EXPERIMENT:-0} -eq 1 ]]
then
    info "Packing up..."

    # We need to do this because AFL++ creates directories and files that are only readable by the
    # owner (`root` in the Docker container).
    chmod -R a+rwX "$experiment_dir"

    # We're packaging the experiment data in the following way:
    # - First, `.tar.xz`-ing the `raw-data/` directory, which contains the raw experiment data, by
    #   far the largest/heaviest part;
    # - Second, zipping the rest of it, to guarantee quick access to the files in the `results/`
    #   directory for quick and easy extraction.
    pushd "$EXPERIMENTS_DIR" >/dev/null 2>&1
        experiment_name="$(basename "$experiment_dir")"
        zipped_experiment="$experiment_name.zip"

        if [[ -f "$zipped_experiment" ]]
        then
            error "'$zipped_experiment' already exists. Stopping to avoid overwriting precious data."
        fi

        pushd "$experiment_dir" >/dev/null 2>&1
            XZ_DEFAULTS="-T 0" tar --use-compress-program=xz -cf raw-data.tar.xz raw-data
        popd >/dev/null 2>&1

        zip --quiet --recurse-paths "$zipped_experiment" "$experiment_name/" --exclude "*/raw-data/*"
        rm -f "$experiment_dir/raw-data.tar.xz"
    popd >/dev/null 2>&1
fi

info "Done!"
