#!/usr/bin/env bash


## Generate a coverage file (`.profdata`) for a set of test inputs.
##
## This coverage file can then be used to generate a coverage report (using `llvm-cov`).
## See https://clang.llvm.org/docs/SourceBasedCodeCoverage.html for more details.

set -e


# `LOG_HEADER` is used in `$COMMON`.
# shellcheck disable=SC2034
LOG_HEADER="collect-coverage"
COMMON="/root/artifact/tools/common.sh"
# Ignore `source` check here, it will be checked independently.
# shellcheck source=/dev/null
source "$COMMON"


if [[ $# -ne 3 ]]
then
    error "usage: $0 <TARGET DIR> <TEST INPUT DIR> <OUTPUT DIR>"
fi

target_config_file="$1/config.toml"
test_input_dir="$2"
output_dir="$3"
coverage_file="$output_dir/coverage.profdata"

mkdir -p "$output_dir"

info "Collecting coverage..."

get_coverage_for_test_input() {
    local output_dir target_config_file test_input input_name

    if [[ $# -ne 3 ]]
    then
        error "INTERNAL: usage:" \
            "get_coverage_for_test_input(output_dir, target_config_file, test_input)"
    fi

    output_dir="$1"
    target_config_file="$2"
    test_input="$3"

    input_name="${test_input##*/}"
    input_name="${input_name%%,*}"
    export LLVM_PROFILE_FILE="$output_dir/$input_name.profraw"
    rosa-trace --output="$output_dir/$input_name.trace" "$target_config_file" "$test_input" \
        2>/dev/null
    rm "$output_dir/$input_name.trace"
}
# Needed for GNU parallel.
export -f get_coverage_for_test_input error

mapfile -t test_inputs < \
    <(find "$test_input_dir" -type f ! -name "README.txt" ! -name "*.trace" ! -path "*/.state/*")
printf "%s\n" "${test_inputs[@]}" | parallel -j"$(nproc)" --block 10k \
    get_coverage_for_test_input "$output_dir" "$target_config_file"

raw_profile_files=("$output_dir"/*.profraw)
raw_profile_file_list="$output_dir/.raw-profile-file-list"
printf "%s\n" "${raw_profile_files[@]}" > "$raw_profile_file_list"
llvm-profdata-21 merge --failure-mode=all --input-files="$raw_profile_file_list" \
    --output "$coverage_file"
rm "$raw_profile_file_list"
# Delete all of the `*.profraw` to save space.
echo "${raw_profile_files[*]}" | xargs rm -f

info "Done! Coverage file at $coverage_file"
