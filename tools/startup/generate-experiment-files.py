"""
Generate experiment files.

This scripts allows us to generate the Bash experiment files (found under
`experiment-helpers/`) which allow to run any one experiment.

This way of generating these files gives us the ability to define things like arbitrary
commit sequences, out of which all experiments (using 2 commits at a time) will be
generated.

To see an example of the input files to this script, see
`targets/libpng/safe-commits.toml`.

Note that this script has a dependency on `tomlkit`, and should thus be invoked via
`uv` as follows:
```console
uv run --with "tomlkit==0.13.2" generate-experiment-files.py <FILE> ...
```
"""

import argparse
import os
from typing import Any

# Ignore undeclared dependency error. See the global docstring above.
import tomlkit  # noqa: I900

EXPERIMENT_HELPERS_DIR = os.path.join(
    "/root", "artifact", "tools", "experiment-helpers"
)

BASE_EXPERIMENT_FILE_TEMPLATE = "\n".join(
    (
        "#!/usr/bin/env bash",
        "",
        "# `BENCHMARK_*` variables are used by `experiment-helpers/run.sh`.",
        "# shellcheck disable=SC2034",
        "",
        "{comments}",
        "",
        'target="{target}"',
        'prefix="{prefix}"',
        "",
        'previous_commit="{previous_commit}"',
        'previous_commit_harness_patch="{previous_commit_harness_patch}"',
        'current_commit="{current_commit}"',
        'current_commit_harness_patch="{current_commit_harness_patch}"',
        "",
        "BENCHMARK_TARGETS=(",
        (
            '    "$previous_commit_harness_patch $target $previous_commit '
            '$prefix-$previous_commit"'
        ),
        (
            '    "$current_commit_harness_patch $target $current_commit '
            '$prefix-$current_commit"'
        ),
        (
            '    "$current_commit_harness_patch $target $current_commit '
            '$prefix-${{current_commit}}__coverage"'
        ),
        ")",
        'BENCHMARK_NAME="$prefix-{suffix}"',
        'BENCHMARK_PREVIOUS="$prefix-$previous_commit"',
        'BENCHMARK_CURRENT="$prefix-$current_commit"',
        'BENCHMARK_COVERAGE="$prefix-${{current_commit}}__coverage"',
        'BENCHMARK_GROUND_TRUTH="$prefix-$current_commit"',
    )
)


def generate_experiments_from_recipe(recipe: dict[Any, Any], output_dir: str) -> None:
    """Generate a set of experiment files from a given recipe."""
    assert "kind" in recipe
    assert "category" in recipe
    assert "target" in recipe
    assert "prefix" in recipe
    assert "commit-sequences" in recipe

    output_dir = os.path.join(output_dir, recipe["category"], recipe["target"])
    os.makedirs(output_dir)

    for sequence in recipe["commit-sequences"]:
        assert "commits" in sequence

        total_commits = len(sequence["commits"])
        # We need at least 2 commits, since we're doing differential testing.
        assert total_commits >= 2

        for i in range(0, len(sequence["commits"]) - 1):
            previous_commit = sequence["commits"][i]
            current_commit = sequence["commits"][i + 1]
            assert "ref" in previous_commit
            assert "ref" in current_commit

            suffix = current_commit.get("name", current_commit["ref"])

            if recipe["kind"] == "commit":
                assert "size" in sequence
                assert "spread" in sequence

                output = BASE_EXPERIMENT_FILE_TEMPLATE.format(
                    comments="\n".join(
                        (
                            "# Commit sequence info:",
                            "#   Size: {size}",
                            "#   Spread: {spread}",
                            (
                                "#   Commit numbers: {first_index} and {second_index} "
                                "(out of {total_commits})"
                            ),
                        )
                    ).format(
                        size=sequence["size"],
                        spread=sequence["spread"],
                        first_index=(i + 1),
                        second_index=(i + 2),
                        total_commits=total_commits,
                    ),
                    target=recipe["target"],
                    prefix=recipe["prefix"],
                    suffix=suffix,
                    previous_commit=previous_commit["ref"],
                    previous_commit_harness_patch=previous_commit["harness-patch"],
                    current_commit=current_commit["ref"],
                    current_commit_harness_patch=current_commit["harness-patch"],
                )
            elif recipe["kind"] == "release":
                assert "releases" in sequence
                assert "distro" in sequence

                output = BASE_EXPERIMENT_FILE_TEMPLATE.format(
                    comments="\n".join(
                        (
                            "# Release info:",
                            "#   Distribution: {distro}",
                            "#   Releases: {releases}",
                        )
                    ).format(
                        releases=sequence["releases"],
                        distro=sequence["distro"],
                    ),
                    target=recipe["target"],
                    prefix=recipe["prefix"],
                    suffix=suffix,
                    previous_commit=previous_commit["ref"],
                    previous_commit_harness_patch=previous_commit["harness-patch"],
                    current_commit=current_commit["ref"],
                    current_commit_harness_patch=current_commit["harness-patch"],
                )
            else:
                raise AssertionError(f"Invalid experiment kind '{recipe['kind']}'.")

            output_file_name = f"{recipe['prefix']}-{suffix}.sh"
            with open(os.path.join(output_dir, output_file_name), "w") as output_file:
                output_file.write(output)


def main():
    """Generate experiment files for any number of recipes."""
    parser = argparse.ArgumentParser(
        description=("Generate experiment files given a number of recipes.")
    )
    parser.add_argument("recipes", help="The recipe (TOML) file(s) to use.", nargs="+")

    args = parser.parse_args()
    assert args is not None

    for recipe_file_path in args.recipes:
        with open(recipe_file_path, "rb") as recipe_file:
            recipe = tomlkit.parse(recipe_file.read())

        generate_experiments_from_recipe(
            recipe=recipe, output_dir=EXPERIMENT_HELPERS_DIR
        )


if __name__ == "__main__":
    main()
