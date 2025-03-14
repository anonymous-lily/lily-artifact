#!/usr/bin/env python3

"""
Get a set of representative commits from a repository.

This script follows the same method as the proposed evaluation in [1]. Specifically:
    1. It picks the last N commits (by default, all of them);
    2. For every commit, it computes the *size* (# of SLOC affected) and the *spread*
       (# of unique files affected);
    3. It sorts commits into 6 separate buckets:
       - Small, medium, large *size*
       - Small, medium, large *spread*
    4. It selects 9 *sequences* (all possible combinations of the 6 buckets) of K
       commits (with `K = 3` by default).


[1] Arindam Sharma, Cristian Cadar, and Jonathan Metzman. 2024. Effective Fuzzing
    within CI/CD Pipelines (Registered Report). In Proceedings of the 3rd ACM
    International Fuzzing Workshop (FUZZING 2024). Association for Computing Machinery,
    New York, NY, USA, 52–60. https://doi.org/10.1145/3678722.3685534
"""


import argparse
import functools
import hashlib
import multiprocessing
import os
import pickle
import random
import re
import statistics
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

SOURCE_EXTENSIONS = ("c", "cpp", "cc", "h", "hpp", "hh")


@dataclass
class Commit:
    """
    Describe a commit, with its size and spread.

    The size is defined as the number of lines affected by the commit.
    The spread is defined as the number of unique files affected by the commit.
    """

    uid: str
    size: int
    spread: int
    files_affected: list[str]

    def affects_at_least_one_source_file(self) -> bool:
        """Check if the commit affects >= 1 source files."""
        return any(
            any(file_name.endswith(f".{extension}") for extension in SOURCE_EXTENSIONS)
            for file_name in self.files_affected
        )

    def affects_only_files_with_patterns(
        self, exclude_patterns: Optional[list[str]]
    ) -> bool:
        """Check if the commit only affects files which should be excluded."""
        exclude_patterns = exclude_patterns if exclude_patterns is not None else []

        return all(
            any(
                re.search(exclude_pattern, file_name) is not None
                for exclude_pattern in exclude_patterns
            )
            for file_name in self.files_affected
        )

    def __repr__(self) -> str:
        """Represent a commit in string form."""
        return f"{self.uid[:10]} (size: {self.size}, spread: {self.spread})"


@dataclass
class CommitSequence:
    """Describe a sequence of commits."""

    commits: list[Commit]

    def mean_size(self) -> float:
        """Get the mean size of the sequence."""
        return statistics.mean([commit.size for commit in self.commits])

    def mean_spread(self) -> float:
        """Get the mean spread of the sequence."""
        return statistics.mean([commit.spread for commit in self.commits])


@dataclass
class MetricStats:
    """Describe the statistics for a given metric."""

    minimum: float
    mean: float
    standard_deviation: float
    maximum: float


@dataclass
class MetricBuckets:
    """Describe a list of buckets (small, medium, large) of a single metric."""

    stats: MetricStats
    small: list[CommitSequence]
    medium: list[CommitSequence]
    large: list[CommitSequence]


@dataclass
class RepoBuckets:
    """Describe buckets of commits depending on size and spread."""

    size: MetricBuckets
    spread: MetricBuckets


def get_commit_hashes(repo_dir: str, oldest_commit: Optional[str]) -> list[str]:
    """Get all of the commit hashes from a repo's history."""
    history = subprocess.run(
        ["git", "log"], cwd=repo_dir, capture_output=True, text=True, errors="replace"
    ).stdout

    hash_matches = re.findall(r"^commit ([a-f0-9]+)$", history, flags=re.MULTILINE)
    hash_matches = hash_matches[::-1]

    if oldest_commit is not None:
        assert (
            oldest_commit in hash_matches
        ), f"Commit '{oldest_commit}' does not exist in repo history"
        oldest_commit_index = hash_matches.index(oldest_commit)
        return hash_matches[oldest_commit_index:]

    return hash_matches


def get_commit_info(
    commit_hashes: tuple[str, str],
    repo_dir: str,
    skip_merge_commits: bool,
) -> Optional[Commit]:
    """
    Get the size and spread of a given commit.

    The size is defined as the number of lines affected by the commit.
    The spread is defined as the number of unique files affected by the commit.
    """
    (previous_commit_hash, current_commit_hash) = commit_hashes
    commit_summary = subprocess.run(
        ["git", "diff", "--stat", previous_commit_hash, current_commit_hash],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        errors="replace",
    ).stdout

    if skip_merge_commits:
        git_cat_file = subprocess.run(
            ["git", "cat-file", "-p", current_commit_hash],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            errors="replace",
        ).stdout
        if git_cat_file.count("parent") > 1:
            return None

    file_name_matches = re.findall(
        r"^ (.+) +\|",
        commit_summary,
        flags=re.MULTILINE,
    )

    files_match = re.search(
        "([0-9]+) file[s]? changed",
        commit_summary,
    )
    # This is most likely a merge commit.
    if files_match is None:
        return None
    spread = int(files_match.group(1))

    size = 0
    insertions_match = re.search(
        r"([0-9]+) insertion[s]?\(\+\)",
        commit_summary,
    )
    if insertions_match is not None:
        size += int(insertions_match.group(1))

    deletions_match = re.search(
        r"([0-9]+) deletion[s]?\(-\)",
        commit_summary,
    )
    if deletions_match is not None:
        size += int(deletions_match.group(1))

    return Commit(
        uid=current_commit_hash,
        size=size,
        spread=spread,
        files_affected=[file_name.strip() for file_name in file_name_matches],
    )


def create_repo_buckets(sequences: list[CommitSequence], tolerance: int) -> RepoBuckets:
    """Create small, medium and large buckets for the 2 metrics (size and spread)."""
    sizes = [sequence.mean_size() for sequence in sequences]
    spreads = [sequence.mean_spread() for sequence in sequences]

    size_stats = MetricStats(
        minimum=min(sizes),
        mean=statistics.mean(sizes),
        standard_deviation=statistics.stdev(sizes),
        maximum=max(sizes),
    )
    spread_stats = MetricStats(
        minimum=min(spreads),
        mean=statistics.mean(spreads),
        standard_deviation=statistics.stdev(spreads),
        maximum=max(spreads),
    )

    size_buckets = MetricBuckets(
        stats=size_stats,
        small=[],
        medium=[],
        large=[],
    )
    spread_buckets = MetricBuckets(
        stats=spread_stats,
        small=[],
        medium=[],
        large=[],
    )

    # Split the commits down 3 ways for each metric
    sorted_by_size = sorted(sequences, key=lambda c: c.mean_size())
    sorted_by_spread = sorted(sequences, key=lambda c: c.mean_spread())

    third = len(sequences) // 3

    tolerance = tolerance if tolerance <= third else third

    small_size = sorted_by_size[: (third + tolerance)]
    medium_size = sorted_by_size[
        (third - (tolerance // 2)) : (len(sorted_by_size) - third + tolerance // 2)
    ]
    large_size = sorted_by_size[
        (len(sorted_by_size) - third - tolerance) : len(sorted_by_size)
    ]
    small_spread = sorted_by_spread[: (third + tolerance)]
    medium_spread = sorted_by_spread[
        (third - (tolerance // 2)) : (len(sorted_by_spread) - third + tolerance // 2)
    ]
    large_spread = sorted_by_spread[
        (len(sorted_by_spread) - third - tolerance) : len(sorted_by_spread)
    ]

    for sequence in sequences:
        if sequence in small_size:
            size_buckets.small.append(sequence)
        if sequence in medium_size:
            size_buckets.medium.append(sequence)
        if sequence in large_size:
            size_buckets.large.append(sequence)

        if sequence in small_spread:
            spread_buckets.small.append(sequence)
        if sequence in medium_spread:
            spread_buckets.medium.append(sequence)
        if sequence in large_spread:
            spread_buckets.large.append(sequence)

    return RepoBuckets(size=size_buckets, spread=spread_buckets)


def main():
    """Select sequences of K commits of various sizes and spreads."""
    parser = argparse.ArgumentParser(
        description="Select sequences of representative commits."
    )
    parser.add_argument("repo_dir", help="The directory of the Git repository.")
    parser.add_argument(
        "-c",
        "--oldest-commit",
        help="The oldest commit to consider (first commit by default).",
    )
    parser.add_argument(
        "-s",
        "--sequence-size",
        help="The size of the commit sequences (3 by default).",
        default=3,
        type=int,
    )
    parser.add_argument(
        "-t",
        "--tolerance",
        help=(
            "The tolerance when splitting the size and spread into buckets "
            "(0 by default)."
        ),
        default=0,
        type=int,
    )
    parser.add_argument(
        "-S",
        "--source-files-only",
        help="Only pick commits which affect source code files.",
        action="store_true",
    )
    parser.add_argument(
        "-E",
        "--exclude-pattern",
        dest="exclude_patterns",
        help="Exclude commits which only modify files following this pattern.",
        nargs="+",
        metavar="pattern",
    )
    parser.add_argument(
        "-M",
        "--skip-merge-commits",
        help="Do not take merge commits into account.",
        action="store_true",
    )

    args = parser.parse_args()
    assert args is not None

    request_id = hashlib.sha256(
        (args.repo_dir + args.oldest_commit).encode()
    ).hexdigest()
    request_cache_name = f".commits-{request_id}"

    if os.path.isfile(request_cache_name):
        print(f"Found cache file {request_cache_name}, using it", file=sys.stderr)
        with open(request_cache_name, "rb") as cache_file:
            commits = pickle.load(cache_file)
    else:
        print("No cache file found, analyzing Git history", file=sys.stderr)
        hashes = get_commit_hashes(
            repo_dir=args.repo_dir, oldest_commit=args.oldest_commit
        )
        hash_pairs = [(hashes[i], hashes[i + 1]) for i in range(len(hashes) - 1)]

        with multiprocessing.Pool(multiprocessing.cpu_count()) as process_pool:
            commits = process_pool.map(
                functools.partial(
                    get_commit_info,
                    repo_dir=args.repo_dir,
                    skip_merge_commits=args.skip_merge_commits,
                ),
                hash_pairs,
            )
        commits = list(filter(lambda x: x is not None, commits))

        with open(request_cache_name, "wb") as cache_file:
            pickle.dump(commits, cache_file)

    sequences = [
        CommitSequence(commits=commits[n : n + args.sequence_size])
        for n in range(0, len(commits), args.sequence_size)
    ]

    filtered_sequences = []
    for sequence in sequences:
        all_commits_valid = True
        for commit in sequence.commits[1:]:
            if (
                args.source_files_only and not commit.affects_at_least_one_source_file()
            ) or (
                args.exclude_patterns
                and commit.affects_only_files_with_patterns(
                    exclude_patterns=args.exclude_patterns
                )
            ):
                all_commits_valid = False
                break

        if all_commits_valid:
            filtered_sequences.append(sequence)
    nb_filtered_out_sequences = len(sequences) - len(filtered_sequences)
    print(
        f"Filtered out {nb_filtered_out_sequences} sequences "
        f"({nb_filtered_out_sequences/len(sequences) * 100:.2f}%)",
        file=sys.stderr,
    )

    repo_buckets = create_repo_buckets(
        sequences=filtered_sequences, tolerance=args.tolerance
    )

    print(
        f"Analyzed {len(commits)} commits, {len(filtered_sequences)} sequences",
        file=sys.stderr,
    )
    print("Size stats:", file=sys.stderr)
    print(f"  Min: {repo_buckets.size.stats.minimum}", file=sys.stderr)
    print(f"  Max: {repo_buckets.size.stats.maximum}", file=sys.stderr)
    print(f"  Avg: {repo_buckets.size.stats.mean}", file=sys.stderr)
    print(f"  Stdev: {repo_buckets.size.stats.standard_deviation}", file=sys.stderr)
    print("Spread stats:", file=sys.stderr)
    print(f"  Min: {repo_buckets.spread.stats.minimum}", file=sys.stderr)
    print(f"  Max: {repo_buckets.spread.stats.maximum}", file=sys.stderr)
    print(f"  Avg: {repo_buckets.spread.stats.mean}", file=sys.stderr)
    print(f"  Stdev: {repo_buckets.spread.stats.standard_deviation}", file=sys.stderr)

    small_small_sequences = [
        s for s in repo_buckets.size.small if s in repo_buckets.spread.small
    ]
    small_medium_sequences = [
        s for s in repo_buckets.size.small if s in repo_buckets.spread.medium
    ]
    small_large_sequences = [
        s for s in repo_buckets.size.small if s in repo_buckets.spread.large
    ]
    medium_small_sequences = [
        s for s in repo_buckets.size.medium if s in repo_buckets.spread.small
    ]
    medium_medium_sequences = [
        s for s in repo_buckets.size.medium if s in repo_buckets.spread.medium
    ]
    medium_large_sequences = [
        s for s in repo_buckets.size.medium if s in repo_buckets.spread.large
    ]
    large_small_sequences = [
        s for s in repo_buckets.size.large if s in repo_buckets.spread.small
    ]
    large_medium_sequences = [
        s for s in repo_buckets.size.large if s in repo_buckets.spread.medium
    ]
    large_large_sequences = [
        s for s in repo_buckets.size.large if s in repo_buckets.spread.large
    ]

    small_small = random.choice(small_small_sequences)
    small_medium = random.choice(small_medium_sequences)
    small_large = random.choice(small_large_sequences)
    medium_small = random.choice(medium_small_sequences)
    medium_medium = random.choice(medium_medium_sequences)
    medium_large = random.choice(medium_large_sequences)
    large_small = random.choice(large_small_sequences)
    large_medium = random.choice(large_medium_sequences)
    large_large = random.choice(large_large_sequences)

    print(f"Small size, small spread ({len(small_small_sequences)} sequences):")
    print("\n".join([f"  {commit}" for commit in small_small.commits]))
    print(f"Small size, medium spread ({len(small_medium_sequences)} sequences):")
    print("\n".join([f"  {commit}" for commit in small_medium.commits]))
    print(f"Small size, large spread ({len(small_large_sequences)} sequences):")
    print("\n".join([f"  {commit}" for commit in small_large.commits]))
    print(f"Medium size, small spread ({len(medium_small_sequences)} sequences):")
    print("\n".join([f"  {commit}" for commit in medium_small.commits]))
    print(f"Medium size, medium spread ({len(medium_medium_sequences)} sequences):")
    print("\n".join([f"  {commit}" for commit in medium_medium.commits]))
    print(f"Medium size, large spread ({len(medium_large_sequences)} sequences):")
    print("\n".join([f"  {commit}" for commit in medium_large.commits]))
    print(f"Large size, small spread ({len(large_small_sequences)} sequences):")
    print("\n".join([f"  {commit}" for commit in large_small.commits]))
    print(f"Large size, medium spread ({len(large_medium_sequences)} sequences):")
    print("\n".join([f"  {commit}" for commit in large_medium.commits]))
    print(f"Large size, large spread ({len(large_large_sequences)} sequences):")
    print("\n".join([f"  {commit}" for commit in large_large.commits]))


if __name__ == "__main__":
    main()
