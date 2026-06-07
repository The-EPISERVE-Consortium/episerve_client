from typing import Iterator

import httpx


class EpiserveDoipClient:
    def __init__(self, doip_url: str):
        self._base = doip_url.rstrip("/")

    def list_components(self, qid: str) -> list[dict]:
        r = httpx.get(f"{self._base}/doip/retrieve/{qid}", timeout=30)
        r.raise_for_status()
        raw = r.json().get("kernel", {}).get("fdo:hasComponent", [])
        return [
            {
                "id": comp.get("@id", "").removeprefix("components/"),
                "mediaType": comp.get("mediaType", ""),
            }
            for comp in raw
        ]

    def download(self, qid: str, component_id: str) -> Iterator[bytes]:
        with httpx.stream("GET", f"{self._base}/doip/retrieve/{qid}/{component_id}", timeout=120) as r:
            r.raise_for_status()
            yield from r.iter_bytes(chunk_size=65536)
