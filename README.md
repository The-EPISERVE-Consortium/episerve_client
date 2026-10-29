# episerve_client

Python client library and standalone CLI for the EPISERVE epidemiological surveillance platform.

## Download the CLI binary

Pre-built binaries are published with every [GitHub Release](../../releases/latest).

## Configuration

Create a `.env` file in the directory where you run the CLI:

```env
EPISERVE_API_URL=https://my-api-server
EPISERVE_CKAN_URL=https://my-ckan-server
EPISERVE_DOIP_URL=https://my-doip-server
EPISERVE_API_KEY=
```

The `.env` file is loaded automatically. You can also set these as environment variables or pass them as CLI flags.

Priority: `CLI flag > environment variable > .env > built-in default`

## CLI usage

### Health check

```bash
episerve health
```

### List items

```bash
episerve list datasets
episerve list models
episerve list runs
```

### Model run status

```bash
episerve run show Q1748526042817     # status and metadata of one run via the API
```

### Item details and components

```bash
# Show full metadata for any item by QID
episerve item show Q1748526042817

# List FDO components stored in the DOIP server
episerve item list-components Q1748526042817

# Download a specific component to a file
# (the component id is what `item list-components` prints: the FDO @id with
#  the leading `components/` stripped)
episerve item download Q1748526042817 output/predictions.tsv -o predictions.tsv

# Stream a component to stdout
episerve item download Q1748526042817 output/predictions.tsv
```

### Check a config before a run

`check-config` checks a model's `config` against the parameters its model card
declares (types, ranges, required and unknown keys) and starts nothing. It
prints `valid`, the problems a run would be refused with, and the config with
the defaults filled in; the exit code is 1 when the config is invalid.

```bash
episerve check-config model__prediction__generic__timesfm '{"history_length": 52, "prediction_length": 4}'
episerve check-config Q7611536028271 config.json
```

### Validate a model card

`validate` checks a JSON document against a platform spec of
[`episerve_specs`](https://github.com/The-EPISERVE-Consortium/episerve_specs) on
the API server, by default a model's `fdo.json` against `model-card`. It prints
`valid` and the issues (errors and warnings, each with its path in the
document); the exit code is 1 when there are errors.

```bash
episerve validate fdo.json
episerve validate fdo.json --spec model-card --spec-version 1
```

### Trigger a model run

Pass parameters as a JSON file or inline JSON string:

```bash
episerve trigger-model-run params.json
episerve trigger-model-run '{"model_image": "ghcr.io/the-episerve-consortium/model__prediction__grippeweb__baseline-nullmodel", "input_data_files": [["https://doip.episerve.zib.de/doip/retrieve/Q3274128860531/GrippeWeb_Daten_des_Wochenberichts.parquet", "input.parquet"]], "config": {"horizon_weeks": 4, "n_reference_weeks": 4}}'
```

Example `params.json`:

```json
{
  "model_image": "ghcr.io/the-episerve-consortium/model__prediction__grippeweb__baseline-nullmodel",
  "model_tag": "latest",
  "input_data_files": [
    ["https://doip.episerve.zib.de/doip/retrieve/Q3274128860531/GrippeWeb_Daten_des_Wochenberichts.parquet", "input.parquet"]
  ],
  "config": {
    "horizon_weeks": 4,
    "n_reference_weeks": 4
  }
}
```

`input_data_files` is a list of `[source_uri, target_filename]` pairs; the
source is a `lakefs://` URI or a DOIP retrieve URL. `data_transformation_sql`
(optional) is a parallel list of DuckDB SQL filters run against a table `df`.

Returns `202` immediately with a `run_id`. Track the run with:

```bash
episerve item show <run_id>
```

### Benchmarks and leaderboards

Reading needs no token; creating, changing, finalizing and adding runs need the daily token (`episerve login`).

```bash
episerve benchmark list                       # final benchmarks with entry counts
episerve benchmark show 3
episerve benchmark leaderboard 3 --rank-by mae --all-runs
episerve benchmark run-spec 3                 # input URL (pinned commit), SQL, config for a model run

# design one: create a draft, check it, then finalize (pins the current lakeFS commit)
episerve benchmark create '{"name": "Influenza A+B 2026", "dataset_qid": "Q9493814122238",
  "target_column": "viruslast_normalisiert", "date_column": "datum",
  "filter_column": "typ", "filter_value": "Influenza A+B",
  "test_start": "2026-04-01", "test_end": "2026-09-30"}'
episerve benchmark check 3
episerve benchmark finalize 3

episerve benchmark update 3 '{"test_end": "2026-08-31"}'   # drafts only; null clears an optional field
episerve benchmark copy 3                     # copy as a new draft
episerve benchmark retire 3
episerve benchmark drafts

# after a run made from the benchmark has finished and CKAN knows it
episerve benchmark add-entry 3 Q1788513584728
episerve benchmark remove-entry 3 12
```

`create` accepts `name`, `dataset_qid`, `target_column`, `date_column`, `test_start`, `test_end` and the optional `description`, `filter_column`, `filter_value`, `history_start`, `history_end`, `input_filename`. Unlike the web designer, `finalize` does not refuse when the data changed since your `check`; it pins the lakeFS head at that moment.

### Version and update check

Released binaries are stamped with their git tag at build time (the `Stamp version` step of the build workflow writes `episerve_client/version.py`), so the client knows its own version:

```bash
episerve --cli-version        # alias: --version
episerve-client 0.1.13
```

The version goes to stdout, the update status to stderr. Exit codes: `0` up to date (or a development build), `1` a newer release exists, `2` the lookup failed (the version is still printed).

```bash
if episerve --cli-version; then echo current; fi     # usable as a script or CI gate
```

When started interactively, the client also checks at most once a day whether a newer release exists and prints a notice on stderr, never stdout. Prereleases (`rc` tags) are never offered. The check is skipped for development builds (`0.0.0.dev0`, source checkouts), in CI and when stderr is not a terminal.

```bash
episerve --no-update-check health          # skip the startup check for this run
EPISERVE_NO_CLIENT_UPDATE_CHECK=1 episerve health
```

It queries the repository's git ref endpoint (the one `git ls-remote` uses): no token, no GitHub API rate limit. It is best-effort: no network, a timeout or an unparseable response all count as "no update" and never affect the command you ran. The result is cached for 24 hours in `~/.cache/episerve/client-update-check.json` (`%LOCALAPPDATA%\episerve\` on Windows). In Python, `episerve_client.__version__` holds the version.

To cut a release, push a tag such as `v0.1.14`: the workflow builds the three binaries stamped `0.1.14` and publishes them as a GitHub release.

### Global flags

These work before or after the command (`episerve --raw list runs` and `episerve list runs --raw` are the same):

```
--api-url          Override EPISERVE_API_URL
--ckan-url         Override EPISERVE_CKAN_URL
--doip-url         Override EPISERVE_DOIP_URL
--api-key          Override EPISERVE_API_KEY
--raw              Compact JSON output (no indentation)
--no-update-check  Skip the automatic update check
```

### Help

`episerve -h` lists the commands, examples and environment variables. `episerve <command> -h` (for example `episerve list -h` or `episerve benchmark create -h`) shows what the command does, its arguments, whether it needs a login, the JSON fields it accepts and examples.

## Python library usage

```python
import json

from episerve_client import EpiserveClient

client = EpiserveClient(
    api_url="https://my-api-server",
    ckan_url="https://my-ckan-server",
    doip_url="https://my-doip-server",
)

# List
runs = client.list_runs()
datasets = client.list_datasets()
models = client.list_models()

# Item detail
details = client.item_show("Q1748526042817")
components = client.item_list_components("Q1748526042817")

# Download (component id as printed by item_list_components)
client.item_download("Q1748526042817", "output/predictions.tsv", "predictions.tsv")

# Benchmarks
boards = client.list_benchmarks()
board = client.get_leaderboard(3, rank_by="mae")
draft = client.create_benchmark("Flu", "Q9493814122238", "viruslast_normalisiert", "datum",
                                "2026-04-01", "2026-09-30", filter_column="typ", filter_value="Influenza A+B")
client.check_benchmark(draft["id"])
client.finalize_benchmark(draft["id"])
spec = client.get_benchmark_run_spec(draft["id"])   # same shape as a model-run request
client.add_benchmark_entry(draft["id"], "Q1788513584728")

run = client.get_run("Q1748526042817")

# Check a config, validate a model card
client.check_model_config("model__prediction__generic__timesfm", {"history_length": 52, "prediction_length": 4})
client.validate(json.load(open("fdo.json")))          # spec model-card by default
client.list_schemas()                                 # specs, versions, schema URLs

# Trigger
result = client.trigger_model_run({
    "model_image": "ghcr.io/the-episerve-consortium/model__prediction__grippeweb__baseline-nullmodel",
    "input_data_files": [
        ["https://doip.episerve.zib.de/doip/retrieve/Q3274128860531/GrippeWeb_Daten_des_Wochenberichts.parquet", "input.parquet"],
    ],
    "config": {"horizon_weeks": 4, "n_reference_weeks": 4},
})
print(result["run_id"])
```

The library also exposes individual clients if you only need one backend:

```python
from episerve_client import EpiserveApiClient, EpisserveCkanClient, EpiserveDoipClient
```

## Install from source

```bash
pip install -r requirements.txt
```

## Running tests

```bash
pytest tests/ -v
```

## Building the binary locally

```bash
pip install pyinstaller
pip install -r requirements.txt
pyinstaller --onefile --name episerve client_cli/main.py
# binary is at dist/episerve
```
