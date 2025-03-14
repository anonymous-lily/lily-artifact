#!/usr/bin/env bash


## Run a naive differential oracle between two versions of a target program.

set -e


# `LOG_HEADER` is used in `$COMMON`.
# shellcheck disable=SC2034
LOG_HEADER="naive-diff"
COMMON="/root/artifact/tools/common.sh"
# Ignore `source` check here, it will be checked independently.
# shellcheck source=/dev/null
source "$COMMON"


if [[ $# -ne 4 ]]
then
    error "usage: $0 <TEST INPUT DIR> <CURRENT TARGET DIR> <PREVIOUS TARGET DIR> <OUTPUT DIR>"
fi

test_input_dir="$1"
current_target_dir="$2"
previous_target_dir="$3"
output_dir="$4"

if [[ -d "$output_dir" ]]
then
    error "output directory $output_dir already exists." \
        "Stopping to avoid overwriting precious data."
fi
mkdir -p "$output_dir"


check_test_input() {
    local test_input current_target_dir previous_target_dir output_dir test_input_hash \
        trace_after syscalls_before syscalls_after diff diff_hash

    if [[ $# -ne 4 ]]
    then
        error "INTERNAL: usage:" \
            "check_test_input(current_target_dir, previous_target_dir, output_dir, test_input)"
    fi

    current_target_dir="$1"
    previous_target_dir="$2"
    output_dir="$3"
    test_input="$4"

    test_input_hash="$(echo "$test_input" | sha1sum | cut -d ' ' -f 1)"
    trace_before="$output_dir/.$test_input_hash.before.trace"
    trace_after="$output_dir/.$test_input_hash.after.trace"

    rosa-trace --output="$trace_before" \
        "$previous_target_dir/config.toml" "$test_input" 2>/dev/null
    rosa-trace --output="$trace_after" \
        "$current_target_dir/config.toml" "$test_input" 2>/dev/null

    syscalls_before="$(rosa-showmap "$trace_before")"
    syscalls_after="$(rosa-showmap "$trace_after")"
    # Make sure to not show line numbers, as that can throw the diff off.
    diff="$(diff --old-line-format="< %L" --new-line-format="> %L" --unchanged-line-format="" \
        <(echo "$syscalls_before") <(echo "$syscalls_after") || echo "")"
    diff_hash="$(echo "$diff" | sha1sum | cut -d ' ' -f 1)"

    if [[ "$diff" != "" ]]
    then
        mkdir -p "$output_dir/$diff_hash"
        echo "$diff" > "$output_dir/$diff_hash/syscalls.diff"
        cp "$test_input" "$output_dir/$diff_hash"
    fi

    rm "$trace_before" "$trace_after"
}
# Needed for GNU parallel.
export -f check_test_input error


info "Running naive differential oracle..."

test_inputs=("$test_input_dir"/id*)

printf "%s\n" "${test_inputs[@]}" | parallel -j"$(nproc)" --block 10k \
    check_test_input "$current_target_dir" "$previous_target_dir" "$output_dir"

info "Done!"
