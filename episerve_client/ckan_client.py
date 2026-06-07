import httpx


class EpisserveCkanClient:
    def __init__(self, ckan_url: str):
        self._base = ckan_url.rstrip("/")

    def show(self, qid: str) -> dict:
        r = httpx.get(
            f"{self._base}/api/3/action/package_show",
            params={"id": qid.lower()},
            timeout=30,
        )
        r.raise_for_status()
        body = r.json()
        if not body.get("success"):
            raise RuntimeError(f"CKAN error: {body.get('error')}")
        return body["result"]
