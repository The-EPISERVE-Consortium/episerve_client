from .api_client import EpiserveApiClient
from .ckan_client import EpisserveCkanClient
from .doip_client import EpiserveDoipClient
from .version import __version__


class EpiserveClient:
    """Unified client for the EPISERVE platform.

    Wraps the API server, CKAN catalog, and DOIP server into a single object.

    Example::

        from episerve_client import EpiserveClient
        client = EpiserveClient()
        print(client.list_runs())
        print(client.item_show("Q1748526042817"))
        client.item_download("Q1748526042817", "output/predictions.tsv", "predictions.tsv")
    """

    def __init__(
        self,
        api_url: str = "https://your-api-server",
        ckan_url: str = "https://your-ckan-server",
        doip_url: str = "https://your-doip-server",
        api_key: str | None = None,
    ):
        self.api = EpiserveApiClient(api_url, api_key)
        self.ckan = EpisserveCkanClient(ckan_url)
        self.doip = EpiserveDoipClient(doip_url)

    # --- API server ---

    def health(self) -> dict:
        return self.api.health()

    def list_datasets(self) -> list[dict]:
        return self.api.list_datasets()

    def list_models(self) -> list[dict]:
        return self.api.list_models()

    def list_runs(self) -> list[dict]:
        return self.api.list_runs()

    def get_run(self, run_id: str) -> dict:
        return self.api.get_run(run_id)

    def trigger_model_run(self, params: dict) -> dict:
        return self.api.trigger_model_run(params)

    def get_token(self, username: str, password: str) -> dict:
        return self.api.get_token(username, password)

    def get_token_status(self) -> dict:
        return self.api.get_token_status()

    # --- benchmarks and leaderboard ---

    def list_benchmarks(self) -> list[dict]:
        return self.api.list_benchmarks()

    def list_benchmark_drafts(self) -> list[dict]:
        return self.api.list_benchmark_drafts()

    def get_benchmark(self, benchmark_id: int) -> dict:
        return self.api.get_benchmark(benchmark_id)

    def create_benchmark(self, *args, **kwargs) -> dict:
        return self.api.create_benchmark(*args, **kwargs)

    def update_benchmark(self, benchmark_id: int, **fields) -> dict:
        return self.api.update_benchmark(benchmark_id, **fields)

    def check_benchmark(self, benchmark_id: int) -> dict:
        return self.api.check_benchmark(benchmark_id)

    def finalize_benchmark(self, benchmark_id: int) -> dict:
        return self.api.finalize_benchmark(benchmark_id)

    def copy_benchmark(self, benchmark_id: int) -> dict:
        return self.api.copy_benchmark(benchmark_id)

    def retire_benchmark(self, benchmark_id: int) -> None:
        self.api.retire_benchmark(benchmark_id)

    def get_benchmark_run_spec(self, benchmark_id: int) -> dict:
        return self.api.get_benchmark_run_spec(benchmark_id)

    def get_leaderboard(self, benchmark_id: int, rank_by: str = "interval_score", all_runs: bool = False) -> dict:
        return self.api.get_leaderboard(benchmark_id, rank_by, all_runs)

    def add_benchmark_entry(self, benchmark_id: int, run_qid: str) -> dict:
        return self.api.add_benchmark_entry(benchmark_id, run_qid)

    def remove_benchmark_entry(self, benchmark_id: int, entry_id: int) -> None:
        self.api.remove_benchmark_entry(benchmark_id, entry_id)

    # --- CKAN ---

    def item_show(self, qid: str) -> dict:
        return self.ckan.show(qid)

    # --- DOIP ---

    def item_list_components(self, qid: str) -> list[dict]:
        return self.doip.list_components(qid)

    def item_download(self, qid: str, component_id: str, output_path: str | None = None) -> None:
        chunks = self.doip.download(qid, component_id)
        if output_path:
            with open(output_path, "wb") as f:
                for chunk in chunks:
                    f.write(chunk)
        else:
            import sys
            for chunk in chunks:
                sys.stdout.buffer.write(chunk)


__all__ = ["__version__", "EpiserveClient", "EpiserveApiClient", "EpisserveCkanClient", "EpiserveDoipClient"]
