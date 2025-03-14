#!/usr/bin/env python3

"""
Run a benchmark with both `rosa` and `rosa-filter-diff`.

A benchmark consists of one or more runs of `rosa`/`rosa-filter-diff` given a target
program-under-test.
"""

import argparse
import functools
import multiprocessing
import os
import shutil
import signal
import subprocess
import sys
from typing import Optional

NAIVE_DIFF_PROGRAM = "/root/artifact/tools/evaluation/run-naive-diff.sh"
COVERAGE_COLLECTOR_PROGRAM = "/root/artifact/tools/evaluation/collect-coverage.sh"
BACKDOOR_TRIGGERING_INPUT_DIR = "backdoor-triggers"
SCRATCH_DIR = "/root/scratch"

NO_TUI = os.environ.get("NO_TUI", "0") == "1"
DISPLAY_CALIBRATION_RUNS = os.environ.get("DISPLAY_CALIBRATION_RUNS", "0") == "1"
DISPLAY_RUNS = os.environ.get("DISPLAY_RUNS", "0") == "1"


def print_info(message: str) -> None:
    """Print an info message."""
    print(f"\033[1m\033[38;5;129m[RUN-BENCHMARK]  {message}\033[0m", file=sys.stderr)


def get_rosa_cmd(
    config_file: str, verbose: bool, phase_one_corpus_dir: Optional[str] = None
) -> list[str]:
    """Get the command to run `rosa`."""
    rosa_cmd = ["rosa", config_file]
    if phase_one_corpus_dir is not None:
        rosa_cmd = [*rosa_cmd, f"--phase-one-corpus={phase_one_corpus_dir}"]
    if verbose:
        rosa_cmd = [*rosa_cmd, "--verbose"]
    if NO_TUI:
        rosa_cmd = [*rosa_cmd, "--no-tui"]

    return rosa_cmd


def trace_input(test_input_name: str, target_dir: str, output_dir: str) -> None:
    """Trace an input through a target program and store the trace."""
    trace_file = os.path.join(output_dir, f"{test_input_name}.trace")
    rosa_trace_process = subprocess.run(
        [
            "rosa-trace",
            f"--output={trace_file}",
            os.path.join(target_dir, "config.toml"),
            os.path.join(output_dir, test_input_name),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert rosa_trace_process.returncode == 0, "`rosa-trace` failed"


def input_has_variable_behavior(
    previous_trace_file: str, current_trace_file: str
) -> bool:
    """Check if an input has variable behavior across different target versions."""
    rosa_showmap_previous_process = subprocess.run(
        ["rosa-showmap", "--component=syscalls", previous_trace_file],
        capture_output=True,
        text=True,
    )
    assert (
        rosa_showmap_previous_process.returncode == 0
    ), "`rosa-showmap` failed (previous target)"
    rosa_showmap_current_process = subprocess.run(
        ["rosa-showmap", "--component=syscalls", current_trace_file],
        capture_output=True,
        text=True,
    )
    assert (
        rosa_showmap_current_process.returncode == 0
    ), "`rosa-showmap` failed (current target)"

    return rosa_showmap_previous_process.stdout != rosa_showmap_current_process.stdout


def save_invariable_input(
    test_input_name: str,
    previous_traces_dir: str,
    current_traces_dir: str,
    output_dir: str,
) -> None:
    """Save an input and its (current) trace if it is invariable."""
    previous_trace_file = os.path.join(previous_traces_dir, f"{test_input_name}.trace")
    current_trace_file = os.path.join(current_traces_dir, f"{test_input_name}.trace")
    if not input_has_variable_behavior(
        previous_trace_file=previous_trace_file,
        current_trace_file=current_trace_file,
    ):
        shutil.copy(
            os.path.join(current_traces_dir, test_input_name),
            os.path.join(output_dir, test_input_name),
        )
        shutil.copy(
            os.path.join(current_traces_dir, f"{test_input_name}.trace"),
            os.path.join(output_dir, f"{test_input_name}.trace"),
        )


def construct_phase_one_corpus(
    current_target_dir: str,
    previous_target_dir: str,
    seconds_per_run: int,
    output_dir: str,
    verbose: bool,
) -> tuple[str, str, str]:
    """Construct a phase-1 corpus.

    This corpus is formed by tracing the corpus of inputs found by the "previous" run
    through the "current" target program.

    Three different phase-one corpora are formed:
    - A "normal" one, which only contains the test inputs produced in the calibration
      run, traced through the current version of the program;
    - A "poisoned" one, which is identical to the "normal" one, except for an
      attacker-injected backdoor-triggering input found in the test inputs of the
      calibration run;
    - A "selective-poisoned" one, which is like "simple" except it additionally filters
      out any test inputs which do not produce the same behavior (in terms of syscalls)
      in both the previous and current versions of the target.

    This allows the "selective-poisoned" version to get rid of maliciously planted
    backdoor-triggering inputs, which would poison phase one and lead to missing
    backdoors.
    """
    assert seconds_per_run > 0

    # Run `rosa`.
    rosa_process = subprocess.Popen(
        get_rosa_cmd(
            config_file=os.path.join(previous_target_dir, "config.toml"),
            verbose=verbose,
        ),
        cwd=output_dir,
        stdout=None if DISPLAY_CALIBRATION_RUNS else subprocess.DEVNULL,
        stderr=None if DISPLAY_CALIBRATION_RUNS else subprocess.DEVNULL,
    )
    try:
        _ = rosa_process.communicate(timeout=seconds_per_run)
    except subprocess.TimeoutExpired:
        rosa_process.send_signal(signal.SIGINT)
        rosa_process.wait()

    assert rosa_process.returncode == 0, "`rosa` failed (calibration run)"

    # Rename output directories to avoid collisions with actual run.
    shutil.move(
        os.path.join(SCRATCH_DIR, "rosa-out"),
        os.path.join(output_dir, "rosa-out-phase-one"),
    )
    shutil.move(
        os.path.join(SCRATCH_DIR, "fuzzer-out"),
        os.path.join(output_dir, "fuzzer-out-phase-one"),
    )

    # Create a directory with the phase one corpus (i.e., the inputs from the
    # calibration run).
    phase_one_corpus_dir = os.path.join(output_dir, "phase-one-corpus")
    os.makedirs(phase_one_corpus_dir)
    traces_dir = os.path.join(output_dir, "rosa-out-phase-one", "traces")
    test_inputs = []
    for element in os.listdir(traces_dir):
        if not (element.endswith(".trace") or element == "README.txt"):
            test_inputs.append(element)

    for test_input in test_inputs:
        shutil.copy(
            os.path.join(traces_dir, test_input),
            os.path.join(phase_one_corpus_dir, test_input),
        )
    with multiprocessing.Pool(multiprocessing.cpu_count()) as process_pool:
        process_pool.map(
            functools.partial(
                trace_input,
                target_dir=current_target_dir,
                output_dir=phase_one_corpus_dir,
            ),
            test_inputs,
        )

    # Copy the "normal" phase-one corpus to create the poisoned corpus.
    poisoned_phase_one_corpus_dir = os.path.join(
        output_dir, "phase-one-corpus-poisoned"
    )
    shutil.copytree(phase_one_corpus_dir, poisoned_phase_one_corpus_dir)
    # Then, poison the corpus by adding backdoor-triggering inputs to it.
    backdoor_triggering_input_dir = os.path.join(
        previous_target_dir, BACKDOOR_TRIGGERING_INPUT_DIR
    )
    backdoor_triggering_inputs = os.listdir(backdoor_triggering_input_dir)
    for backdoor_triggering_input in backdoor_triggering_inputs:
        shutil.copy(
            os.path.join(backdoor_triggering_input_dir, backdoor_triggering_input),
            os.path.join(poisoned_phase_one_corpus_dir, backdoor_triggering_input),
        )
    with multiprocessing.Pool(multiprocessing.cpu_count()) as process_pool:
        process_pool.map(
            functools.partial(
                trace_input,
                target_dir=current_target_dir,
                output_dir=poisoned_phase_one_corpus_dir,
            ),
            backdoor_triggering_inputs,
        )

    # Now, create a secure phase one corpus directory, filtering out input files which
    # produce the same behavior on both targets.
    selective_poisoned_phase_one_corpus_dir = os.path.join(
        output_dir, "phase-one-corpus-selective-poisoned"
    )
    os.makedirs(selective_poisoned_phase_one_corpus_dir)

    with multiprocessing.Pool(multiprocessing.cpu_count()) as process_pool:
        process_pool.map(
            functools.partial(
                save_invariable_input,
                previous_traces_dir=traces_dir,
                current_traces_dir=poisoned_phase_one_corpus_dir,
                output_dir=selective_poisoned_phase_one_corpus_dir,
            ),
            test_inputs,
        )

    return (
        phase_one_corpus_dir,
        poisoned_phase_one_corpus_dir,
        selective_poisoned_phase_one_corpus_dir,
    )


def run(
    current_target_dir: str,
    previous_target_dir: str,
    coverage_target_dir: str,
    seconds_per_run: int,
    runs: int,
    output_dir: str,
    verbose: bool,
) -> None:
    """Run a benchmark.

    The benchmark is run between two versions of the target program: "current" is taken
    to be a more recent version than "previous".
    """
    assert seconds_per_run > 0
    assert runs > 0

    rosa_filter_diff_cmd = [
        "rosa-filter-diff",
    ]
    rosa_simulate_cmd = [
        "rosa-simulate",
        "--copy-inputs",
    ]
    if verbose:
        rosa_filter_diff_cmd = [*rosa_filter_diff_cmd, "--verbose"]

    for run in range(runs):
        run_dir = os.path.join(output_dir, f"run-{run:02d}")
        os.makedirs(run_dir)

        print_info(f"Performing run {run + 1}/{runs}...")

        print_info(
            (
                f"  [Run {run + 1}/{runs}] Performing calibration run for phase-1 "
                f"corpus ({seconds_per_run} seconds)..."
            ),
        )

        (
            phase_one_corpus_dir,
            poisoned_phase_one_corpus_dir,
            selective_poisoned_phase_one_corpus_dir,
        ) = construct_phase_one_corpus(
            current_target_dir=current_target_dir,
            previous_target_dir=previous_target_dir,
            seconds_per_run=seconds_per_run,
            output_dir=SCRATCH_DIR,
            verbose=verbose,
        )

        print_info(
            (
                f"  [Run {run + 1}/{runs}] Performing RosaSource run "
                f"({seconds_per_run} seconds)..."
            ),
        )
        # Run "vanilla" ROSA with a 1-second phase-one duration.
        rosa_source_process = subprocess.Popen(
            get_rosa_cmd(
                config_file=os.path.join(current_target_dir, "config.toml"),
                verbose=verbose,
            ),
            cwd=SCRATCH_DIR,
            stdout=None if DISPLAY_RUNS else subprocess.DEVNULL,
            stderr=None if DISPLAY_RUNS else subprocess.DEVNULL,
        )
        try:
            _ = rosa_source_process.communicate(timeout=seconds_per_run)
        except subprocess.TimeoutExpired:
            rosa_source_process.send_signal(signal.SIGINT)
            rosa_source_process.wait()
        assert rosa_source_process.returncode == 0, "`rosa` failed"
        # Rename output directories accordingly.
        shutil.move(
            os.path.join(SCRATCH_DIR, "rosa-out"),
            os.path.join(SCRATCH_DIR, "rosa-source-out"),
        )
        shutil.move(
            os.path.join(SCRATCH_DIR, "fuzzer-out"),
            os.path.join(SCRATCH_DIR, "fuzzer-source-out"),
        )

        print_info(f"  [Run {run + 1}/{runs}] Simulating LilyCorpus run...")
        # Simulate a ROSA run with the "unsafe" phase-one corpus.
        rosa_simulate_process = subprocess.run(
            [
                *rosa_simulate_cmd,
                f"--phase-one-corpus={phase_one_corpus_dir}",
                "rosa-source-out",
                os.path.join(current_target_dir, "config.toml"),
            ],
            cwd=SCRATCH_DIR,
            stdout=None if DISPLAY_RUNS else subprocess.DEVNULL,
            stderr=None if DISPLAY_RUNS else subprocess.DEVNULL,
        )
        assert rosa_simulate_process.returncode == 0, "`rosa-simulate` failed"
        # Rename output directory accordingly.
        shutil.move(
            os.path.join(SCRATCH_DIR, "rosa-out"),
            os.path.join(SCRATCH_DIR, "lily-corpus-out"),
        )

        print_info(f"  [Run {run + 1}/{runs}] Simulating LilyCorpusPoisoned run...")
        # Simulate a ROSA run with the "unsafe" phase-one corpus.
        rosa_simulate_process = subprocess.run(
            [
                *rosa_simulate_cmd,
                f"--phase-one-corpus={poisoned_phase_one_corpus_dir}",
                "rosa-source-out",
                os.path.join(current_target_dir, "config.toml"),
            ],
            cwd=SCRATCH_DIR,
            stdout=None if DISPLAY_RUNS else subprocess.DEVNULL,
            stderr=None if DISPLAY_RUNS else subprocess.DEVNULL,
        )
        assert rosa_simulate_process.returncode == 0, "`rosa-simulate` failed"
        # Rename output directory accordingly.
        shutil.move(
            os.path.join(SCRATCH_DIR, "rosa-out"),
            os.path.join(SCRATCH_DIR, "lily-corpus-poisoned-out"),
        )

        print_info(
            f"  [Run {run + 1}/{runs}] Simulating LilyCorpusSelectivePoisoned run..."
        )
        # It is possible for the two versions to be different enough to lead to an
        # empty selective phase-one corpus. In that case, fall back to using the normal
        # RosaSource run.
        if not os.listdir(selective_poisoned_phase_one_corpus_dir):
            print_info(
                "    Selective poisoned phase-one corpus is empty, "
                "falling back on RosaSource"
            )
            shutil.copytree(
                os.path.join(SCRATCH_DIR, "rosa-source-out"),
                os.path.join(SCRATCH_DIR, "lily-corpus-selective-poisoned-out"),
            )
        else:
            # Simulate `rosa` with the selective phase-one corpus.
            rosa_simulate_process = subprocess.run(
                [
                    *rosa_simulate_cmd,
                    f"--phase-one-corpus={selective_poisoned_phase_one_corpus_dir}",
                    "rosa-source-out",
                    os.path.join(current_target_dir, "config.toml"),
                ],
                cwd=SCRATCH_DIR,
                stdout=None if DISPLAY_RUNS else subprocess.DEVNULL,
                stderr=None if DISPLAY_RUNS else subprocess.DEVNULL,
            )
            assert rosa_simulate_process.returncode == 0, "`rosa-simulate` failed"
            # Rename output directory accordingly.
            shutil.move(
                os.path.join(SCRATCH_DIR, "rosa-out"),
                os.path.join(SCRATCH_DIR, "lily-corpus-selective-poisoned-out"),
            )

        print_info(f"  [Run {run + 1}/{runs}] Performing NaiveDiff run...")
        # Run naive diff.
        naive_diff_process = subprocess.run(
            [
                NAIVE_DIFF_PROGRAM,
                os.path.join(SCRATCH_DIR, "fuzzer-source-out", "main", "queue"),
                current_target_dir,
                previous_target_dir,
                os.path.join(SCRATCH_DIR, "naive-diff-out"),
            ],
            cwd=SCRATCH_DIR,
            stdout=None if DISPLAY_RUNS else subprocess.DEVNULL,
            stderr=None if DISPLAY_RUNS else subprocess.DEVNULL,
        )
        assert naive_diff_process.returncode == 0, f"`{NAIVE_DIFF_PROGRAM}` failed"

        print_info(f"  [Run {run + 1}/{runs}] Performing Lily run...")
        # Run `rosa-filter-diff` on the result of `rosa-corpus`.
        rosa_filter_diff_process = subprocess.run(
            [
                *rosa_filter_diff_cmd,
                "lily-corpus-out",
                os.path.join(previous_target_dir, "config.toml"),
                "lily-out",
            ],
            cwd=SCRATCH_DIR,
            stdout=None if DISPLAY_RUNS else subprocess.DEVNULL,
            stderr=None if DISPLAY_RUNS else subprocess.DEVNULL,
        )
        assert rosa_filter_diff_process.returncode == 0, "`rosa-filter-diff` failed"

        print_info(f"  [Run {run + 1}/{runs}] Performing LilyPoisoned run...")
        # Run `rosa-filter-diff` on the result of `rosa-corpus-simple-out`.
        rosa_filter_diff_process = subprocess.run(
            [
                *rosa_filter_diff_cmd,
                "lily-corpus-poisoned-out",
                os.path.join(previous_target_dir, "config.toml"),
                "lily-poisoned-out",
            ],
            cwd=SCRATCH_DIR,
            stdout=None if DISPLAY_RUNS else subprocess.DEVNULL,
            stderr=None if DISPLAY_RUNS else subprocess.DEVNULL,
        )
        assert rosa_filter_diff_process.returncode == 0, "`rosa-filter-diff` failed"

        print_info(f"  [Run {run + 1}/{runs}] Performing LilySelectivePoisoned run...")
        # Run `rosa-filter-diff` on the result of `rosa-corpus-secure-out`.
        rosa_filter_diff_process = subprocess.run(
            [
                *rosa_filter_diff_cmd,
                "lily-corpus-selective-poisoned-out",
                os.path.join(previous_target_dir, "config.toml"),
                "lily-selective-poisoned-out",
            ],
            cwd=SCRATCH_DIR,
            stdout=None if DISPLAY_RUNS else subprocess.DEVNULL,
            stderr=None if DISPLAY_RUNS else subprocess.DEVNULL,
        )
        assert rosa_filter_diff_process.returncode == 0, "`rosa-filter-diff` failed"

        print_info(f"  [Run {run + 1}/{runs}] Collecting coverage...")
        # Collect coverage.
        coverage_collector_process = subprocess.run(
            [
                COVERAGE_COLLECTOR_PROGRAM,
                coverage_target_dir,
                os.path.join(SCRATCH_DIR, "fuzzer-source-out", "main", "queue"),
                os.path.join(SCRATCH_DIR, "coverage-data"),
            ],
            cwd=SCRATCH_DIR,
            stdout=None if DISPLAY_RUNS else subprocess.DEVNULL,
            stderr=None if DISPLAY_RUNS else subprocess.DEVNULL,
        )
        assert (
            coverage_collector_process.returncode == 0
        ), f"`{COVERAGE_COLLECTOR_PROGRAM}` failed"

        # Copy everything to the run directory for storage.
        for directory in (
            "rosa-out-phase-one",
            "fuzzer-out-phase-one",
            "phase-one-corpus",
            "phase-one-corpus-poisoned",
            "phase-one-corpus-selective-poisoned",
            "rosa-source-out",
            "fuzzer-source-out",
            "lily-corpus-out",
            "lily-corpus-poisoned-out",
            "lily-corpus-selective-poisoned-out",
            "naive-diff-out",
            "lily-out",
            "lily-poisoned-out",
            "lily-selective-poisoned-out",
            "coverage-data",
        ):
            shutil.move(
                os.path.join(SCRATCH_DIR, directory), os.path.join(run_dir, directory)
            )

        # Rename all references to the scratch directory.
        escaped_scratch_dir = SCRATCH_DIR.replace("/", "\\/")
        escaped_run_dir = run_dir.replace("/", "\\/")
        subprocess.run(
            [
                "sed",
                "-i",
                "-E",
                f"s/{escaped_scratch_dir}/{escaped_run_dir}/g",
                "lily-corpus-out/config.toml",
                "lily-corpus-poisoned-out/config.toml",
                "lily-corpus-selective-poisoned-out/config.toml",
                "lily-out/config.toml",
                "lily-poisoned-out/config.toml",
                "lily-selective-poisoned-out/config.toml",
            ],
            cwd=run_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Clear scratch directory.
        for element in os.listdir(SCRATCH_DIR):
            full_element_path = os.path.join(SCRATCH_DIR, element)
            try:
                if os.path.isfile(full_element_path):
                    os.unlink(full_element_path)
                else:
                    shutil.rmtree(full_element_path)
            except Exception:
                # We are not killing the experiment over a deletion error.
                pass


def main() -> None:
    """Run a benchmark and evaluate it."""
    parser = argparse.ArgumentParser(
        description="Run a single benchmark a given number of times."
    )
    parser.add_argument(
        "current_target_dir", help='The "current" version of the target.'
    )
    parser.add_argument(
        "previous_target_dir", help='The "previous" version of the target.'
    )
    parser.add_argument(
        "coverage_target_dir",
        help=(
            'The "current" version of the target, instrumented with coverage '
            "tracking."
        ),
    )
    parser.add_argument(
        "output_dir",
        help="The directory where the result of the run(s) should be placed.",
    )
    parser.add_argument(
        "seconds_per_run",
        help="The amount of seconds to allocate to each run.",
        type=int,
    )
    parser.add_argument("runs", help="The number of runs to perform.", type=int)
    parser.add_argument(
        "-v",
        "--verbose",
        help="Display more detailed output.",
        action="store_true",
    )

    args = parser.parse_args()
    assert args is not None

    try:
        # Run the target.
        run(
            current_target_dir=args.current_target_dir,
            previous_target_dir=args.previous_target_dir,
            coverage_target_dir=args.coverage_target_dir,
            seconds_per_run=args.seconds_per_run,
            runs=args.runs,
            output_dir=args.output_dir,
            verbose=args.verbose,
        )
    except KeyboardInterrupt:
        pass

    print_info(f"Done! The results can be found in '{args.output_dir}'.")


if __name__ == "__main__":
    main()
