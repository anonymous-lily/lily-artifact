# Artifact for the paper "Not In My Git Yard: Catching Backdoors at Commit and Release Time"

This artifact allows for the reproduction of the results shown in the paper, as well as the
execution of arbitrary experiments with Lily and its variants on different versions of software.

The intended use is to build a Docker image and run all experiments inside a dedicated Docker
container.

## Notation

In the context of code snippets, `[host] $` refers to a shell on the _host_ machine (i.e., your
machine), while `[container] $` refers to a shell _inside of a running Docker container_.

## Installing the Docker image

To build the image, simply run the `build.sh` script:

```text
[host] $ ./build.sh
```

## Using the Docker image

To run a Docker container using the installed Docker image, use the `run.sh` script:

```text
[host] $ ./run.sh
```

The container should start and you should be greeted with a shell.

The first thing you should do is run the sanity check script, which will run a backdoor detection
campaign (1 run, 10 seconds per run) on the vsFTPd target program (specifically the infected 2.3.4
version):

```text
[container] $ /root/artifact/run-sanity-check.sh
```

The experiment infrastructure should then run the experiment, and you should see the following
steps:

1. Building the official and infected versions for version number `2.3.4` of vsFTPd (as well as
   another version for coverage measurements);
2. Running the evaluation (including the "calibration run" for the "previous" version) for all tool
   variants;
3. Evaluating the results of the experiment.

When done, the sanity check script should have stored the evaluation result summary under
`/root/evaluation/sanity-check/results.json`:

```text
[container] $ cat /root/evaluation/sanity-check/results.json
...
```

### Running the experiments from the paper

The recipes for all experiments from the paper can be found under
`/root/artifact/tools/experiment-helpers/`, and can be run with
`/root/artifact/tools/experiment-helpers/run.sh`. For instance, running the same vsFTPd 2.3.4
infected experiment as the sanity check script but with 5 minutes (i.e., 300 seconds) per run for a
total of 10 runs can be achieved with the following command:

```text
[container] $ RUNS=10 SECONDS_PER_RUN=300 /root/artifact/tools/experiment-helpers/run.sh \
    /root/artifact/tools/experiment-helpers/simple-commit/vsftpd__simple-commit-2.3.4-infected.sh
```

In general, the following experiment recipe categories are available:

- `simple-commit`: backdoor detection experiments, where a single backdoor is injected in a single
  version of a target program, for each target program.
- `simple-releases`: backdoor detection experiments, where a single backdoor is injected in multiple
  release versions of a target program, for each target program.
- `safe-commits`: false-positive filtering experiments, where we use pairs of backdoor-free commit
  versions of a target program, for each target program.
- `safe-code-commits`: false-positive filtering experiments, where we use pairs of backdoor-free
  commit versions _specifically altering code files_ of a target program, for each target program.
- `safe-releases`: false-positive filtering experiments, where we use pairs of backdoor-free release
  versions of a target program, for each target program.

## Uninstalling the Docker image

To uninstall the Docker image, remove the version which was installed:

```text
[host] $ docker rmi lily-artifact:$(cat VERSION)
```

## Repository outline

### Scripts for artifact evaluation

- `run-sanity-check.sh`: script to run a sanity check inside the Docker container. See
  [_Using the Docker image_](#using-the-docker-image).

### Fuzzer data

- `dictionaries`: directory containing the dictionaries used by the fuzzer.
- `seeds`: directory containing the minimized seeds used by the fuzzer.

## Target program data

- `targets`: directory containing the target programs/PUTs used in the evaluation of the paper.
- `targets.toml`: data file containing information on how to invoke each target program, used
  throughout the toolchain.
  - `original`/`<version number>`: directory containing the actual source code of the target program
    (via submodule where possible).
  - `patches`: various patches to the target program (depending on the version), to install a
    harness, a backdoor or a backdoor with a ground-truth marker.
  - `backdoor-triggers`: directory containing backdoor-triggering inputs for the target (used in the
    evaluation of attack models by poisoning the representative input corpus).
  - `build.sh`: script containing commands to build the target.
  - `safe-commits.toml`: data file containing the representative commits used in the evaluation of
    the paper. Generated with data from `tools/analysis/get-representative-commits.py`.
  - `safe-code-commits.toml`: data file containing the representative code commits used in the
    evaluation of the paper. Generated with data from
    `tools/analysis/get-representative-commits.py`.
  - `safe-releases.toml`: data file containing the representative releases used in the evaluation of
    the paper. Generated with data from `tools/analysis/get-representative-commits.py`.

## Tools

- `tools`: directory containing the toolchain of the artifact. This is the infrastructure which
  allows us to create, run, evaluate and analyze experiments.
  - `common.sh`: script containing common functions used throughout the toolchain.
  - `startup`: tools used during Docker container startup (e.g., to generate experiment recipes).
    - `startup.sh`: script orchestrating all startup-time actions.
    - `generate-configs.py`: script to generate configuration files for every target program. This
      ensures that the settings used in the configuration files are uniform for all target programs,
      and that any changes are propagated to all configuration files.
    - `generate-experiment-files.py`: script to generate the experiment recipes used in the paper.
      See `experiment-helpers/run.sh` below.
  - `analysis`: tools pertaining to the analysis of a target repository or the results of an
    evaluation.
    - `extract-results.py`: script to extract results from a zipped experiment file. Experiments are
      packaged in compressed form (see `experiment-helpers/run.sh` below) and contain all raw data
      generated in the experiment. This script extracts a summary of the results and outputs it to
      `stdout` in JSON format.
    - `get-representative-commits.py`: script to get a set of representative commits from a given
      Git repository using a technique inspired by the state of the art.
  - `evaluation`: tools pertaining to the evaluation of the paper (i.e., which help carry out the
    actual experiments).
    - `build-target.sh`: script to build a single version of a specific target program (with
      possibility of applying patches).
    - `collect-coverage.sh`: script to run all fuzzer-generated inputs through the target program
      and collect coverage information.
    - `run-benchmark.py`: script to run a specific benchmark for all tool variants present in the
      paper.
    - `evaluate-benchmark.py`: script to evaluate a specific benchmark (i.e., the result of
      `run-benchmark.py` above), producing detailed results for all tool variants present in the
      paper.
    - `run-naive-diff.sh`: script to run the NaiveDiff baseline from the paper, given the inputs
      generated by the fuzzer and two versions of a target program.
  - `experiment-helpers`: recipes for the specific experiments used in the paper.
    - `run.sh`: script to run a single experiment recipe. This script is fed an experiment recipe
      (described below) and runs it for a specific duration and a certain number of times (specified
      by the `SECONDS_PER_RUN` and `RUNS` environment variables respectively). When done, if the
      `PACKAGE_EXPERIMENT` environment variable is set to `1`, this script packages the raw
      experiment data in a zip file.
    - `<recipe category>`: directories containing different experiment recipes, in the form of Bash
      scripts. These recipes describe which target program to use, which version to use for the two
      versions of the PUT, what patches to apply and so on.

### Repository metadata & Docker data

- `AUTHORS`: the names and email addresses of the authors (anonymized).
- `IMAGE`: the name of the Docker image (used during building).
- `VERSION`: the version to tag the Docker image with (used during building).
- `build.sh`: build the Docker image (using `IMAGE` and `VERSION`).
- `run.sh`: run a Docker container with the built image (using `IMAGE` and `VERSION`).
- `Dockerfile`: the recipe for the Docker image.
