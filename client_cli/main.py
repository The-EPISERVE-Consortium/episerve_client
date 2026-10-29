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

from client_cli import update_check
from episerve_client import EpiserveApiClient, EpisserveCkanClient, EpiserveDoipClient
from episerve_client.version import __version__


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


# --- update check ---

def _maybe_announce_update(args) -> None:
    """Print an update notice on stderr when a newer release exists.

    Best-effort and silent on every failure, so it never affects the command's
    output or exit code.
    """
    if not update_check.should_check(no_update_check=args.no_update_check):
        return
    info = update_check.check_for_update(__version__)
    if info:
        print(update_check.format_notice(info), file=sys.stderr)


def _run_cli_version() -> int:
    """Handle ``--cli-version``: print the version, then report on updates.

    The version goes to stdout so it can be captured; the update status goes to
    stderr. This queries the network directly (bypassing the cache) and reports
    failures rather than staying silent.

    Returns:
        int: 0 when up to date (or a development build), 1 when a newer release
        exists, 2 when the lookup itself failed.
    """
    print(f"episerve-client {__version__}")
    if update_check._is_placeholder(update_check.parse_version(__version__)):
        print("No update check was performed: this is a development build.", file=sys.stderr)
        return 0
    try:
        info = update_check.check_explicitly(__version__)
    except Exception:
        print(f"Cannot reach {update_check.HOST} to check for updates.", file=sys.stderr)
        return 2
    if info:
        print(update_check.format_notice(info), file=sys.stderr)
        return 1
    print("This is the latest release.", file=sys.stderr)
    return 0


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
            "  episerve-client login -u <email> -p <password>\n"
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


def cmd_check_config(args):
    result = _api(args).check_model_config(args.model, _load_json(args.config))
    _out(result, args.raw)
    if result.get("valid") is False:
        sys.exit(1)


def cmd_validate(args):
    result = _api(args).validate(_load_json(args.document), args.spec, args.spec_version)
    _out(result, args.raw)
    if not result.get("valid"):
        sys.exit(1)


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


_ENV_HELP = """\
environment (read from the shell or from ./.env; flags win over both):
  EPISERVE_API_URL                  API server        (--api-url)
  EPISERVE_CKAN_URL                 CKAN catalog      (--ckan-url)
  EPISERVE_DOIP_URL                 DOIP server       (--doip-url)
  EPISERVE_API_KEY                  daily token       (--api-key; 'login' saves it)
  EPISERVE_USERNAME / _PASSWORD     used by 'login' when -u/-p are not given
  EPISERVE_NO_CLIENT_UPDATE_CHECK=1 skip the automatic update check
"""

_LOGIN_NOTE = "requires a token: run 'episerve-client login' first (the token is valid for one day)."


def _add_global_options(target: argparse.ArgumentParser, *, top: bool) -> None:
    """Add the options shared by every command.

    On subcommands the defaults are suppressed so a value given before the command is not overwritten,
    which makes the options work both before and after the command name.
    """
    group = target.add_argument_group(
        "global options" if top else "global options (also accepted before the command)"
    )
    extra = {} if top else {"default": argparse.SUPPRESS}
    group.add_argument("--api-url", metavar="URL", help="API server URL (default: $EPISERVE_API_URL)", **extra)
    group.add_argument("--ckan-url", metavar="URL",
                       help="CKAN URL, used by 'item show' (default: $EPISERVE_CKAN_URL)", **extra)
    group.add_argument("--doip-url", metavar="URL",
                       help="DOIP server URL, used by 'item list-components' and 'item download' "
                            "(default: $EPISERVE_DOIP_URL)", **extra)
    group.add_argument("--api-key", metavar="KEY",
                       help="bearer token for commands that need a login (default: $EPISERVE_API_KEY)", **extra)
    group.add_argument("--raw", action="store_true", help="compact JSON output, no indentation", **extra)
    group.add_argument("--no-update-check", action="store_true",
                       help=f"skip the automatic update check (also {update_check.ENV_OPT_OUT}=1)", **extra)


def _command(subparsers, name: str, help_: str, *, usage: str, description: str,
             examples: str = "", notes: str = "") -> argparse.ArgumentParser:
    """Add a subcommand with a usage line, description, notes, examples and the global options."""
    epilog = ""
    if notes:
        epilog += notes.rstrip() + "\n\n"
    if examples:
        epilog += "examples:\n" + "".join(f"  {line}\n" for line in examples.strip().splitlines())
    parser = subparsers.add_parser(
        name, help=help_, usage=f"episerve-client [global options] {usage}", description=description,
        epilog=epilog or None, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_global_options(parser, top=False)
    return parser


def _subcommands(parser: argparse.ArgumentParser, dest: str):
    return parser.add_subparsers(dest=dest, required=False, metavar="<subcommand>", title="subcommands")


_BENCHMARK_FIELDS = """\
JSON fields:
  required   name, dataset_qid, target_column, date_column, test_start, test_end   (dates: YYYY-MM-DD)
  optional   description, filters, covariates, history_start, history_end, input_filename
  - filters: equality filters that together select a single series, e.g.
             [{"column": "Bundesland_id", "value": "5"}, {"column": "Altersgruppe", "value": "35-59"}]
             (filter_column/filter_value still work for one filter)
  - covariates: further data sources whose columns are added to the model input, e.g.
             [{"name": "wetter", "dataset_qid": "Q...", "date_column": "datum", "columns": ["temp"],
               "filters": [], "aggregation": "mean"}]   (aggregation: mean | sum | last)
  - history_end: empty = the last observation before test_start
  - input_filename: name the model sees (default input.parquet)
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="episerve-client",
        usage="episerve-client [global options] <command> [<args>]",
        description="CLI for the EPISERVE epidemiological surveillance platform.\n"
                    "Run 'episerve-client <command> -h' for the details of a command.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
        epilog="""examples:
  episerve-client login
  episerve-client health
  episerve-client list runs
  episerve-client run show Q1748526042817
  episerve-client benchmark leaderboard 3 --rank-by mae
  episerve-client item download Q1748526042817 output/predictions.tsv -o predictions.tsv
  episerve-client --cli-version

""" + _ENV_HELP,
    )
    parser.add_argument("-h", "--help", action="help", default=argparse.SUPPRESS,
                        help="show this help and exit")
    parser.add_argument("--cli-version", "--version", dest="cli_version", action="store_true",
                        help="print this client's version, check whether a newer release exists and exit "
                             "(exit codes: 0 up to date, 1 update available, 2 check failed)")
    _add_global_options(parser, top=True)

    sub = parser.add_subparsers(dest="command", required=False, metavar="<command>", title="commands")

    # login
    login_p = _command(
        sub, "login", "Authenticate and manage tokens", usage="login [-u USER] [-p PASSWORD] | login status",
        description="Log in to the API server and save the daily token as EPISERVE_API_KEY in ./.env.\n"
                    "Commands that change data (trigger-model-run, benchmark create/finalize/...) need it.",
        examples="episerve-client login -u alice -p secret\nepiserve-client login status",
        notes="Without -u/-p the values EPISERVE_USERNAME and EPISERVE_PASSWORD are used.",
    )
    login_p.add_argument("--username", "-u", metavar="<email>", help="email address of your account")
    login_p.add_argument("--password", "-p", metavar="<password>", help="password")
    login_sub = _subcommands(login_p, "login_command")
    _command(login_sub, "status", "Check whether the current token is valid and show expiry",
             usage="login status", description="Check the token in EPISERVE_API_KEY and show when it expires.")

    # health
    _command(sub, "health", "Check API server health", usage="health",
             description="Ask the API server whether it is up. Prints {\"status\": \"ok\"}.")

    # list
    list_p = _command(
        sub, "list", "List datasets, models or model runs", usage="list <type>",
        description="List items from the EPISERVE API server as JSON.\n\n"
                    "types:\n"
                    "  datasets   processed datasets in the catalog (QID, name, description, DOIP link, ...)\n"
                    "  models     registered forecast models (docker image and tag, description, ...)\n"
                    "  runs       all model runs with status, timestamps and input/output files",
        notes="see also:\n"
              "  benchmark list     final benchmarks (episerve-client benchmark -h)\n"
              "  run show <QID>     one model run\n"
              "  item show <QID>    the full catalog record of any item",
        examples="episerve-client list runs\n"
                 "episerve-client --raw list datasets | jq '.[].qid'\n"
                 "episerve-client list models --api-url http://localhost:8000",
    )
    list_p.add_argument("type", choices=["datasets", "models", "runs"], metavar="<type>", nargs="?",
                        default=None, help="datasets | models | runs")
    list_p.set_defaults(_list_parser=list_p)

    # item
    item_p = _command(
        sub, "item", "Show an item or download its files by QID", usage="item <subcommand> <QID> ...",
        description="Look at any catalog item (dataset, model or model run) by its QID, e.g. Q1748526042817.\n"
                    "'show' reads the CKAN record; 'list-components' and 'download' use the DOIP server.",
        examples="episerve-client item show Q1748526042817\n"
                 "episerve-client item list-components Q1748526042817\n"
                 "episerve-client item download Q1748526042817 output/predictions.tsv -o predictions.tsv",
    )
    item_sub = _subcommands(item_p, "item_command")
    item_p.set_defaults(_item_parser=item_p)

    show_p = _command(item_sub, "show", "Show item details from CKAN", usage="item show <QID>",
                      description="Print the CKAN record of an item as JSON (needs --ckan-url).")
    show_p.add_argument("qid", metavar="<QID>", help="item id, e.g. Q1748526042817")

    lc_p = _command(item_sub, "list-components", "List FDO components via DOIP",
                    usage="item list-components <QID>",
                    description="List the files (components) of an item. Use the printed ids with 'item download'.")
    lc_p.add_argument("qid", metavar="<QID>", help="item id")

    dl_p = _command(
        item_sub, "download", "Download a component via DOIP", usage="item download <QID> <component-id> [-o FILE]",
        description="Download one file of an item from the DOIP server. Without -o the bytes go to stdout.",
        examples="episerve-client item download Q1748526042817 output/predictions.tsv -o predictions.tsv\n"
                 "episerve-client item download Q1748526042817 output/predictions.tsv | head",
    )
    dl_p.add_argument("qid", metavar="<QID>", help="item id")
    dl_p.add_argument("component_id", metavar="<component-id>",
                      help="component id as printed by 'item list-components', e.g. output/predictions.tsv")
    dl_p.add_argument("--output", "-o", metavar="<file>", help="output file path (default: stdout)")

    # trigger-model-run
    trigger_p = _command(
        sub, "trigger-model-run", "Trigger a model run via the API", usage="trigger-model-run <params>",
        description="Start a model run. <params> is the path of a JSON file or an inline JSON string.\n"
                    "Returns at once (202) with a run_id; follow it with 'run show <run_id>'.",
        notes="JSON fields:\n"
              "  model_image             docker image, e.g. ghcr.io/the-episerve-consortium/model__prediction__...\n"
              "  model_tag               image tag (default latest)\n"
              "  input_data_files        list of [source_uri, target_filename] pairs (lakefs:// or DOIP URL)\n"
              "  config                  the model's own parameters, e.g. {\"horizon_weeks\": 4}\n"
              "  data_transformation_sql optional list, one DuckDB filter per input, run on a table 'df'\n\n"
              + _LOGIN_NOTE,
        examples="episerve-client trigger-model-run params.json\n"
                 "episerve-client trigger-model-run '{\"model_image\": \"ghcr.io/...\", "
                 "\"input_data_files\": [[\"https://...\", \"input.parquet\"]], \"config\": {}}'\n"
                 "episerve-client benchmark run-spec 3     # a ready-made start for a benchmark run",
    )
    trigger_p.add_argument("params", metavar="<params>", help="path to a JSON file, or an inline JSON string")

    # check-config
    cc_p = _command(
        sub, "check-config", "Check a run config against a model's card, without starting a run",
        usage="check-config <model> <config>",
        description="Check a model's config (the 'config' of trigger-model-run) against the parameters its\n"
                    "model card declares: types, ranges, required and unknown keys. Nothing is started.\n"
                    "Prints valid, the problems (the ones trigger-model-run would be refused with) and the\n"
                    "config with the defaults filled in. Exit code 1 when the config is invalid.",
        notes="'list models' shows each model's parameters. valid is null when the card declares none.",
        examples="episerve-client check-config model__prediction__generic__timesfm "
                 "'{\"history_length\": 52, \"prediction_length\": 4}'\n"
                 "episerve-client check-config Q7611536028271 config.json",
    )
    cc_p.add_argument("model", metavar="<model>", help="model name or QID, as printed by 'list models'")
    cc_p.add_argument("config", metavar="<config>", help="path to a JSON file, or an inline JSON object")

    # validate
    val_p = _command(
        sub, "validate", "Validate a document (e.g. a model card) against a platform spec",
        usage="validate <document> [--spec SPEC] [--spec-version N]",
        description="Validate a JSON document against a spec of episerve_specs on the API server, e.g. a\n"
                    "model's fdo.json against 'model-card'. Prints valid and the issues (errors and warnings,\n"
                    "each with the path in the document). Exit code 1 when there are errors.",
        notes="The version is --spec-version if given, else the one the document's conformsTo names, else the newest.\n"
              "The same check runs offline with 'episerve-validate' from the episerve_specs package.",
        examples="episerve-client validate fdo.json\n"
                 "episerve-client validate fdo.json --spec model-card --spec-version 1",
    )
    val_p.add_argument("document", metavar="<document>", help="path to a JSON file, or an inline JSON string")
    val_p.add_argument("--spec", default="model-card", metavar="<spec>", help="spec name (default: model-card)")
    val_p.add_argument("--spec-version", metavar="<N>", help="spec version (default: from conformsTo, else newest)")

    # run
    run_p = _command(sub, "run", "Inspect a model run", usage="run <subcommand> <QID>",
                     description="Inspect a model run through the API server.")
    run_sub = _subcommands(run_p, "run_command")
    run_p.set_defaults(_run_parser=run_p)
    run_show_p = _command(
        run_sub, "show", "Show the status of one model run via the API", usage="run show <run-QID>",
        description="Print status, timestamps, computation time and input/output files of one run as JSON.",
        examples="episerve-client run show Q1748526042817",
    )
    run_show_p.add_argument("run_id", metavar="<run-QID>", help="the run's id, as printed by 'list runs'")

    # benchmark
    bench_p = _command(
        sub, "benchmark", "Design benchmarks, read leaderboards, add runs", usage="benchmark <subcommand> ...",
        description="A benchmark fixes a series, a test window and a data version; model runs made from it\n"
                    "are scored once and ranked on its leaderboard.\n\n"
                    "typical flow:\n"
                    "  create -> check -> finalize          design (needs a login)\n"
                    "  run-spec -> trigger-model-run        run a model on the pinned data\n"
                    "  add-entry -> leaderboard             score the finished run, read the ranking",
        notes="Reading (list, show, run-spec, leaderboard) needs no login; everything else does.",
        examples="episerve-client benchmark list\n"
                 "episerve-client benchmark leaderboard 3 --rank-by mae\n"
                 "episerve-client benchmark add-entry 3 Q1788513584728",
    )
    bench_sub = _subcommands(bench_p, "benchmark_command")
    bench_p.set_defaults(_benchmark_parser=bench_p)

    def with_id(name, help_, *, description, examples="", notes=""):
        p = _command(bench_sub, name, help_, usage=f"benchmark {name} <benchmark-id>", description=description,
                     examples=examples, notes=notes)
        p.add_argument("id", type=int, metavar="<benchmark-id>", help="id as printed by 'benchmark list'")
        return p

    _command(bench_sub, "list", "List final benchmarks", usage="benchmark list",
             description="List the final benchmarks with their entry counts.")
    _command(bench_sub, "drafts", "List draft benchmarks (needs a token)", usage="benchmark drafts",
             description="List benchmarks that are still drafts.", notes=_LOGIN_NOTE)
    with_id("show", "Show one benchmark", description="Show the definition and state of one benchmark.",
            notes="Drafts are only visible with a token.")

    create_p = _command(
        bench_sub, "create", "Create a draft from a JSON file or inline JSON (needs a token)",
        usage="benchmark create <params>",
        description="Create a draft benchmark. <params> is the path of a JSON file or an inline JSON string.",
        notes=_BENCHMARK_FIELDS + "\n" + _LOGIN_NOTE,
        examples="episerve-client benchmark create '{\"name\": \"Influenza A+B 2026\", "
                 "\"dataset_qid\": \"Q9493814122238\", \"target_column\": \"viruslast_normalisiert\", "
                 "\"date_column\": \"datum\", \"filter_column\": \"typ\", \"filter_value\": \"Influenza A+B\", "
                 "\"test_start\": \"2026-04-01\", \"test_end\": \"2026-09-30\"}'\n"
                 "episerve-client benchmark create benchmark.json",
    )
    create_p.add_argument("params", metavar="<params>", help="path to a JSON file, or an inline JSON string")

    update_p = with_id(
        "update", "Change fields of a draft from a JSON file or inline JSON (needs a token)",
        description="Change fields of a draft. Only the fields in <params> change; null clears an optional field.\n"
                    "Final benchmarks cannot be changed: use 'benchmark copy' to start a new draft.",
        notes=_BENCHMARK_FIELDS + "\n" + _LOGIN_NOTE,
        examples="episerve-client benchmark update 3 '{\"test_end\": \"2026-08-31\"}'\n"
                 "episerve-client benchmark update 3 '{\"filter_column\": null, \"filter_value\": null}'",
    )
    update_p.add_argument("params", metavar="<params>", help="path to a JSON file, or an inline JSON string")

    with_id("check", "Check a draft against the current data",
            description="Read the data at the current lakeFS head and report problems (which block finalizing),\n"
                        "warnings, the forecast length and the generated input SQL. Stores nothing.",
            notes=_LOGIN_NOTE)
    with_id("finalize", "Pin the current data commit and make a draft final",
            description="Freeze a draft: pins the current lakeFS commit and makes the benchmark immutable.\n"
                        "Unlike the web designer this does not compare with the commit of an earlier 'check';\n"
                        "it pins whatever the lakeFS head is at that moment.",
            notes=_LOGIN_NOTE)
    with_id("copy", "Copy a benchmark as a new draft",
            description="Create a new draft with the same definition. This is how a final benchmark is changed.",
            notes=_LOGIN_NOTE)
    with_id("retire", "Hide a benchmark from the lists",
            description="Retire a benchmark: it disappears from the lists and takes no new entries,\n"
                        "but its leaderboard stays readable.", notes=_LOGIN_NOTE)
    with_id("run-spec", "Show the generated input file and config to run a model on a final benchmark",
            description="Print what a model run needs to use the benchmark's pinned data: the input URL\n"
                        "(with ?version=<data commit>), the SQL, the file name and the forecast length.\n"
                        "The output has the shape of a model-run request.",
            examples="episerve-client benchmark run-spec 3 > spec.json   # add model_image and the model's own "
                     "config, then trigger-model-run")

    lb_p = with_id(
        "leaderboard", "Show the ranked leaderboard",
        description="Show the stored ranking of a benchmark. Each model appears once with its best entry\n"
                    "unless --all-runs is given.",
        notes="--rank-by:\n"
              "  mae             mean absolute error (lower is better)\n"
              "  rmse            root mean squared error (lower is better)\n"
              "  coverage        share of observations inside the 80% interval (closest to 0.8 is best)\n"
              "  interval_score  width of the 80% interval plus a penalty for misses (lower is better; default)",
        examples="episerve-client benchmark leaderboard 3\n"
                 "episerve-client benchmark leaderboard 3 --rank-by mae --all-runs",
    )
    lb_p.add_argument("--rank-by", choices=["mae", "rmse", "coverage", "interval_score"],
                      default="interval_score", help="ranking metric (default: interval_score)")
    lb_p.add_argument("--all-runs", action="store_true", help="every entry instead of each model's best")

    add_p = with_id(
        "add-entry", "Score a finished model run and add it to the leaderboard",
        description="Score a finished model run against the benchmark and add it to the leaderboard.\n"
                    "The run must have read its input at the benchmark's pinned commit and have succeeded.\n"
                    "It can take up to about an hour after a run finishes until it is known to the catalog.",
        notes="If the run is refused, the reason is printed and nothing is stored.\n" + _LOGIN_NOTE,
        examples="episerve-client benchmark add-entry 3 Q1788513584728",
    )
    add_p.add_argument("run_qid", metavar="<run-QID>", help="the finished model run")
    rm_p = with_id(
        "remove-entry", "Remove an entry from the leaderboard",
        description="Remove an entry (soft delete). Add the run again to recompute its scores.",
        notes=_LOGIN_NOTE,
    )
    rm_p.add_argument("entry_id", type=int, metavar="<entry-id>", help="entry id, as shown in 'benchmark leaderboard'")

    return parser


def main():
    _print_banner()
    parser = _build_parser()
    if len(sys.argv) == 1:
        _print_short_help(parser)
        sys.exit(0)
    args = parser.parse_args()
    if args.cli_version:
        sys.exit(_run_cli_version())
    if args.command is None:
        parser.error("a command is required")
    _maybe_announce_update(args)

    dispatch = {
        "login":              cmd_login,
        "health":             cmd_health,
        "list":               cmd_list,
        "trigger-model-run":  cmd_trigger_model_run,
        "check-config":       cmd_check_config,
        "validate":           cmd_validate,
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
