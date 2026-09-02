from .api_client import EpiserveApiClient
from .ckan_client import EpisserveCkanClient
from .doip_client import EpiserveDoipClient


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

    def trigger_model_run(self, params: dict) -> dict:
        return self.api.trigger_model_run(params)

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


__all__ = ["EpiserveClient", "EpiserveApiClient", "EpisserveCkanClient", "EpiserveDoipClient"]
