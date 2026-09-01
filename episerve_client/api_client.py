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

    def _get(self, path: str):
        r = self._http.get(path)
        r.raise_for_status()
        return r.json()
