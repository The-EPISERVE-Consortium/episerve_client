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
episerve list datasets-raw
episerve list datasets
episerve list models
episerve list runs
```

### Item details and components

```bash
# Show full metadata for any item by QID
episerve item show Q1748526042817

# List FDO components stored in the DOIP server
episerve item list-components Q1748526042817

# Download a specific component to a file
episerve item download Q1748526042817 components/output/predictions.tsv -o predictions.tsv

# Stream a component to stdout
episerve item download Q1748526042817 components/output/predictions.tsv
```

### Trigger a model run

Pass parameters as a JSON file or inline JSON string:

```bash
episerve trigger-model-run params.json
episerve trigger-model-run '{"model_image": "ghcr.io/the-episerve-consortium/model__prediction__grippeweb__baseline-nullmodel", "input_path": "lakefs://data-raw/main/incidence/influenza/RKI__grippeweb.tsv", "config": {"horizon_weeks": 4, "n_reference_weeks": 4}}'
```

Example `params.json`:

```json
{
  "model_image": "ghcr.io/the-episerve-consortium/model__prediction__grippeweb__baseline-nullmodel",
  "model_tag": "latest",
  "input_path": "lakefs://data-raw/main/incidence/influenza/RKI__grippeweb.tsv",
  "config": {
    "horizon_weeks": 4,
    "n_reference_weeks": 4
  }
}
```

Returns `202` immediately with a `run_id`. Track the run with:

```bash
episerve item show <run_id>
```

### Global flags

```
--api-url   Override EPISERVE_API_URL
--ckan-url  Override EPISERVE_CKAN_URL
--doip-url  Override EPISERVE_DOIP_URL
--api-key   Override EPISERVE_API_KEY
--raw       Compact JSON output (no indentation)
```

## Python library usage

```python
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

# Download
client.item_download("Q1748526042817", "components/output/predictions.tsv", "predictions.tsv")

# Trigger
result = client.trigger_model_run({
    "model_image": "ghcr.io/the-episerve-consortium/model__prediction__grippeweb__baseline-nullmodel",
    "input_path": "lakefs://data-raw/main/incidence/influenza/RKI__grippeweb.tsv",
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
