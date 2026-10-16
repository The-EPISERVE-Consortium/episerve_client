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
    url = args.api_url or os.environ.get("EPISERVE_API_URL", "https://my-api-server")
    key = args.api_key or os.environ.get("EPISERVE_API_KEY") or None
    print(f"  → {url}", file=sys.stderr)
    return EpiserveApiClient(url, key)


def _ckan(args) -> EpisserveCkanClient:
    url = args.ckan_url or os.environ.get("EPISERVE_CKAN_URL", "https://my-ckan-server")
    print(f"  → {url}", file=sys.stderr)
    return EpisserveCkanClient(url)


def _doip(args) -> EpiserveDoipClient:
    url = args.doip_url or os.environ.get("EPISERVE_DOIP_URL", "https://my-doip-server")
    print(f"  → {url}", file=sys.stderr)
    return EpiserveDoipClient(url)


# --- command handlers ---

def cmd_login(args):
    if getattr(args, "login_command", None) == "status":
        cmd_login_status(args)
        return

    username = args.username or os.environ.get("EPISERVE_USERNAME")
    password = args.password or os.environ.get("EPISERVE_PASSWORD")

    if not username or not password:
        print(
            "Authenticate and save the daily token to .env:\n"
            "  episerve-client login -u <username> -p <password>\n"
            "\n"
            "Or set EPISERVE_USERNAME and EPISERVE_PASSWORD in .env to skip the flags.\n"
            "\n"
            "Check whether the stored token is still valid:\n"
            "  episerve-client login status",
            file=sys.stderr,
        )
        sys.exit(0)

    url = args.api_url or os.environ.get("EPISERVE_API_URL", "https://my-api-server")
    result = EpiserveApiClient(url).get_token(username, password)
    token = result["token"]
    expires_at = result["expires_at"]

    env_path = Path(".env")
    if env_path.exists():
        lines = env_path.read_text().splitlines()
        new_lines, updated = [], False
        for line in lines:
            if line.startswith("EPISERVE_API_KEY="):
                new_lines.append(f"EPISERVE_API_KEY={token}")
                updated = True
            else:
                new_lines.append(line)
        if not updated:
            new_lines.append(f"EPISERVE_API_KEY={token}")
        env_path.write_text("\n".join(new_lines) + "\n")
    else:
        env_path.write_text(f"EPISERVE_API_KEY={token}\n")

    print(f"Token saved to .env (valid until {expires_at})", file=sys.stderr)


def cmd_login_status(args):
    result = _api(args).get_token_status()
    print(f"Token is valid. Expires at: {result['expires_at']} UTC", file=sys.stderr)


def cmd_health(args):
    _out(_api(args).health(), args.raw)


def cmd_list(args):
    if args.type is None:
        args._list_parser.print_help(sys.stderr)
        sys.exit(0)
    client = _api(args)
    result = {
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


def _load_json(raw: str):
    """Parse ``raw`` as the path of a JSON file or as inline JSON; exit with an error if it is neither."""
    try:
        with open(raw) as f:
            return json.load(f)
    except (FileNotFoundError, IsADirectoryError, OSError):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            print(f"Error: '{raw}' is neither a valid file path nor valid JSON.", file=sys.stderr)
            sys.exit(1)


def cmd_trigger_model_run(args):
    _out(_api(args).trigger_model_run(_load_json(args.params)), args.raw)


def cmd_run_show(args):
    _out(_api(args).get_run(args.run_id), args.raw)


def cmd_benchmark(args):
    if args.benchmark_command is None:
        args._benchmark_parser.print_help(sys.stderr)
        sys.exit(0)
    client = _api(args)
    command = args.benchmark_command
    if command == "list":
        result = client.list_benchmarks()
    elif command == "drafts":
        result = client.list_benchmark_drafts()
    elif command == "show":
        result = client.get_benchmark(args.id)
    elif command == "create":
        result = client.create_benchmark(**_load_json(args.params))
    elif command == "update":
        result = client.update_benchmark(args.id, **_load_json(args.params))
    elif command == "check":
        result = client.check_benchmark(args.id)
    elif command == "finalize":
        result = client.finalize_benchmark(args.id)
    elif command == "copy":
        result = client.copy_benchmark(args.id)
    elif command == "retire":
        client.retire_benchmark(args.id)
        print(f"Benchmark {args.id} retired.", file=sys.stderr)
        return
    elif command == "run-spec":
        result = client.get_benchmark_run_spec(args.id)
    elif command == "leaderboard":
        result = client.get_leaderboard(args.id, args.rank_by, args.all_runs)
    elif command == "add-entry":
        result = client.add_benchmark_entry(args.id, args.run_qid)
    else:  # remove-entry
        client.remove_benchmark_entry(args.id, args.entry_id)
        print(f"Entry {args.entry_id} removed from benchmark {args.id}.", file=sys.stderr)
        return
    _out(result, args.raw)


# --- parser ---

def _print_short_help(parser: argparse.ArgumentParser) -> None:
    print(parser.description + "\n", file=sys.stderr)
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            print("positional arguments:", file=sys.stderr)
            print(f"  {action.metavar}", file=sys.stderr)
            for choice in action._choices_actions:
                print(f"    {choice.dest:<20} {choice.help}", file=sys.stderr)
            break
    print("\noptions:", file=sys.stderr)
    print("  -h, --help           show extended help and exit", file=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="episerve-client",
        description="CLI for the EPISERVE epidemiological surveillance platform.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
        epilog="""
examples:
  episerve-client login
  episerve-client login status
  episerve-client health
  episerve-client list runs
  episerve-client list datasets
  episerve-client benchmark list
  episerve-client benchmark leaderboard 3 --rank-by mae
  episerve-client run show Q1748526042817
  episerve-client item show Q1748526042817
  episerve-client item list-components Q1748526042817
  episerve-client item download Q1748526042817 output/predictions.tsv -o predictions.tsv
""",
    )
    parser.add_argument("-h", "--help", action="help", default=argparse.SUPPRESS,
                        help="show extended help and exit")
    parser.add_argument("--api-url",  metavar="URL", help="set the API server URL (controls all list/trigger commands)")
    parser.add_argument("--ckan-url", metavar="URL", help="set the CKAN URL (controls item show)")
    parser.add_argument("--doip-url", metavar="URL", help="set the DOIP server URL (controls item list-components and download)")
    parser.add_argument("--api-key",  metavar="KEY", help="set the bearer token for authenticated API requests")
    parser.add_argument("--raw", action="store_true", help="Compact JSON output (no indentation)")

    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    # login
    login_p = sub.add_parser("login", help="Authenticate and manage tokens")
    login_p.add_argument("--username", "-u", metavar="<username>")
    login_p.add_argument("--password", "-p", metavar="<password>")
    login_sub = login_p.add_subparsers(dest="login_command", metavar="<subcommand>")
    login_sub.add_parser("status", help="Check whether the current token is valid and show expiry")

    # health
    sub.add_parser("health", help="Check API server health")

    # list
    list_p = sub.add_parser("list", help="List items of a given type")
    list_p.add_argument(
        "type",
        choices=["datasets", "models", "runs"],
        metavar="<type>",
        nargs="?",
        default=None,
        help="datasets | models | runs",
    )
    list_p.set_defaults(_list_parser=list_p)

    # item
    item_p = sub.add_parser("item", help="Interact with a specific item by QID")
    item_sub = item_p.add_subparsers(dest="item_command", required=False, metavar="<subcommand>")
    item_p.set_defaults(_item_parser=item_p)

    show_p = item_sub.add_parser("show", help="Show item details from CKAN")
    show_p.add_argument("qid", metavar="<QID>")

    lc_p = item_sub.add_parser("list-components", help="List FDO components via DOIP")
    lc_p.add_argument("qid", metavar="<QID>")

    dl_p = item_sub.add_parser("download", help="Download a component via DOIP")
    dl_p.add_argument("qid", metavar="<QID>")
    dl_p.add_argument("component_id", metavar="<component-id>",
                      help="component id as printed by 'item list-components', "
                           "e.g. output/predictions.tsv")
    dl_p.add_argument("--output", "-o", metavar="<file>",
                      help="Output file path (default: stdout)")

    # trigger-model-run
    trigger_p = sub.add_parser("trigger-model-run", help="Trigger a model run via the API")
    trigger_p.add_argument(
        "params",
        metavar="<params>",
        help="Path to a JSON file or an inline JSON string with the model run parameters",
    )

    # run
    run_p = sub.add_parser("run", help="Inspect a model run")
    run_sub = run_p.add_subparsers(dest="run_command", required=False, metavar="<subcommand>")
    run_p.set_defaults(_run_parser=run_p)
    run_show_p = run_sub.add_parser("show", help="Show the status of one model run via the API")
    run_show_p.add_argument("run_id", metavar="<run-QID>")

    # benchmark
    bench_p = sub.add_parser("benchmark", help="Design benchmarks, read leaderboards, add runs")
    bench_sub = bench_p.add_subparsers(dest="benchmark_command", required=False, metavar="<subcommand>")
    bench_p.set_defaults(_benchmark_parser=bench_p)

    def with_id(name, help_):
        p = bench_sub.add_parser(name, help=help_)
        p.add_argument("id", type=int, metavar="<benchmark-id>")
        return p

    bench_sub.add_parser("list", help="List final benchmarks")
    bench_sub.add_parser("drafts", help="List draft benchmarks (needs a token)")
    with_id("show", "Show one benchmark")
    create_p = bench_sub.add_parser("create", help="Create a draft from a JSON file or inline JSON (needs a token)")
    create_p.add_argument("params", metavar="<params>")
    update_p = with_id("update", "Change fields of a draft from a JSON file or inline JSON (needs a token)")
    update_p.add_argument("params", metavar="<params>")
    with_id("check", "Check a draft against the current data")
    with_id("finalize", "Pin the current data commit and make a draft final")
    with_id("copy", "Copy a benchmark as a new draft")
    with_id("retire", "Hide a benchmark from the lists")
    with_id("run-spec", "Show the input files, SQL and config to run a model on a final benchmark")
    lb_p = with_id("leaderboard", "Show the ranked leaderboard")
    lb_p.add_argument("--rank-by", choices=["mae", "rmse", "coverage", "interval_score"],
                      default="interval_score")
    lb_p.add_argument("--all-runs", action="store_true", help="Every entry instead of each model's best")
    add_p = with_id("add-entry", "Score a finished model run and add it to the leaderboard")
    add_p.add_argument("run_qid", metavar="<run-QID>")
    rm_p = with_id("remove-entry", "Remove an entry from the leaderboard")
    rm_p.add_argument("entry_id", type=int, metavar="<entry-id>")

    return parser


def main():
    _print_banner()
    parser = _build_parser()
    if len(sys.argv) == 1:
        _print_short_help(parser)
        sys.exit(0)
    args = parser.parse_args()

    dispatch = {
        "login":              cmd_login,
        "health":             cmd_health,
        "list":               cmd_list,
        "trigger-model-run":  cmd_trigger_model_run,
        "benchmark":          cmd_benchmark,
    }

    try:
        if args.command == "run":
            if args.run_command is None:
                args._run_parser.print_help(sys.stderr)
                sys.exit(0)
            cmd_run_show(args)
        elif args.command == "item":
            if args.item_command is None:
                args._item_parser.print_help(sys.stderr)
                sys.exit(0)
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
            "  EPISERVE_API_URL=https://my-api-server\n"
            "  EPISERVE_CKAN_URL=https://my-ckan-server\n"
            "  EPISERVE_DOIP_URL=https://my-doip-server\n"
            "  EPISERVE_API_KEY=",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
