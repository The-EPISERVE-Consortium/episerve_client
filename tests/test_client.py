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

    def test_get_run(self):
        client = EpiserveApiClient("https://your-api-server")
        with patch.object(client._http, "get", return_value=_respond({"qid": "Q123", "status": "success"})) as get:
            assert client.get_run("Q123")["status"] == "success"
        assert get.call_args.args[0] == "/model-runs/Q123"

    def test_facade_exposes_run_and_token_calls(self):
        client = EpiserveClient()
        with patch.object(client.api, "get_run", return_value={"qid": "Q1"}) as run, \
                patch.object(client.api, "get_token", return_value={"token": "t"}) as token, \
                patch.object(client.api, "get_token_status", return_value={"expires_at": "x"}) as status:
            assert client.get_run("Q1") == {"qid": "Q1"}
            assert client.get_token("u", "p") == {"token": "t"}
            assert client.get_token_status() == {"expires_at": "x"}
        run.assert_called_once_with("Q1")
        token.assert_called_once_with("u", "p")
        status.assert_called_once_with()

    def test_trigger_model_run(self):
        client = EpiserveApiClient("https://your-api-server")
        mock_response = MagicMock()
        mock_response.json.return_value = {"run_id": "abc", "status": "SCHEDULED"}
        with patch.object(client._http, "post", return_value=mock_response):
            result = client.trigger_model_run({"model_image": "ghcr.io/test", "input_path": "lakefs://x", "config": {}})
        assert result["status"] == "SCHEDULED"


def _respond(payload=None, status=200):
    response = MagicMock()
    response.status_code = status
    response.json.return_value = payload
    return response


class TestBenchmarkMethods:
    def setup_method(self):
        self.client = EpiserveApiClient("https://your-api-server", "tok")

    def test_reads_use_get(self):
        with patch.object(self.client._http, "get", return_value=_respond([{"id": 1}])) as get:
            assert self.client.list_benchmarks() == [{"id": 1}]
            self.client.list_benchmark_drafts()
            self.client.get_benchmark(4)
            self.client.get_benchmark_run_spec(4)
        assert [c.args[0] for c in get.call_args_list] == [
            "/benchmarks", "/benchmarks/drafts", "/benchmarks/4", "/benchmarks/4/run-spec"]

    def test_leaderboard_passes_ranking_options(self):
        with patch.object(self.client._http, "get", return_value=_respond({"entries": []})) as get:
            self.client.get_leaderboard(4, "mae", True)
        assert get.call_args.args[0] == "/benchmarks/4/leaderboard"
        assert get.call_args.kwargs["params"] == {"rank_by": "mae", "all_runs": True}

    def test_create_sends_iso_dates_and_omits_unset_options(self):
        from datetime import date
        with patch.object(self.client._http, "request", return_value=_respond({"id": 9}, 201)) as req:
            result = self.client.create_benchmark(
                "Flu", "Q1", "v", "datum", date(2026, 4, 1), "2026-09-30", filter_column="typ", filter_value="A")
        assert result == {"id": 9}
        method, path = req.call_args.args
        assert (method, path) == ("POST", "/benchmarks")
        assert req.call_args.kwargs["json"] == {
            "name": "Flu", "dataset_qid": "Q1", "target_column": "v", "date_column": "datum",
            "test_start": "2026-04-01", "test_end": "2026-09-30", "filter_column": "typ", "filter_value": "A"}

    def test_update_sends_only_given_fields_and_keeps_none_to_clear(self):
        with patch.object(self.client._http, "request", return_value=_respond({"id": 9})) as req:
            self.client.update_benchmark(9, name="New", filter_column=None)
        assert req.call_args.args == ("PATCH", "/benchmarks/9")
        assert req.call_args.kwargs["json"] == {"name": "New", "filter_column": None}

    def test_lifecycle_calls(self):
        with patch.object(self.client._http, "request", return_value=_respond({"ok": True})) as req:
            self.client.check_benchmark(2)
            self.client.finalize_benchmark(2)
            self.client.copy_benchmark(2)
            self.client.add_benchmark_entry(2, "Q55")
        assert [c.args for c in req.call_args_list] == [
            ("POST", "/benchmarks/2/check"), ("POST", "/benchmarks/2/finalize"),
            ("POST", "/benchmarks/2/copy"), ("POST", "/benchmarks/2/entries")]
        assert req.call_args.kwargs["json"] == {"run_qid": "Q55"}

    def test_204_calls_return_none(self):
        with patch.object(self.client._http, "request", return_value=_respond(None, 204)) as req:
            assert self.client.retire_benchmark(2) is None
            assert self.client.remove_benchmark_entry(2, 7) is None
        assert [c.args for c in req.call_args_list] == [
            ("POST", "/benchmarks/2/retire"), ("DELETE", "/benchmarks/2/entries/7")]

    def test_errors_are_raised(self):
        import httpx
        response = _respond({"detail": "no"}, 422)
        response.raise_for_status.side_effect = httpx.HTTPStatusError("bad", request=MagicMock(), response=response)
        with patch.object(self.client._http, "request", return_value=response):
            with pytest.raises(httpx.HTTPStatusError):
                self.client.finalize_benchmark(2)

    def test_facade_delegates(self):
        client = EpiserveClient()
        with patch.object(client.api, "get_leaderboard", return_value={"entries": []}) as call:
            assert client.get_leaderboard(3, "rmse") == {"entries": []}
        call.assert_called_once_with(3, "rmse", False)


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
        assert result[0]["id"] == "output/predictions.tsv"

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

    def test_benchmark_help_lists_subcommands(self):
        result = subprocess.run(
            [sys.executable, "-m", "client_cli.main", "benchmark", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        for name in ("create", "finalize", "leaderboard", "add-entry", "remove-entry", "run-spec"):
            assert name in result.stdout

    def test_benchmark_commands_call_the_client(self, monkeypatch, capsys):
        from client_cli import main as cli

        calls = []

        class Fake:
            def __getattr__(self, name):
                return lambda *a, **k: calls.append((name, a, k)) or {"ok": name}

        monkeypatch.setattr(cli, "_api", lambda args: Fake())
        for argv, expected in (
            (["benchmark", "list"], ("list_benchmarks", (), {})),
            (["benchmark", "leaderboard", "3", "--rank-by", "mae", "--all-runs"],
             ("get_leaderboard", (3, "mae", True), {})),
            (["benchmark", "add-entry", "3", "Q9"], ("add_benchmark_entry", (3, "Q9"), {})),
            (["benchmark", "update", "3", '{"name": "x"}'], ("update_benchmark", (3,), {"name": "x"})),
            (["benchmark", "create", '{"name": "x", "dataset_qid": "Q1"}'],
             ("create_benchmark", (), {"name": "x", "dataset_qid": "Q1"})),
            (["benchmark", "retire", "3"], ("retire_benchmark", (3,), {})),
            (["benchmark", "remove-entry", "3", "7"], ("remove_benchmark_entry", (3, 7), {})),
        ):
            calls.clear()
            monkeypatch.setattr(sys, "argv", ["episerve-client", *argv])
            cli.main()
            assert calls == [expected]

    def test_run_show_calls_the_client(self, monkeypatch):
        from client_cli import main as cli

        seen = []

        class Fake:
            def get_run(self, run_id):
                seen.append(run_id)
                return {"qid": run_id}

        monkeypatch.setattr(cli, "_api", lambda args: Fake())
        monkeypatch.setattr(sys, "argv", ["episerve-client", "run", "show", "Q77"])
        cli.main()
        assert seen == ["Q77"]

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
