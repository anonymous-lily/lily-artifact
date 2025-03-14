#!/usr/bin/env python3


"""
Extract results from a benchmark tarball.

Benchmark results are packaged in zip files, which contain both results (CSV files
containing various metrics) as well as raw experiment data (AFL++ & ROSA
output), aggressively compressed in a tarball. This 2-level compression allows us to
simultaneously reduce the overall size of the experiment artifacts and also make
CSV/result file extraction fast.

This script dumps the summary of all the experiment metrics in `stdout` in JSON form.
"""


from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
from dataclasses import dataclass
from typing import Any, Optional, Sequence

CATEGORIES = (
    "safe-commit",
    "safe-code-commit",
    "safe-release",
    "simple-commit",
    "simple-release",
)


@dataclass
class RunMetrics:
    """Metrics for a single run of a single variant."""

    run_id: int


@dataclass
class DetectionRunMetrics(RunMetrics):
    """Metrics for a single run of a single backdoor detection variant."""

    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    seconds_to_first_backdoor: Optional[int]

    @staticmethod
    def from_raw_results(raw_results: str) -> list[DetectionRunMetrics]:
        """Parse the metrics of a detection run from the raw CSV results."""
        # Skip header.
        raw_result_lines = [line for line in raw_results.split("\n") if line][1:]
        run_metrics = []

        for line in raw_result_lines:
            (
                run_id,
                true_positives,
                false_positives,
                true_negatives,
                false_negatives,
                raw_seconds_to_first_backdoor,
            ) = line.split(",")

            if raw_seconds_to_first_backdoor == "N/A":
                seconds_to_first_backdoor = None
            else:
                seconds_to_first_backdoor = int(raw_seconds_to_first_backdoor)

            run_metrics.append(
                DetectionRunMetrics(
                    run_id=int(run_id),
                    true_positives=int(true_positives),
                    false_positives=int(false_positives),
                    true_negatives=int(true_negatives),
                    false_negatives=int(false_negatives),
                    seconds_to_first_backdoor=seconds_to_first_backdoor,
                )
            )

        return run_metrics

    def is_failed(self) -> bool:
        """Check whether the run failed to detect a backdoor."""
        return self.seconds_to_first_backdoor is None


@dataclass
class CoverageRunMetrics(RunMetrics):
    """Metrics for a single run for SLOC coverage."""

    covered_lines: Optional[int]
    total_lines: int

    @staticmethod
    def from_raw_results(raw_results: str) -> list[CoverageRunMetrics]:
        """Parse the metrics of a detection run from the raw CSV results."""
        # Skip header.
        raw_result_lines = [line for line in raw_results.split("\n") if line][1:]
        run_metrics = []

        for line in raw_result_lines:
            (run_id, covered_lines, total_lines) = line.split(",")

            if int(total_lines) == 0:
                metrics = CoverageRunMetrics(
                    run_id=int(run_id), covered_lines=None, total_lines=0
                )
            else:
                metrics = CoverageRunMetrics(
                    run_id=int(run_id),
                    covered_lines=int(covered_lines),
                    total_lines=int(total_lines),
                )

            run_metrics.append(metrics)

        return run_metrics

    def coverage_percentage(self) -> Optional[float]:
        """Get the coverage percentage for this run."""
        if self.total_lines == 0:
            return None

        assert self.covered_lines is not None
        return self.covered_lines / self.total_lines


VARIANTS = (
    ("coverage", CoverageRunMetrics),
    ("rosa-source", DetectionRunMetrics),
    ("lily-corpus", DetectionRunMetrics),
    ("naive-diff", DetectionRunMetrics),
    ("lily", DetectionRunMetrics),
    ("lily-corpus-poisoned", DetectionRunMetrics),
    ("lily-corpus-selective-poisoned", DetectionRunMetrics),
    ("lily-poisoned", DetectionRunMetrics),
    ("lily-selective-poisoned", DetectionRunMetrics),
)


@dataclass
class VariantMetrics:
    """Metrics for a single variant across multiple runs."""

    variant: str
    runs: Sequence[RunMetrics]

    def failed_runs(self) -> list[RunMetrics]:
        """Get the runs which have not detected a true positive."""
        return [run for run in self.runs if getattr(run, "is_failed", lambda: False)()]

    def runs_with_false_positives(self) -> list[RunMetrics]:
        """Get the runs which have at least one false positive."""
        return [run for run in self.runs if getattr(run, "false_positives", 0) > 0]

    def runs_with_false_negatives(self) -> list[RunMetrics]:
        """Get the runs which have at least one false negative."""
        return [run for run in self.runs if getattr(run, "false_negatives", 0) > 0]

    def false_positives(self) -> dict[str, float]:
        """Get the statistics of the false positives across all runs."""
        fps = [getattr(run, "false_positives", 0) for run in self.runs]

        return {
            "min": min(fps),
            "avg": statistics.mean(fps),
            "stdev": statistics.stdev(fps) if len(fps) > 1 else 0.0,
            "max": max(fps),
        }


@dataclass
class ExperimentResults:
    """A set of results for the entire experiment."""

    date: str
    target: str
    category: str
    ref: str
    variant_metrics: dict[str, VariantMetrics]

    def coverage(self) -> dict[str, Any]:
        """Get the coverage statistics for the experiment."""
        coverage_metrics = self.variant_metrics["coverage"]

        coverage_percentages = []
        for run in coverage_metrics.runs:
            percentage = getattr(run, "coverage_percentage", lambda: None)()
            if percentage is None:
                return {
                    "min": None,
                    "avg": None,
                    "stdev": None,
                    "max": None,
                }
            else:
                coverage_percentages.append(percentage)

        return {
            "min": min(coverage_percentages),
            "avg": statistics.mean(coverage_percentages),
            "stdev": (
                statistics.stdev(coverage_percentages)
                if len(coverage_percentages) > 1
                else 0.0
            ),
            "max": max(coverage_percentages),
        }


@dataclass
class StudyResults:
    """A set of results for an entire study with multiple experiments.

    A study is a meta-experiment across many experiments, for example all of the
    "simple-commit" experiments across all targets.
    """

    study: str
    target: str
    experiments: list[ExperimentResults]

    def summary(self) -> dict[str, Any]:
        """Produce a summary of a given study.

        Generally, these are the interesting results which will make it in the paper.
        """
        average_coverage_and_refs = [
            (experiment.ref, experiment.coverage()["avg"])
            for experiment in self.experiments
        ]
        uncoverable_refs = [
            ref for (ref, avg) in average_coverage_and_refs if avg is None
        ]
        fully_uncovered_refs = [
            ref for (ref, avg) in average_coverage_and_refs if avg == 0.0
        ]
        average_coverage = [
            avg for (_, avg) in average_coverage_and_refs if avg is not None
        ]

        variant_summaries = {}
        for variant in [v for (v, _) in VARIANTS if v != "coverage"]:
            variant_metrics = [
                experiment.variant_metrics[variant] for experiment in self.experiments
            ]
            runs_per_experiment = [len(metric.runs) for metric in variant_metrics]
            failed_runs_metric = [metric.failed_runs() for metric in variant_metrics]
            runs_with_fps_metric = [
                metric.runs_with_false_positives() for metric in variant_metrics
            ]
            runs_with_fns_metric = [
                metric.runs_with_false_negatives() for metric in variant_metrics
            ]
            max_false_positives_metric = [
                metric.false_positives()["max"] for metric in variant_metrics
            ]

            variant_summaries[variant] = {
                "experiments-with-all-successful-runs": len(
                    [1 for failed_runs in failed_runs_metric if len(failed_runs) == 0]
                ),
                "experiments-with-all-failed-runs": len(
                    [
                        failed_runs
                        for (failed_runs, total_runs) in zip(
                            failed_runs_metric, runs_per_experiment
                        )
                        if len(failed_runs) == total_runs
                    ]
                ),
                "experiments-with-at-least-one-successful-run": len(
                    [
                        1
                        for (failed_runs, total_runs) in zip(
                            failed_runs_metric, runs_per_experiment
                        )
                        if len(failed_runs) < total_runs
                    ]
                ),
                "experiments-with-at-least-half-successful-runs": len(
                    [
                        1
                        for (failed_runs, total_runs) in zip(
                            failed_runs_metric, runs_per_experiment
                        )
                        if len(failed_runs) < (total_runs // 2)
                    ]
                ),
                "experiments-with-at-least-one-failed-run": len(
                    [failed_runs for failed_runs in failed_runs_metric if failed_runs]
                ),
                "successful-runs": sum(
                    [
                        total_runs - len(failed_runs)
                        for (failed_runs, total_runs) in zip(
                            failed_runs_metric, runs_per_experiment
                        )
                    ]
                ),
                "failed-runs": sum(
                    [len(failed_runs) for failed_runs in failed_runs_metric]
                ),
                "experiments-with-false-positives-for-all-runs": len(
                    [
                        runs_with_fps
                        for (runs_with_fps, total_runs) in zip(
                            runs_with_fps_metric, runs_per_experiment
                        )
                        if len(runs_with_fps) == total_runs
                    ]
                ),
                "experiments-with-at-least-one-false-positive": len(
                    [
                        runs_with_fps
                        for runs_with_fps in runs_with_fps_metric
                        if runs_with_fps
                    ]
                ),
                "runs-with-false-positives": sum(
                    [len(runs_with_fps) for runs_with_fps in runs_with_fps_metric]
                ),
                "experiments-with-false-negatives": len(
                    [
                        runs_with_fns
                        for runs_with_fns in runs_with_fns_metric
                        if runs_with_fns
                    ]
                ),
                "runs-with-false-negatives": sum(
                    [len(runs_with_fns) for runs_with_fns in runs_with_fns_metric]
                ),
                "max-false-positives": {
                    "min": min(max_false_positives_metric),
                    "avg": statistics.mean(max_false_positives_metric),
                    "stdev": (
                        statistics.stdev(max_false_positives_metric)
                        if len(max_false_positives_metric) > 1
                        else 0.0
                    ),
                    "max": max(max_false_positives_metric),
                },
            }

        return {
            "study": self.study,
            "target": self.target,
            "experiments": len(self.experiments),
            "avg-coverage": {
                "uncoverable-refs": uncoverable_refs,
                "uncoverable-refs-len": len(uncoverable_refs),
                "fully-uncovered-refs": fully_uncovered_refs,
                "fully-uncovered-refs-len": len(fully_uncovered_refs),
                "min": min(average_coverage) if average_coverage else None,
                "avg": statistics.mean(average_coverage) if average_coverage else None,
                "stdev": (
                    (
                        statistics.stdev(average_coverage)
                        if len(average_coverage) > 1
                        else 0.0
                    )
                    if average_coverage
                    else None
                ),
                "max": max(average_coverage) if average_coverage else None,
            },
            "total-runs": sum(
                [
                    len(experiment.variant_metrics["coverage"].runs)
                    for experiment in self.experiments
                ]
            ),
            **variant_summaries,
        }


def get_result_file(experiment_dir_name: str, variant: str) -> str:
    """Get the relative path to the CSV file of a variant in the zipped experiment."""
    return os.path.join(experiment_dir_name, "results", f"results-{variant}.csv")


def get_experiment_results(zipped_experiment_path: str) -> ExperimentResults:
    """Get the results for the whole experiment."""
    experiment_dir_name = os.path.basename(zipped_experiment_path)
    # Strip the tailing ".zip".
    (experiment_dir_name, _) = os.path.splitext(experiment_dir_name)
    (target, experiment, date) = experiment_dir_name.split("__")

    category = None
    for potential_category in CATEGORIES:
        if experiment.startswith(potential_category):
            category = potential_category
            break

    assert category is not None, f"Unknown category: '{experiment}'"
    # Skip the category and the following dash.
    ref = experiment[len(category) + 1 :]

    variant_metrics = {}
    for variant_name, variant_constructor in VARIANTS:
        results_file_path = get_result_file(experiment_dir_name, variant_name)
        unzip_process = subprocess.run(
            ["unzip", "-p", zipped_experiment_path, results_file_path],
            capture_output=True,
            text=True,
            errors="replace",
        )
        assert unzip_process.returncode == 0, (
            f"`unzip` failed for {variant_name}\n"
            f"stdout: '{unzip_process.stdout}'\n"
            f"stderr: '{unzip_process.stderr}'"
        )

        runs: Sequence[RunMetrics] = variant_constructor.from_raw_results(
            unzip_process.stdout
        )

        variant_metrics[variant_name] = VariantMetrics(
            variant=variant_name,
            runs=runs,
        )

    return ExperimentResults(
        date=date,
        target=target,
        category=category,
        ref=ref,
        variant_metrics=variant_metrics,
    )


def main() -> None:
    """Extract the results from a set of zipped experiments and display a summary."""
    parser = argparse.ArgumentParser(
        description="Extract results from a set of zipped experiments."
    )
    parser.add_argument(
        "zipped_experiments",
        metavar="TARGET__VARIANT__DATE.zip",
        help="The path to a `.zip` file containing the results of an experiment.",
        nargs="+",
    )

    args = parser.parse_args()
    assert args is not None

    experiment_results = [
        get_experiment_results(zipped_experiment_path=zipped_experiment_path)
        for zipped_experiment_path in args.zipped_experiments
    ]

    study_results = StudyResults(
        study=experiment_results[0].category,
        target=experiment_results[0].target,
        experiments=experiment_results,
    )

    print(json.dumps(study_results.summary(), indent=4))


if __name__ == "__main__":
    main()
