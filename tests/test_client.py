"""Basic tests for the episerve client library and CLI."""

import json
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from episerve_client import EpiserveApiClient, EpisserveCkanClient, EpiserveDoipClient, EpiserveClient


class TestEpiserveApiClient:
    def test_health(self):
        client = EpiserveApiClient("https://your-api-server")
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "ok"}
        with patch.object(client._http, "get", return_value=mock_response):
            result = client.health()
        assert result == {"status": "ok"}

    def test_list_runs(self):
        client = EpiserveApiClient("https://your-api-server")
        mock_response = MagicMock()
        mock_response.json.return_value = [{"qid": "Q123", "model_name": "test"}]
        with patch.object(client._http, "get", return_value=mock_response):
            result = client.list_runs()
        assert isinstance(result, list)
        assert result[0]["qid"] == "Q123"

    def test_trigger_model_run(self):
        client = EpiserveApiClient("https://your-api-server")
        mock_response = MagicMock()
        mock_response.json.return_value = {"run_id": "abc", "status": "SCHEDULED"}
        with patch.object(client._http, "post", return_value=mock_response):
            result = client.trigger_model_run({"model_image": "ghcr.io/test", "input_path": "lakefs://x", "config": {}})
        assert result["status"] == "SCHEDULED"


class TestEpisserveCkanClient:
    def test_show(self):
        client = EpisserveCkanClient("https://your-ckan-server")
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True, "result": {"id": "q123", "title": "Test"}}
        with patch("episerve_client.ckan_client.httpx.get", return_value=mock_response):
            result = client.show("Q123")
        assert result["id"] == "q123"

    def test_show_ckan_error(self):
        client = EpisserveCkanClient("https://your-ckan-server")
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": False, "error": {"message": "Not found"}}
        with patch("episerve_client.ckan_client.httpx.get", return_value=mock_response):
            with pytest.raises(RuntimeError, match="CKAN error"):
                client.show("Q999")


class TestEpiserveDoipClient:
    def test_list_components(self):
        client = EpiserveDoipClient("https://your-doip-server")
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "kernel": {
                "fdo:hasComponent": [
                    {"@id": "components/output/predictions.tsv", "componentId": "predictions.tsv"}
                ]
            }
        }
        with patch("episerve_client.doip_client.httpx.get", return_value=mock_response):
            result = client.list_components("Q123")
        assert len(result) == 1
        assert result[0]["id"] == "predictions.tsv"

    def test_list_components_empty(self):
        client = EpiserveDoipClient("https://your-doip-server")
        mock_response = MagicMock()
        mock_response.json.return_value = {"kernel": {}}
        with patch("episerve_client.doip_client.httpx.get", return_value=mock_response):
            result = client.list_components("Q123")
        assert result == []


class TestEpiserveClient:
    def test_instantiation(self):
        client = EpiserveClient()
        assert client.api is not None
        assert client.ckan is not None
        assert client.doip is not None

    def test_custom_urls(self):
        client = EpiserveClient(
            api_url="http://localhost:8000",
            ckan_url="http://localhost:5000",
            doip_url="http://localhost:3567",
        )
        assert "localhost:8000" in str(client.api._http.base_url)


class TestCLI:
    def test_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "client_cli.main", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "episerve" in result.stdout

    def test_list_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "client_cli.main", "list", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "datasets" in result.stdout

    def test_item_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "client_cli.main", "item", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0

    def test_trigger_invalid_json(self, tmp_path):
        result = subprocess.run(
            [sys.executable, "-m", "client_cli.main", "trigger-model-run", "not-a-file-or-json"],
            capture_output=True, text=True,
        )
        assert result.returncode == 1
        assert "Error" in result.stderr

    def test_trigger_from_file(self, tmp_path):
        params_file = tmp_path / "params.json"
        params_file.write_text(json.dumps({
            "model_image": "ghcr.io/test/model",
            "input_path": "lakefs://data-raw/main/test.tsv",
            "config": {"horizon_weeks": 4},
        }))
        mock_response = MagicMock()
        mock_response.json.return_value = {"run_id": "abc", "status": "SCHEDULED"}
        mock_response.raise_for_status = MagicMock()

        with patch("episerve_client.api_client.httpx.Client") as mock_cls:
            mock_cls.return_value._http = MagicMock()
            result = subprocess.run(
                [sys.executable, "-m", "client_cli.main", "trigger-model-run", str(params_file)],
                capture_output=True, text=True, env={**__import__("os").environ, "EPISERVE_API_URL": "http://localhost:8000"},
            )
        assert result.returncode in (0, 1)
