from datetime import date

import httpx


class EpiserveApiClient:
    def __init__(self, base_url: str, api_key: str | None = None):
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._http = httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=30)

    def health(self) -> dict:
        return self._get("/health")

    def list_datasets(self) -> list[dict]:
        return self._get("/datasets")

    def list_models(self) -> list[dict]:
        return self._get("/models")

    def list_runs(self) -> list[dict]:
        return self._get("/model-runs")

    def get_run(self, run_id: str) -> dict:
        """Status and metadata of one model run, by QID."""
        return self._get(f"/model-runs/{run_id}")

    def get_token(self, username: str, password: str) -> dict:
        r = self._http.post("/auth/token", json={"username": username, "password": password})
        r.raise_for_status()
        return r.json()

    def get_token_status(self) -> dict:
        r = self._http.get("/auth/status")
        r.raise_for_status()
        return r.json()

    def trigger_model_run(self, params: dict) -> dict:
        r = self._http.post("/model-runs", json=params)
        r.raise_for_status()
        return r.json()

    # --- benchmarks and leaderboard ---

    def list_benchmarks(self) -> list[dict]:
        """Final benchmarks with their entry counts."""
        return self._get("/benchmarks")

    def list_benchmark_drafts(self) -> list[dict]:
        """Draft benchmarks (needs a token)."""
        return self._get("/benchmarks/drafts")

    def get_benchmark(self, benchmark_id: int) -> dict:
        """One benchmark; a draft needs a token."""
        return self._get(f"/benchmarks/{benchmark_id}")

    def create_benchmark(
        self,
        name: str,
        dataset_qid: str,
        target_column: str,
        date_column: str,
        test_start: str | date,
        test_end: str | date,
        *,
        description: str | None = None,
        filter_column: str | None = None,
        filter_value: str | None = None,
        history_start: str | date | None = None,
        history_end: str | date | None = None,
        input_filename: str | None = None,
    ) -> dict:
        """Create a draft benchmark (needs a token). Dates are ``date`` objects or ``YYYY-MM-DD`` strings."""
        body = {
            "name": name, "dataset_qid": dataset_qid, "target_column": target_column,
            "date_column": date_column, "test_start": test_start, "test_end": test_end,
            "description": description, "filter_column": filter_column, "filter_value": filter_value,
            "history_start": history_start, "history_end": history_end, "input_filename": input_filename,
        }
        return self._send("POST", "/benchmarks", _body(body, drop_none=True))

    def update_benchmark(self, benchmark_id: int, **fields) -> dict:
        """Change fields of a draft; only the given fields are sent and ``None`` clears an optional one."""
        return self._send("PATCH", f"/benchmarks/{benchmark_id}", _body(fields))

    def check_benchmark(self, benchmark_id: int) -> dict:
        """Check a draft against the current data; stores nothing."""
        return self._send("POST", f"/benchmarks/{benchmark_id}/check")

    def finalize_benchmark(self, benchmark_id: int) -> dict:
        """Pin the current lakeFS commit and make the draft final.

        Unlike the web designer this does not compare against the commit of an earlier check.
        """
        return self._send("POST", f"/benchmarks/{benchmark_id}/finalize")

    def copy_benchmark(self, benchmark_id: int) -> dict:
        """Copy a benchmark as a new draft."""
        return self._send("POST", f"/benchmarks/{benchmark_id}/copy")

    def retire_benchmark(self, benchmark_id: int) -> None:
        """Hide a benchmark from the lists."""
        self._send("POST", f"/benchmarks/{benchmark_id}/retire")

    def get_benchmark_run_spec(self, benchmark_id: int) -> dict:
        """Input files, SQL and config suggestion for running a model on a final benchmark."""
        return self._get(f"/benchmarks/{benchmark_id}/run-spec")

    def get_leaderboard(self, benchmark_id: int, rank_by: str = "interval_score", all_runs: bool = False) -> dict:
        """The stored ranking. ``rank_by``: ``mae``, ``rmse``, ``coverage`` or ``interval_score``."""
        return self._get(
            f"/benchmarks/{benchmark_id}/leaderboard", params={"rank_by": rank_by, "all_runs": all_runs}
        )

    def add_benchmark_entry(self, benchmark_id: int, run_qid: str) -> dict:
        """Score a finished model run and add it to the leaderboard (needs a token)."""
        return self._send("POST", f"/benchmarks/{benchmark_id}/entries", {"run_qid": run_qid})

    def remove_benchmark_entry(self, benchmark_id: int, entry_id: int) -> None:
        """Remove an entry (soft); add the run again to recompute it."""
        self._send("DELETE", f"/benchmarks/{benchmark_id}/entries/{entry_id}")

    def _get(self, path: str, params: dict | None = None):
        r = self._http.get(path, params=params)
        r.raise_for_status()
        return r.json()

    def _send(self, method: str, path: str, body: dict | None = None):
        """Send a write request; returns the JSON body, or None for ``204 No Content``."""
        r = self._http.request(method, path, json=body)
        r.raise_for_status()
        return None if r.status_code == 204 else r.json()


def _body(fields: dict, drop_none: bool = False) -> dict:
    """JSON body from ``fields``: dates become ISO strings, ``None`` is dropped or kept as null."""
    return {
        key: value.isoformat() if isinstance(value, date) else value
        for key, value in fields.items()
        if not (drop_none and value is None)
    }
