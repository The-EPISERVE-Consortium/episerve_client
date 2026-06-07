import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _print_banner() -> None:
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.SetConsoleMode(
            ctypes.windll.kernel32.GetStdHandle(-11), 7
        )
    CYAN = "\033[36m"
    RESET = "\033[0m"
    banner = (
        "\n"
        "██████  ████▄   ██   ████  ██████  ████▄   ██   ██  ██████\n"
        "██▄▄    ██▄▄█▀  ██  ▄▄▄██  ██▄▄    ██▄▄█▀   ██ ██   ██▄▄  \n"
        "██████  ██      ██  ████▀  ██████  ██  ▀█    ▀█▀    ██████\n"
        "\n"
        "        Epidemiological Surveillance Platform\n"
    )
    print(CYAN + banner + RESET, file=sys.stderr)

import httpx

from episerve_client import EpiserveApiClient, EpisserveCkanClient, EpiserveDoipClient


# --- helpers ---

def _out(data, raw: bool) -> None:
    print(json.dumps(data) if raw else json.dumps(data, indent=2, ensure_ascii=False))


def _api(args) -> EpiserveApiClient:
    url = args.api_url or os.environ.get("EPISERVE_API_URL", "https://your-api-server")
    key = args.api_key or os.environ.get("EPISERVE_API_KEY") or None
    print(f"  → {url}", file=sys.stderr)
    return EpiserveApiClient(url, key)


def _ckan(args) -> EpisserveCkanClient:
    url = args.ckan_url or os.environ.get("EPISERVE_CKAN_URL", "https://your-ckan-server")
    print(f"  → {url}", file=sys.stderr)
    return EpisserveCkanClient(url)


def _doip(args) -> EpiserveDoipClient:
    url = args.doip_url or os.environ.get("EPISERVE_DOIP_URL", "https://your-doip-server")
    print(f"  → {url}", file=sys.stderr)
    return EpiserveDoipClient(url)


# --- command handlers ---

def cmd_health(args):
    _out(_api(args).health(), args.raw)


def cmd_list(args):
    client = _api(args)
    result = {
        "datasets-raw": client.list_raw_datasets,
        "datasets":     client.list_datasets,
        "models":       client.list_models,
        "runs":         client.list_runs,
    }[args.type]()
    _out(result, args.raw)


def cmd_item_show(args):
    _out(_ckan(args).show(args.qid), args.raw)


def cmd_item_list_components(args):
    _out(_doip(args).list_components(args.qid), args.raw)


def cmd_item_download(args):
    client = _doip(args)
    if args.output:
        path = Path(args.output)
        with path.open("wb") as f:
            for chunk in client.download(args.qid, args.component_id):
                f.write(chunk)
        print(f"Saved to {path}", file=sys.stderr)
    else:
        for chunk in client.download(args.qid, args.component_id):
            sys.stdout.buffer.write(chunk)


def cmd_trigger_model_run(args):
    raw = args.params
    try:
        with open(raw) as f:
            params = json.load(f)
    except (FileNotFoundError, IsADirectoryError, OSError):
        try:
            params = json.loads(raw)
        except json.JSONDecodeError:
            print(f"Error: '{raw}' is neither a valid file path nor valid JSON.", file=sys.stderr)
            sys.exit(1)
    _out(_api(args).trigger_model_run(params), args.raw)


# --- parser ---

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="episerve-client",
        description="CLI for the EPISERVE epidemiological surveillance platform.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  episerve-client health
  episerve-client list runs
  episerve-client list datasets
  episerve-client item show Q1748526042817
  episerve-client item list-components Q1748526042817
  episerve-client item download Q1748526042817 components/output/predictions.tsv -o predictions.tsv
""",
    )
    parser.add_argument("--api-url",  metavar="URL", help="set the API server URL (controls all list/trigger commands)")
    parser.add_argument("--ckan-url", metavar="URL", help="set the CKAN URL (controls item show)")
    parser.add_argument("--doip-url", metavar="URL", help="set the DOIP server URL (controls item list-components and download)")
    parser.add_argument("--api-key",  metavar="KEY", help="set the bearer token for authenticated API requests")
    parser.add_argument("--raw", action="store_true", help="Compact JSON output (no indentation)")

    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    # health
    sub.add_parser("health", help="Check API server health")

    # list
    list_p = sub.add_parser("list", help="List items of a given type")
    list_p.add_argument(
        "type",
        choices=["datasets-raw", "datasets", "models", "runs"],
        metavar="<type>",
        help="datasets-raw | datasets | models | runs",
    )

    # item
    item_p = sub.add_parser("item", help="Interact with a specific item by QID")
    item_sub = item_p.add_subparsers(dest="item_command", required=True, metavar="<subcommand>")

    show_p = item_sub.add_parser("show", help="Show item details from CKAN")
    show_p.add_argument("qid", metavar="<QID>")

    lc_p = item_sub.add_parser("list-components", help="List FDO components via DOIP")
    lc_p.add_argument("qid", metavar="<QID>")

    dl_p = item_sub.add_parser("download", help="Download a component via DOIP")
    dl_p.add_argument("qid", metavar="<QID>")
    dl_p.add_argument("component_id", metavar="<component-id>",
                      help="e.g. components/output/predictions.tsv")
    dl_p.add_argument("--output", "-o", metavar="<file>",
                      help="Output file path (default: stdout)")

    # trigger-model-run
    trigger_p = sub.add_parser("trigger-model-run", help="Trigger a model run via the API")
    trigger_p.add_argument(
        "params",
        metavar="<params>",
        help="Path to a JSON file or an inline JSON string with the model run parameters",
    )

    return parser


def main():
    _print_banner()
    parser = _build_parser()
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(0)
    args = parser.parse_args()

    dispatch = {
        "health":             cmd_health,
        "list":               cmd_list,
        "trigger-model-run":  cmd_trigger_model_run,
    }

    try:
        if args.command == "item":
            {
                "show":             cmd_item_show,
                "list-components":  cmd_item_list_components,
                "download":         cmd_item_download,
            }[args.item_command](args)
        else:
            dispatch[args.command](args)
    except httpx.HTTPStatusError as exc:
        print(f"HTTP {exc.response.status_code}: {exc.response.text}", file=sys.stderr)
        sys.exit(1)
    except httpx.RequestError as exc:
        print(f"Connection error: {exc}", file=sys.stderr)
        print(
            "\nHint: create a .env file in the current directory with:\n"
            "  EPISERVE_API_URL=https://...\n"
            "  EPISERVE_CKAN_URL=https://...\n"
            "  EPISERVE_DOIP_URL=https://...\n"
            "  EPISERVE_API_KEY=",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
