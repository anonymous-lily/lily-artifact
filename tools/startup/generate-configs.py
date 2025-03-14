"""
Generate the ROSA configurations for all of the targets.

This script allows us to modify the configurations uniformly, ensuring that the same
settings are in use for all targets.

Note that this script has a dependency on `tomlkit`, and should thus be invoked via
`uv` as follows:
```console
uv run --with "tomlkit==0.13.2" generate-configs.py
```
"""

import copy
import os
from functools import partial
from typing import Any, Optional

# Ignore undeclared dependency error. See the global docstring above.
import tomlkit  # noqa: I900

TARGETS_DIR = os.path.join("/root", "artifact", "targets")
TARGET_SETTINGS_FILE = os.path.join(TARGETS_DIR, "targets.toml")
SEED_DIRS = os.path.join("/root", "artifact", "seeds")
AFL_FUZZ = os.path.join("/root", "rosa", "fuzzers", "aflpp", "aflpp", "afl-fuzz")
with open(TARGET_SETTINGS_FILE, "rb") as target_settings_file:
    TARGET_SETTINGS = tomlkit.parse(target_settings_file.read())

DEFAULT_CONFIG = {
    "output_dir": "/root/scratch/rosa-out",
    "cluster_formation_criterion": "edges-only",
    "cluster_formation_edge_tolerance": 0,
    "cluster_formation_syscall_tolerance": 0,
    "cluster_selection_criterion": "syscalls-only",
    "oracle_criterion": "syscalls-only",
    "cluster_formation_distance_metric": {
        "kind": "hamming",
    },
    "cluster_selection_distance_metric": {
        "kind": "hamming",
    },
    "oracle": {
        "kind": "comp-min-max",
    },
    "oracle_distance_metric": {
        "kind": "hamming",
    },
    "phase_one": {
        "seconds": 3,
    },
    "fuzzers": [],
}

DEFAULT_FUZZER_CONFIG: dict[Any, Any] = {
    "backend": {
        "kind": "afl++",
        "name": None,
        "mode": "standard",
        "is_main": None,
        "afl_fuzz": AFL_FUZZ,
        "input_dir": None,
        "output_dir": "/root/scratch/fuzzer-out",
        "target": [],
        "input": None,
        "extra_args": [],
        "env": {
            "AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES": "1",
            "AFL_SKIP_CPUFREQ": "1",
            "AFL_IGNORE_SEED_PROBLEMS": "1",
            "AFL_FAST_CAL": "1",
            "AFL_SYNC_TIME": "1",
            "AFL_FINAL_SYNC": "1",
            "AFL_TESTCACHE_SIZE": "1024",
            "AFL_MAX_DET_EXTRAS": "1000",
        },
    }
}


def generate_fuzzer_config(
    name: str,
    target: list[str],
    is_main: bool,
    input_kind: str,
    seed_dir: str,
    dictionaries: list[str],
    power_schedule: str,
    mode: str,
    disable_trim: bool = False,
    cmplog: bool = True,
    extra_args: Optional[list[str]] = None,
    extra_env: Optional[dict[Any, Any]] = None,
) -> dict[Any, Any]:
    """
    Generate a single fuzzer configuration.

    Some options are hardcoded here, as we know we want an AFL++ backend in standard
    mode.
    """
    extra_args = extra_args or []
    extra_env = extra_env or {}
    config = copy.deepcopy(DEFAULT_FUZZER_CONFIG)

    dictionary_args = []
    for dictionary in dictionaries:
        dictionary_args += ["-x", dictionary]

    config["backend"]["name"] = name
    config["backend"]["target"] = target
    config["backend"]["is_main"] = is_main
    config["backend"]["input"] = input_kind
    config["backend"]["input_dir"] = seed_dir
    config["backend"]["extra_args"] += [
        "-u",
        *dictionary_args,
        "-p",
        power_schedule,
    ]

    if cmplog:
        config["backend"]["extra_args"] += ["-c", "0"]

    if mode == "ascii":
        config["backend"]["extra_args"] += ["-a", "ascii"]
        config["backend"]["env"]["AFL_NO_ARITH"] = "1"
    elif mode == "binary":
        config["backend"]["extra_args"] += ["-a", "binary"]

    if disable_trim:
        config["backend"]["env"]["AFL_DISABLE_TRIM"] = "1"

    config["backend"]["extra_args"] += extra_args
    config["backend"]["env"].update(extra_env)

    return config


def generate_fuzzer_configs(
    target: list[str],
    seed_dir: str,
    dictionary: str,
    mode: str,
    input_kind: str,
) -> list[dict[Any, Any]]:
    """
    Generate a list of fuzzer configurations.

    This defines the main "template" used for all targets in the evaluation.
    """
    config = partial(
        generate_fuzzer_config,
        target=target,
        input_kind=input_kind,
        seed_dir=seed_dir,
    )

    (dictionary_dir, _) = os.path.split(dictionary)
    autodict = os.path.join(dictionary_dir, "autodict.dict")

    return [
        config(
            name="main",
            is_main=False,
            dictionaries=[dictionary, autodict],
            power_schedule="explore",
            mode=mode,
            disable_trim=True,
            cmplog=True,
            extra_args=["-l", "2A"],
        ),
        config(
            name="fast",
            is_main=False,
            dictionaries=[dictionary, autodict],
            power_schedule="fast",
            mode=mode,
            cmplog=True,
            extra_args=["-l", "2A"],
        ),
        config(
            name="explore",
            is_main=False,
            dictionaries=[dictionary, autodict],
            power_schedule="explore",
            mode=mode,
            cmplog=True,
            extra_args=["-l", "2A"],
        ),
    ]


for target in TARGET_SETTINGS:
    target_info = TARGET_SETTINGS[target]
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["fuzzers"] = generate_fuzzer_configs(
        target=[
            os.path.join("__TARGET_DIR__", "original", target_info["program"]),
            *target_info["arguments"],
        ],
        mode=target_info["mode"],
        seed_dir=os.path.join(SEED_DIRS, target_info["seeds"]),
        dictionary=os.path.join("__TARGET_DIR__", target_info["dictionary"]),
        input_kind=target_info["input"],
    )

    with open(
        os.path.join(TARGETS_DIR, target, "config.toml.template"), "w"
    ) as config_file:
        # Break the string in two to avoid vim parsing it as a legitimate modeline.
        config_file.write("# vim" + ": set syntax=toml:\n")  # noqa: ISC003
        config_file.write(tomlkit.dumps(config))
