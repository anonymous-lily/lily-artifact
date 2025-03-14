#!/usr/bin/env python3

"""
Evaluate results of a benchmark, run with both `rosa` and `rosa-filter-diff`.

This script evaluates a set of benchmark runs and stores the results in an output
directory, in the form of CSV files. These CSV files are named after the following
format:

    results-<FILTER VARIANT>.csv

A benchmark consists of one or more runs of `rosa`/`rosa-filter-diff` given a target
program-under-test.
"""

import argparse
import functools
import json
import multiprocessing
import os
import re
import signal
import subprocess
import tomllib
from dataclasses import dataclass
from typing import Optional

DEFAULT_GROUND_TRUTH_MARKER = "***BACKDOOR TRIGGERED***"
TARGET_FILE_PATH = os.path.join("/root", "artifact", "targets", "targets.toml")
EVALUATION_TIMEOUT_SECONDS = 5

with open(TARGET_FILE_PATH, "rb") as target_toml_file:
    TARGET_SETTINGS = tomllib.load(target_toml_file)


@dataclass
class Result:
    """Result of an evaluation."""

    def header(self) -> str:
        """Get the header of the CSV file containing this result."""
        raise NotImplementedError

    def to_csv(self, run_id: int) -> str:
        """Convert the result to CSV form."""
        raise NotImplementedError


@dataclass
class RunResult(Result):
    """Result of a single run."""

    """True positives (suspicious inputs which are actually backdoor-triggering)."""
    true_positives: int = 0
    """False positives (suspicious inputs which are actually safe)."""
    false_positives: int = 0
    """True negatives (safe inputs which are actually safe)."""
    true_negatives: int = 0
    """False negatives (safe inputs which are actually backdoor-triggering)."""
    false_negatives: int = 0
    """The amount of seconds from the start of the run until the first true positive."""
    seconds_to_first_backdoor: Optional[int] = None

    def header(self) -> str:
        """Get the header of the CSV file containing this result."""
        return (
            ",".join(
                (
                    "run_id",
                    "true_positives",
                    "false_positives",
                    "true_negatives",
                    "false_negatives",
                    "seconds_to_first_backdoor",
                )
            )
            + "\n"
        )

    def to_csv(self, run_id: int) -> str:
        """Convert the result to CSV form."""
        return "{},{},{},{},{},{}\n".format(
            run_id,
            self.true_positives,
            self.false_positives,
            self.true_negatives,
            self.false_negatives,
            self.seconds_to_first_backdoor or "N/A",
        )


@dataclass
class CoverageResult(Result):
    """Coverage result of a single run."""

    """The number of lines covered."""
    covered_lines: int
    """The number of total affected lines in the patch."""
    total_lines: int

    def header(self) -> str:
        """Get the header of the CSV file containing this result."""
        return (
            ",".join(
                (
                    "run_id",
                    "covered_lines",
                    "total_lines",
                )
            )
        ) + "\n"

    def to_csv(self, run_id: int) -> str:
        """Convert the result to CSV form."""
        return "{},{},{}\n".format(
            run_id,
            self.covered_lines,
            self.total_lines,
        )


@dataclass
class SourceLineOfCode:
    """A line of source code (SLOC)."""

    """The relative path of the source file this line is in."""
    source_file_path: str
    """The number of the line."""
    line_number: int

    def __str__(self) -> str:
        """Get the string representation of the SLOC."""
        return f"{self.source_file_path}:{self.line_number}"


def get_affected_lines(patch: str, target_dir: str) -> list[SourceLineOfCode]:
    """Get the affected lines (per file) given a patch.

    This is essentially the lines to monitor for coverage, in order to know if the
    patch was covered.
    """
    result = []
    hunk_start_string = "\n@@ "
    diff_header = "\ndiff --git "

    segment_start_index = patch.find(diff_header)
    while segment_start_index != -1:
        next_segment_start_index = patch.find(diff_header, segment_start_index + 1)
        if next_segment_start_index == -1:
            # Skip the leading newline.
            segment = patch[segment_start_index + 1 :]
        else:
            # Skip the leading newline.
            segment = patch[segment_start_index + 1 : next_segment_start_index]

        segment_lines = segment.split("\n")
        last_header_line_index_candidates = [
            i for i, line in enumerate(segment_lines) if line.startswith("+++ ")
        ]
        if not last_header_line_index_candidates:
            # Skip this segment, probably a binary file.
            segment_start_index = next_segment_start_index
            continue
        segment_header = segment_lines[: last_header_line_index_candidates[0] + 1]
        # Skip the leading "+++ <FILE>".
        raw_file_path = segment_header[-1][5:]
        adapted_target_dir = os.path.join(target_dir, "original")
        rel_file_path = os.path.relpath(raw_file_path, adapted_target_dir)

        affected_lines = set()
        hunk_start_index = segment.find(hunk_start_string)
        while hunk_start_index != -1:
            next_hunk_start_index = segment.find(
                hunk_start_string, hunk_start_index + 1
            )
            if next_hunk_start_index == -1:
                # Make sure to not include the "diff --git ..." header of the next
                # segment (if there is one).
                hunk_end_index = segment.find(diff_header, hunk_start_index + 1)
                if hunk_end_index == -1:
                    # Skip the leading newline.
                    hunk = segment[hunk_start_index + 1 :]
                else:
                    # Skip the leading newline.
                    hunk = segment[hunk_start_index + 1 : hunk_end_index]
            else:
                # Skip the leading newline.
                hunk = segment[hunk_start_index + 1 : next_hunk_start_index]

            hunk_lines = [line for line in hunk.split("\n") if line and line]
            # Filter out lines starting with '\' (stuff like "no newline at the end of
            # file).
            hunk_lines = [line for line in hunk_lines if not line.startswith("\\")]
            hunk_header = hunk_lines[0]
            # We need to get the starting line number for the hunk.
            # The hunk header will look like "@@ -A,B +C,D @", where:
            #     A: the starting line of the hunk *before* the diff is applied
            #     B: the line count of the hunk *before* the diff is applied
            #     C: the starting line of the hunk *after* the diff is applied
            #     D: the line count of the hunk *after* the diff is applied
            # We are only interested in C, which will give us the starting line number
            # to count from to get the actual line number in the source file.
            hunk_header_elements = hunk_header.split(" ")
            starting_line = int(hunk_header_elements[2][1:].split(",")[0])

            current_line_number = starting_line - 1
            for i, hunk_line in enumerate(hunk_lines[1:]):
                if hunk_line[0] != "-":
                    current_line_number += 1

                if hunk_line[0] == "+":
                    affected_lines.add(current_line_number)
                elif hunk_line[0] == "-":
                    # Handle removed lines by potentially adding lines before and after
                    # them. We don't want to naively do this for every removed line,
                    # though, as we may have blocks of removed lines.
                    #
                    # So, we will only add the previous and next lines if they are
                    # *not* removed lines.

                    # Remember, we index `hunk_lines` at 1 to get the actual SLOCs, so
                    # we need to offset `i` accordingly.

                    # This is the case where we've hit the start of a block of removed
                    # code, so we need to add the line before it.
                    if i > 1 and hunk_lines[1 + (i - 1)][0] != "-":
                        affected_lines.add(current_line_number)
                    # This is the case where we've hit the end of a block of removed
                    # code, so we need to add the line after it.
                    if i < len(hunk_lines) - 2 and hunk_lines[1 + (i + 1)][0] != "-":
                        affected_lines.add(current_line_number + 1)

            hunk_start_index = next_hunk_start_index

        for line_number in affected_lines:
            result.append(
                SourceLineOfCode(
                    source_file_path=rel_file_path,
                    line_number=line_number,
                )
            )

        segment_start_index = next_segment_start_index

    return result


def get_coverage(
    slocs: list[SourceLineOfCode],
    target_dir: str,
    target_program: str,
    coverage_file: str,
) -> dict[str, Optional[int]]:
    """Get the coverage (number of hits) of a list of source lines of code."""
    target_repo_dir = os.path.join(target_dir, "original")
    llvm_cov_process = subprocess.run(
        [
            "llvm-cov-21",
            "show",
            f"--instr-profile={coverage_file}",
            os.path.join(target_repo_dir, target_program),
        ],
        capture_output=True,
    )
    assert llvm_cov_process.returncode == 0, "`llvm-cov` failed"

    raw_coverage_report = llvm_cov_process.stdout.decode(
        encoding="utf-8", errors="ignore"
    )

    raw_file_reports = [
        raw_report for raw_report in raw_coverage_report.split("\n\n") if raw_report
    ]

    def process_hit_number(raw_number: str) -> int:
        """Process the number of hits that llvm-cov provides into an int."""
        if raw_number[-1] == "k":
            return int(1e3 * float(raw_number[:-1]))
        elif raw_number[-1] == "M":
            return int(1e6 * float(raw_number[:-1]))
        elif raw_number[-1] == "G":
            return int(1e9 * float(raw_number[:-1]))
        elif raw_number[-1] == "T":
            return int(1e12 * float(raw_number[:-1]))

        return int(raw_number)

    coverage_reports = {}
    for raw_report in raw_file_reports:
        raw_report_lines = raw_report.split("\n")
        file_path = raw_report_lines[0][:-1]
        # Get path file relative to the root of the target repo.
        #
        # Sometimes, we have to use unpacked release tarballs to get versions that are
        # not in the Git repo. In that case, there is no `original/` directory in the
        # source code (it's just the name of the version/tarball). As such, we have to
        # handle both cases.
        if file_path.startswith(target_repo_dir):
            rel_file_path = os.path.relpath(file_path, start=target_repo_dir)
        elif file_path.startswith(target_dir):
            rel_file_path = os.path.relpath(file_path, start=target_dir)
        else:
            # If we can't match either version of the target dir to the beginning of
            # the file, then we should simply ignore the file, since it's out-of-tree.
            # This can happen with the ROSA header (which includes the
            # `__ROSA_TRACE_START()` macro), among other things. We obviously don't
            # care about covering that.
            continue

        hit_counts = []
        for raw_report_line in raw_report_lines[1:]:
            # Sometimes, we get stuff like this in the coverage report:
            #
            # ```
            #  ------------------
            #  | Unexecuted instantiation: sccp.c:scdf_is_edge_feasible
            #  ------------------
            # ```
            #
            # This is irrelevant to the coverage measurements for us, so we should
            # simply skip over those lines.
            if raw_report_line.startswith("  -") or raw_report_line.startswith("  |"):
                continue
            raw_hit_count = raw_report_line.split("|")[1].strip()
            hit_count = process_hit_number(raw_hit_count) if raw_hit_count else None
            hit_counts.append(hit_count)

        coverage_reports[rel_file_path] = hit_counts

    output_report = {}
    for sloc in slocs:
        cov_report = coverage_reports.get(sloc.source_file_path)
        if cov_report is not None:
            output_report[str(sloc)] = cov_report[sloc.line_number - 1]
        else:
            output_report[str(sloc)] = None

    return output_report


def evaluate_coverage(
    patch_file: str,
    target_dir: str,
    target_program: str,
    coverage_file: str,
    report_output_dir: str,
) -> CoverageResult:
    """Evaluate the coverage of a patch given a coverage file (*.profdata)."""
    with open(patch_file, "r", errors="replace") as fd:
        patch = fd.read()

    affected_lines = get_affected_lines(patch=patch, target_dir=target_dir)
    coverage_dict = get_coverage(
        slocs=affected_lines,
        target_dir=target_dir,
        target_program=target_program,
        coverage_file=coverage_file,
    )
    # Dump coverage result logs in `coverage-data/`.
    with open(os.path.join(report_output_dir, "report.json"), "w") as fd:
        fd.write(json.dumps(coverage_dict, sort_keys=True, indent=4))

    # Filter out any lines that do not have valid hits (e.g., comments).
    valid_line_hits = [hits for hits in coverage_dict.values() if hits is not None]
    return CoverageResult(
        covered_lines=len([hits for hits in valid_line_hits if hits > 0]),
        total_lines=len(valid_line_hits),
    )


def evaluate_baseline_test_input(
    test_input_path: str,
    target_program: list[str],
    stdin_input: bool,
    ground_truth_marker: str,
) -> bool:
    """Evaluate the result of a single baseline test input.

    If it triggers the backdoor, return `True`, otherwise return `False`.
    """
    # Filter out any `@@`s.
    target_program = [arg for arg in target_program if arg != "@@"]
    if stdin_input:
        with open(test_input_path, "rb") as test_input_file:
            target_program_process = subprocess.Popen(
                target_program,
                stdin=test_input_file,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
    else:
        target_program_process = subprocess.Popen(
            target_program + [test_input_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    try:
        _ = target_program_process.communicate(timeout=EVALUATION_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        target_program_process.send_signal(signal.SIGINT)
        target_program_process.wait()

    output_stdout, output_stderr = target_program_process.communicate()

    return ground_truth_marker in output_stdout.decode(
        encoding="utf-8", errors="ignore"
    ) or ground_truth_marker in output_stderr.decode(encoding="utf-8", errors="ignore")


def evaluate_baseline_run(
    baseline_inputs_dir: str,
    target_program: list[str],
    stdin_input: bool,
    ground_truth_marker: str,
    time_limit_seconds: Optional[int],
) -> RunResult:
    """Evaluate the baseline inputs for a single run, for a single target."""
    baseline_inputs = []
    baseline_input_times_milliseconds = []
    last_timestamp_milliseconds = 0

    for element in sorted(os.listdir(baseline_inputs_dir)):
        # Only keep directories (which should store deduplicated test inputs).
        if os.path.isdir(os.path.join(baseline_inputs_dir, element)):
            inputs_subdir = os.path.join(baseline_inputs_dir, element)
            # Pick the first file from the directory as the "witness".
            test_input_files = [
                element
                for element in os.listdir(inputs_subdir)
                if element.startswith("id:")
            ]
            witness_test_input = sorted(test_input_files)[0]
            # Get the time for the input file.
            timestamp_match = re.search(r"time:(\d+)", witness_test_input)
            input_milliseconds = last_timestamp_milliseconds
            if timestamp_match is not None:
                input_milliseconds = int(timestamp_match.group(1))
                last_timestamp_milliseconds = input_milliseconds

            baseline_inputs.append(os.path.join(inputs_subdir, witness_test_input))
            baseline_input_times_milliseconds.append(input_milliseconds)

    # Run actual evaluation.
    run_result = RunResult()
    with multiprocessing.Pool(multiprocessing.cpu_count()) as process_pool:
        results = process_pool.map(
            functools.partial(
                evaluate_baseline_test_input,
                target_program=target_program,
                stdin_input=stdin_input,
                ground_truth_marker=ground_truth_marker,
            ),
            baseline_inputs,
        )

    for index, result in enumerate(results):
        seconds = baseline_input_times_milliseconds[index] // 1000
        # Round up to 1 second if needed.
        if seconds == 0:
            seconds = 1

        # Skip if past time limit.
        if time_limit_seconds is not None and seconds > time_limit_seconds:
            continue

        if result:
            run_result.true_positives += 1
            if run_result.seconds_to_first_backdoor is None:
                run_result.seconds_to_first_backdoor = seconds
        else:
            run_result.false_positives += 1

    return run_result


def evaluate_rosa_run(
    rosa_dir: str,
    target_program: list[str],
    ground_truth_marker: str,
    time_limit_seconds: Optional[int],
) -> RunResult:
    """Evaluate the ROSA inputs for a single run, for a single target."""
    time_limit_args = (
        ["--time-limit", f"{time_limit_seconds}"]
        if time_limit_seconds is not None
        else []
    )

    evaluation_cmd = [
        "rosa-evaluate",
        "--target-program",
        " ".join(["timeout", f"{EVALUATION_TIMEOUT_SECONDS}s", *target_program]),
        "--summary",
        *time_limit_args,
        "--",
        rosa_dir,
    ]

    rosa_evaluate_process = subprocess.run(
        evaluation_cmd,
        capture_output=True,
        text=True,
    )
    assert rosa_evaluate_process.returncode == 0, "\n".join(
        (
            "`rosa-evaluate` failed:",
            f"  cmd: `{' '.join(evaluation_cmd)}`",
            f"  stderr: {rosa_evaluate_process.stderr}",
            f"  stdout: {rosa_evaluate_process.stdout}",
        )
    )

    output_lines = rosa_evaluate_process.stdout.split("\n")
    (raw_tp, raw_fp, raw_tn, raw_fn, raw_seconds) = output_lines[1].split(",")

    return RunResult(
        true_positives=int(raw_tp),
        false_positives=int(raw_fp),
        true_negatives=int(raw_tn),
        false_negatives=int(raw_fn),
        seconds_to_first_backdoor=None if raw_seconds == "N/A" else int(raw_seconds),
    )


def evaluate_run(
    run_dir: str,
    ground_truth_target_program: list[str],
    coverage_target_dir: str,
    coverage_target_program: str,
    stdin_input: bool,
    ground_truth_marker: str,
    patch_file: str,
    coverage_file: str,
    verbose: bool,
    time_limit_seconds: Optional[int],
) -> dict[str, Result]:
    """Evaluate a single run for a single target."""
    print("  Evaluating RosaSource...")
    rosa_source_results = evaluate_rosa_run(
        os.path.join(run_dir, "rosa-source-out"),
        target_program=ground_truth_target_program,
        ground_truth_marker=ground_truth_marker,
        time_limit_seconds=time_limit_seconds,
    )

    # This is used for the phase-one duration study.
    if os.environ.get("EVALUATE_ROSA_SOURCE_ONLY", "0") == "1":
        return {
            "rosa-source": rosa_source_results,
        }

    print("  Evaluating LilyCorpus...")
    lily_corpus_results = evaluate_rosa_run(
        os.path.join(run_dir, "lily-corpus-out"),
        target_program=ground_truth_target_program,
        ground_truth_marker=ground_truth_marker,
        time_limit_seconds=time_limit_seconds,
    )
    print("  Evaluating LilyCorpusPoisoned...")
    lily_corpus_poisoned_results = evaluate_rosa_run(
        os.path.join(run_dir, "lily-corpus-poisoned-out"),
        target_program=ground_truth_target_program,
        ground_truth_marker=ground_truth_marker,
        time_limit_seconds=time_limit_seconds,
    )
    print("  Evaluating LilyCorpusSelectivePoisoned...")
    lily_corpus_selective_poisoned_results = evaluate_rosa_run(
        os.path.join(run_dir, "lily-corpus-selective-poisoned-out"),
        target_program=ground_truth_target_program,
        ground_truth_marker=ground_truth_marker,
        time_limit_seconds=time_limit_seconds,
    )
    print("  Evaluating NaiveDiff...")
    naive_diff_results = evaluate_baseline_run(
        baseline_inputs_dir=os.path.join(run_dir, "naive-diff-out"),
        target_program=ground_truth_target_program,
        stdin_input=stdin_input,
        ground_truth_marker=ground_truth_marker,
        time_limit_seconds=time_limit_seconds,
    )
    print("  Evaluating Lily...")
    lily_results = evaluate_rosa_run(
        os.path.join(run_dir, "lily-out"),
        target_program=ground_truth_target_program,
        ground_truth_marker=ground_truth_marker,
        time_limit_seconds=time_limit_seconds,
    )
    print("  Evaluating LilyPoisoned...")
    lily_poisoned_results = evaluate_rosa_run(
        os.path.join(run_dir, "lily-poisoned-out"),
        target_program=ground_truth_target_program,
        ground_truth_marker=ground_truth_marker,
        time_limit_seconds=time_limit_seconds,
    )
    print("  Evaluating LilySelectivePoisoned...")
    lily_selective_poisoned_results = evaluate_rosa_run(
        os.path.join(run_dir, "lily-selective-poisoned-out"),
        target_program=ground_truth_target_program,
        ground_truth_marker=ground_truth_marker,
        time_limit_seconds=time_limit_seconds,
    )

    print("  Evaluating coverage...")
    coverage_results = evaluate_coverage(
        patch_file=patch_file,
        target_program=coverage_target_program,
        target_dir=coverage_target_dir,
        coverage_file=coverage_file,
        report_output_dir=os.path.join(run_dir, "coverage-data"),
    )

    return {
        "rosa-source": rosa_source_results,
        "lily-corpus": lily_corpus_results,
        "lily-corpus-poisoned": lily_corpus_poisoned_results,
        "lily-corpus-selective-poisoned": lily_corpus_selective_poisoned_results,
        "naive-diff": naive_diff_results,
        "lily": lily_results,
        "lily-poisoned": lily_poisoned_results,
        "lily-selective-poisoned": lily_selective_poisoned_results,
        "coverage": coverage_results,
    }


def evaluate_benchmark(
    benchmark_dir: str,
    ground_truth_target_program: list[str],
    coverage_target_program: str,
    coverage_target_dir: str,
    stdin_input: bool,
    ground_truth_marker: str,
    verbose: bool,
    time_limit_seconds: Optional[int],
) -> dict[str, list[Result]]:
    """Evaluate a full benchmark (multiple runs) for a single target.

    This also takes into account that the runs might be parallel (i.e., there might be
    nested directories for parallel runs in the benchmark directory.
    """
    run_dirs = []
    for element in sorted(os.listdir(benchmark_dir)):
        element_path = os.path.join(benchmark_dir, element)
        if os.path.isdir(element_path) and element.startswith("parallel-"):
            for subelement in sorted(os.listdir(element_path)):
                subelement_path = os.path.join(element_path, subelement)
                if os.path.isdir(subelement_path) and subelement.startswith("run-"):
                    run_dirs.append(subelement_path)
        elif os.path.isdir(element_path) and element.startswith("run-"):
            run_dirs.append(element_path)

    benchmark_results = {}
    for run_dir in run_dirs:
        print(f"Evaluating run {run_dir}...")
        run_results = evaluate_run(
            run_dir=run_dir,
            ground_truth_target_program=ground_truth_target_program,
            coverage_target_program=coverage_target_program,
            coverage_target_dir=coverage_target_dir,
            stdin_input=stdin_input,
            ground_truth_marker=ground_truth_marker,
            patch_file=os.path.join(coverage_target_dir, "full-diff.patch"),
            coverage_file=os.path.join(run_dir, "coverage-data", "coverage.profdata"),
            verbose=verbose,
            time_limit_seconds=time_limit_seconds,
        )

        for kind in run_results:
            if kind not in benchmark_results:
                benchmark_results[kind] = [run_results[kind]]
            else:
                benchmark_results[kind] += [run_results[kind]]

    return benchmark_results


def main() -> None:
    """Run a benchmark and evaluate it."""
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate a single benchmark. "
            "Benchmarks should be generated with `run-benchmark.py`."
        )
    )
    parser.add_argument(
        "benchmark_dir", help="The directory containing the output of the benchmark."
    )
    parser.add_argument(
        "ground_truth_target_dir",
        help="The directory containing the ground-truth version of the target.",
    )
    parser.add_argument(
        "coverage_target_dir",
        help=(
            "The directory containing the coverage-instrumented version of the target."
        ),
    )
    parser.add_argument(
        "output_dir",
        help="The directory where the result of the evaluation should be placed.",
    )
    parser.add_argument(
        "-g",
        "--ground-truth-marker",
        help=(
            "The ground-truth marker to check for in the stderr and stdout of the "
            "target."
        ),
        default=DEFAULT_GROUND_TRUTH_MARKER,
    )
    parser.add_argument(
        "-t",
        "--time-limit",
        help=(
            "Do not evaluate inputs discovered past a certain time limit (in seconds)."
        ),
        type=int,
        default=None,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        help="Display more detailed output.",
        action="store_true",
    )

    args = parser.parse_args()
    assert args is not None

    # The expected target directory name is `<target name>__<suffix>`. The suffix is
    # optional.
    target_name = os.path.basename(
        args.ground_truth_target_dir.rstrip(os.path.sep)
    ).split("__")[0]
    assert (
        target_name in TARGET_SETTINGS
    ), f"Unknown target '{target_name}'. Expected {', '.join(TARGET_SETTINGS.keys())}."

    ground_truth_target_program = [
        os.path.join(
            args.ground_truth_target_dir,
            "original",
            TARGET_SETTINGS[target_name]["program"],
        ),
        *[
            arg.replace("__TARGET_DIR__", args.ground_truth_target_dir)
            for arg in TARGET_SETTINGS[target_name]["arguments"]
        ],
    ]
    stdin_input = False
    if TARGET_SETTINGS[target_name]["input"] in ("libfuzzer", "file"):
        ground_truth_target_program.append("@@")
    else:
        stdin_input = True

    coverage_target_program = ground_truth_target_program[0].replace(
        args.ground_truth_target_dir, args.coverage_target_dir
    )

    benchmark_results = evaluate_benchmark(
        benchmark_dir=args.benchmark_dir,
        ground_truth_target_program=ground_truth_target_program,
        coverage_target_program=coverage_target_program,
        coverage_target_dir=args.coverage_target_dir,
        stdin_input=stdin_input,
        ground_truth_marker=args.ground_truth_marker,
        verbose=args.verbose,
        time_limit_seconds=args.time_limit,
    )

    for kind, results in benchmark_results.items():
        with open(
            os.path.join(args.output_dir, f"results-{kind}.csv"), "w"
        ) as output_results_file:
            output_results_file.write(results[0].header())
            for run_id, result in enumerate(results):
                csv_line = result.to_csv(run_id=run_id)
                output_results_file.write(f"{csv_line}")


if __name__ == "__main__":
    main()
