"""Command line interface for FlowYAML v0.

    flowyaml render flow.yaml -o flow.html
    flowyaml render flow.yaml --output fragment --model archive
    flowyaml serve flow.yaml
    flowyaml data flow.yaml -o flow.data.json
    flowyaml validate flow.yaml
    flowyaml models flow.yaml
    flowyaml import workflow.mmd -o workflow.yaml
    flowyaml import process.bpmn --format bpmn > process.yaml
    flowyaml themes

``render`` writes an artifact that is complete on the day it is written.
``serve`` keeps a page attached to the YAML file instead, so an edit shows up
in the browser without a rebuild.

Exit codes: ``0`` success, ``1`` validation or render failure, ``2`` usage.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .api import load, payload_json, read_bpmn, read_mermaid, render, to_yaml, validate
from .errors import FlowYAMLError, FlowYAMLValidationError
from .importers import BPMN_SUFFIXES, MERMAID_SUFFIXES
from .live import DEFAULT_HOST as SERVE_HOST
from .live import DEFAULT_PORT as SERVE_PORT
from .live import serve as serve_source
from .renderer import (
    ASSET_MODES,
    DATA_MODES,
    DEFAULT_LEVELS,
    DEFAULT_POLL_MS,
    LEVEL_MODES,
    OUTPUT_MODES,
)
from .themes import DEFAULT_SCHEME, DEFAULT_THEME, SCHEMES, theme_names

__all__ = ["main", "build_parser"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flowyaml",
        description="Render YAML-defined process flows to offline HTML.",
    )
    parser.add_argument("--version", action="version", version=f"flowyaml {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    render_parser = subparsers.add_parser(
        "render", help="render a YAML source to an HTML document or fragment"
    )
    render_parser.add_argument("source", type=Path, help="path to a FlowYAML YAML file")
    render_parser.add_argument(
        "-o",
        "--out",
        type=Path,
        default=None,
        help="destination file; writes to stdout when omitted",
    )
    render_parser.add_argument(
        "-m", "--model", default=None, help="meta.id of the model that opens first"
    )
    render_parser.add_argument(
        "--output", choices=OUTPUT_MODES, default="document", help="output shape"
    )
    render_parser.add_argument(
        "--assets", choices=ASSET_MODES, default="inline", help="asset embedding mode"
    )
    render_parser.add_argument(
        "--theme", choices=theme_names(), default=DEFAULT_THEME, help="theme name"
    )
    render_parser.add_argument(
        "--scheme",
        choices=SCHEMES,
        default=DEFAULT_SCHEME,
        help=(
            "auto follows the reader's system setting; light and dark pin it. "
            "Both palettes ship either way"
        ),
    )
    render_parser.add_argument(
        "--levels",
        choices=LEVEL_MODES,
        default=DEFAULT_LEVELS,
        help=(
            "breadcrumb keeps the trail in the toolbar; snapshot shows a stripe "
            "of the levels above with a picture of the nearest one"
        ),
    )
    render_parser.add_argument(
        "--lang",
        default=None,
        help="document language tag; defaults to meta.lang, then to en",
    )
    render_parser.add_argument(
        "--instance-id",
        default=None,
        help="fixed DOM prefix, for reproducible output",
    )
    render_parser.add_argument(
        "--data",
        choices=DATA_MODES,
        default="inline",
        help=(
            "inline embeds the graph once; url leaves it out and has the page "
            "fetch it from --data-url, so an edited YAML reaches the page"
        ),
    )
    render_parser.add_argument(
        "--data-url",
        default=None,
        help="where the host serves the payload; required with --data url",
    )
    render_parser.add_argument(
        "--revision-url",
        default=None,
        help="optional cheaper poll target answering a revision marker",
    )
    render_parser.add_argument(
        "--poll-ms",
        type=int,
        default=DEFAULT_POLL_MS,
        help="how often a --data url page checks for a new revision; 0 disables",
    )

    serve_parser = subparsers.add_parser(
        "serve",
        help="serve a page that follows the YAML file as it is edited",
    )
    serve_parser.add_argument("source", type=Path, help="path to a FlowYAML YAML file")
    serve_parser.add_argument(
        "--host", default=SERVE_HOST, help="interface to bind"
    )
    serve_parser.add_argument(
        "-p", "--port", type=int, default=SERVE_PORT, help="port to bind"
    )
    serve_parser.add_argument(
        "-m", "--model", default=None, help="meta.id of the model that opens first"
    )
    serve_parser.add_argument(
        "--theme", choices=theme_names(), default=DEFAULT_THEME, help="theme name"
    )
    serve_parser.add_argument(
        "--poll-ms",
        type=int,
        default=DEFAULT_POLL_MS,
        help="how often the page checks for a new revision; 0 means on reload only",
    )
    serve_parser.add_argument(
        "--open", action="store_true", help="open the page in the default browser"
    )
    serve_parser.add_argument(
        "-v", "--verbose", action="store_true", help="log every request"
    )

    data_parser = subparsers.add_parser(
        "data",
        help="emit the JSON payload a host serves to a --data url page",
    )
    data_parser.add_argument("source", type=Path)
    data_parser.add_argument(
        "-o", "--out", type=Path, default=None, help="destination file; stdout when omitted"
    )
    data_parser.add_argument(
        "-m", "--model", default=None, help="meta.id of the model that opens first"
    )
    data_parser.add_argument(
        "--revision",
        default=None,
        help="opaque marker the page compares to decide whether to reload",
    )

    validate_parser = subparsers.add_parser(
        "validate", help="report structured validation issues"
    )
    validate_parser.add_argument("source", type=Path)

    models_parser = subparsers.add_parser(
        "models", help="list the model ids embedded in a source"
    )
    models_parser.add_argument("source", type=Path)

    import_parser = subparsers.add_parser(
        "import", help="convert a Mermaid or BPMN source to FlowYAML YAML"
    )
    import_parser.add_argument(
        "source", type=Path, help="path to a .mmd, .mermaid, .bpmn or .xml file"
    )
    import_parser.add_argument(
        "-o",
        "--out",
        type=Path,
        default=None,
        help="destination file; writes to stdout when omitted",
    )
    import_parser.add_argument(
        "--format",
        choices=IMPORT_FORMATS,
        default=None,
        help="source notation; inferred from the file suffix when omitted",
    )
    import_parser.add_argument(
        "--id", dest="model_id", default=None, help="meta.id of the first model"
    )
    import_parser.add_argument(
        "--name", default=None, help="meta.name of the first model"
    )

    subparsers.add_parser("themes", help="list the registered theme names")
    return parser


IMPORT_FORMATS = ("mermaid", "bpmn")

_IMPORTERS = {"mermaid": read_mermaid, "bpmn": read_bpmn}


def _infer_format(path: Path) -> str | None:
    """Return the import format a path's suffix implies, or ``None``."""
    name = path.name.lower()
    if name.endswith(MERMAID_SUFFIXES):
        return "mermaid"
    if name.endswith(BPMN_SUFFIXES):
        return "bpmn"
    return None


def _run_import(args: argparse.Namespace) -> int:
    source_format = args.format or _infer_format(args.source)
    if source_format is None:
        print(
            f"flowyaml: cannot infer the import format of {args.source}; "
            f"pass --format {{{','.join(IMPORT_FORMATS)}}}",
            file=sys.stderr,
        )
        return 2

    try:
        diagram = _IMPORTERS[source_format](
            args.source, model_id=args.model_id, name=args.name
        )
    except FlowYAMLValidationError as error:  # pragma: no cover - defensive
        for issue in error.issues:
            print(str(issue), file=sys.stderr)
        return 1
    except FlowYAMLError as error:
        print(f"flowyaml: {error}", file=sys.stderr)
        return 1

    text = to_yaml(diagram)
    if args.out is None:
        _write_stdout(text)
        return 0

    if args.out.parent and not args.out.parent.exists():
        args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    count = len(diagram)
    noun = "model" if count == 1 else "models"
    print(f"flowyaml: wrote {args.out} ({count} {noun})")
    return 0


def _run_serve(args: argparse.Namespace) -> int:
    if not args.source.is_file():
        print(f"flowyaml: cannot read {args.source}", file=sys.stderr)
        return 1
    # A source that does not validate is not a reason to refuse to start: the
    # point of serving is to edit, and the page reports the issues itself.
    issues = validate(_read(args.source))
    for issue in issues:
        print(str(issue), file=sys.stderr)
    if issues:
        count = len(issues)
        print(
            f"flowyaml: {count} issue{'s' if count != 1 else ''} in {args.source}; "
            "serving anyway, the page will report them",
            file=sys.stderr,
        )
    try:
        serve_source(
            args.source,
            host=args.host,
            port=args.port,
            model_id=args.model,
            theme=args.theme,
            poll_ms=args.poll_ms,
            open_browser=args.open,
            verbose=args.verbose,
        )
    except OSError as error:
        print(f"flowyaml: cannot serve on {args.host}:{args.port}: {error}", file=sys.stderr)
        return 1
    return 0


def _run_data(args: argparse.Namespace) -> int:
    try:
        text = payload_json(
            _read(args.source), model_id=args.model, revision=args.revision
        )
    except FlowYAMLValidationError as error:
        for issue in error.issues:
            print(str(issue), file=sys.stderr)
        return 1
    except FlowYAMLError as error:
        print(f"flowyaml: {error}", file=sys.stderr)
        return 1

    if args.out is None:
        _write_stdout(text)
        return 0
    if args.out.parent and not args.out.parent.exists():
        args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"flowyaml: wrote {args.out}")
    return 0


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_stdout(text: str) -> None:
    """Emit ``text`` to stdout as UTF-8, whatever the console codepage is.

    The artifact declares ``<meta charset="utf-8">`` and the ``--out`` path
    always writes UTF-8, so the stdout path must not fall back to the locale
    codec. On a cp1252 console a plain ``sys.stdout.write`` either mangles or
    refuses accented labels, which is exactly what real source files carry.
    """
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:  # pragma: no cover - streams without a byte layer
        sys.stdout.write(text)
        return
    sys.stdout.flush()
    buffer.write(text.encode("utf-8"))
    buffer.flush()


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "themes":
        for name in theme_names():
            marker = " (default)" if name == DEFAULT_THEME else ""
            print(f"{name}{marker}")
        return 0

    if args.command == "import":
        # The importers read the file themselves, so an error can name the
        # source and the position inside it.
        return _run_import(args)

    if args.command == "serve":
        # The server reads the file per request, which is the whole point.
        return _run_serve(args)

    try:
        source = _read(args.source)
    except OSError as error:
        print(f"flowyaml: cannot read {args.source}: {error}", file=sys.stderr)
        return 1

    if args.command == "data":
        return _run_data(args)

    if args.command == "validate":
        issues = validate(source)
        if not issues:
            print(f"flowyaml: {args.source} is valid")
            return 0
        for issue in issues:
            print(str(issue), file=sys.stderr)
        count = len(issues)
        print(
            f"flowyaml: {count} issue{'s' if count != 1 else ''} in {args.source}",
            file=sys.stderr,
        )
        return 1

    if args.command == "models":
        try:
            diagram = load(source)
        except FlowYAMLValidationError as error:
            for issue in error.issues:
                print(str(issue), file=sys.stderr)
            return 1
        for model in diagram.models:
            print(f"{model.id}\t{model.title}")
        return 0

    try:
        html_text = render(
            source,
            model_id=args.model,
            output=args.output,
            assets=args.assets,
            data=args.data,
            data_url=args.data_url,
            revision_url=args.revision_url,
            poll_ms=args.poll_ms,
            theme=args.theme,
            scheme=args.scheme,
            levels=args.levels,
            lang=args.lang,
            instance_id=args.instance_id,
        )
    except FlowYAMLValidationError as error:
        for issue in error.issues:
            print(str(issue), file=sys.stderr)
        return 1
    except FlowYAMLError as error:
        print(f"flowyaml: {error}", file=sys.stderr)
        return 1

    if args.out is None:
        _write_stdout(html_text)
        return 0

    if args.out.parent and not args.out.parent.exists():
        args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html_text, encoding="utf-8")
    size_kb = round(len(html_text.encode("utf-8")) / 1024)
    print(f"flowyaml: wrote {args.out} ({size_kb} KB)")
    return 0
