"""Keep a rendered FlowYAML page linked to the YAML file it came from.

The delivered ERP DINFRA flowchart works this way: the page carries no graph
of its own, and a Django view re-reads ``dinfra_workflows.yaml`` from disk on
every request to ``/flowcharts/data.json``. Editing the YAML and reloading the
page is the whole update loop, with no build step in between.

This module is that host, in stdlib only, for a FlowYAML source:

    /                       the rendered shell, ``data="url"``
    /flowyaml/data.json     the graph, re-read and re-validated per request
    /flowyaml/revision.json a content digest, so the page can poll cheaply

It is a local host for an editing session, not a production server: it binds
to the loopback interface, answers three fixed paths, and never maps a
request path onto the filesystem.
"""

from __future__ import annotations

import hashlib
import html
import json
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from .api import payload as build_payload
from .api import render
from .errors import FlowYAMLError, FlowYAMLValidationError
from .renderer import DEFAULT_POLL_MS, GENERATOR
from .themes import DEFAULT_THEME

__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DATA_PATH",
    "REVISION_PATH",
    "LinkedSource",
    "LiveServer",
    "create_server",
    "serve",
]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

#: Fixed routes. Nothing else is served, and no path reaches the filesystem.
DATA_PATH = "/flowyaml/data.json"
REVISION_PATH = "/flowyaml/revision.json"
PAGE_PATHS = ("/", "/index.html")

#: Revision reported when the source file is not there at all.
MISSING_REVISION = "missing"


class LinkedSource:
    """One YAML file on disk, read afresh whenever it is asked for.

    The shell HTML is cached per revision because it carries the vendored
    layout engine and is expensive to rebuild; the graph never is. When the
    file stops being valid the last good shell keeps being served, so the page
    stays alive and reports the validation issues on its own canvas.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        model_id: str | None = None,
        theme: str = DEFAULT_THEME,
        poll_ms: int = DEFAULT_POLL_MS,
    ) -> None:
        self.path = Path(path)
        self.model_id = model_id
        self.theme = theme
        self.poll_ms = poll_ms
        self._lock = threading.Lock()
        self._document: str | None = None
        self._document_revision: str | None = None

    # ------------------------------------------------------------- reading

    def read(self) -> str | None:
        """Return the current source text, or ``None`` when unreadable."""
        try:
            return self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def revision(self) -> str:
        """An opaque marker that changes exactly when the file content does."""
        try:
            raw = self.path.read_bytes()
        except OSError:
            return MISSING_REVISION
        return hashlib.sha256(raw).hexdigest()[:16]

    # ------------------------------------------------------------- answers

    def data(self) -> dict[str, Any]:
        """The body for the data route.

        A broken source is an ordinary answer, not a failed request: whoever is
        editing the YAML gets the issues drawn on the canvas instead of a dead
        page, and the next save fixes it in place.
        """
        revision = self.revision()
        source = self.read()
        if source is None:
            return self._error(revision, f"cannot read {self.path}", ())
        try:
            return build_payload(source, model_id=self.model_id, revision=revision)
        except FlowYAMLValidationError as error:
            count = len(error.issues)
            noun = "issue" if count == 1 else "issues"
            return self._error(
                revision,
                f"{self.path.name}: {count} validation {noun}",
                tuple(str(issue) for issue in error.issues),
            )
        except FlowYAMLError as error:
            return self._error(revision, f"{self.path.name}: {error}", ())

    def document(self) -> str:
        """The shell HTML for the page route."""
        revision = self.revision()
        with self._lock:
            if self._document is not None and self._document_revision == revision:
                return self._document

        source = self.read()
        rendered: str | None = None
        if source is not None:
            try:
                rendered = render(
                    source,
                    model_id=self.model_id,
                    theme=self.theme,
                    data="url",
                    data_url=DATA_PATH,
                    revision_url=REVISION_PATH,
                    poll_ms=self.poll_ms,
                )
            except FlowYAMLError:
                rendered = None

        with self._lock:
            if rendered is not None:
                self._document = rendered
                self._document_revision = revision
                return rendered
            if self._document is not None:
                # The source is broken right now. The last good shell still
                # runs, and its data request reports what broke.
                return self._document
        return self._placeholder()

    # ------------------------------------------------------------ internals

    def _error(
        self, revision: str, message: str, issues: tuple[str, ...]
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "generator": GENERATOR,
            "revision": revision,
            "error": message,
        }
        if issues:
            body["issues"] = list(issues)
        return body

    def _placeholder(self) -> str:
        """A page for a source that has never been renderable in this session.

        It refreshes itself, so fixing the YAML brings the real page back
        without the reader having to do anything.
        """
        body = self.data()
        lines = [html.escape(str(body.get("error", "")))]
        for issue in body.get("issues", []):
            lines.append(html.escape(str(issue)))
        items = "".join(f"<li>{line}</li>" for line in lines if line)
        return (
            "<!doctype html>"
            '<html lang="en"><head><meta charset="utf-8">'
            '<meta http-equiv="refresh" content="2">'
            "<title>FlowYAML: source not renderable</title>"
            "<style>body{margin:0;padding:40px;font:14px/1.6 ui-sans-serif,"
            "system-ui,sans-serif;color:#1d2733;background:#f5f6f8}"
            "ul{padding-left:18px}li{margin:4px 0}</style></head><body>"
            f"<h1>{html.escape(self.path.name)} is not renderable</h1>"
            f"<ul>{items}</ul>"
            "<p>Fix the source and save; this page reloads itself every two "
            "seconds.</p></body></html>"
        )


class _Handler(BaseHTTPRequestHandler):
    """Three fixed routes. No path is ever resolved against the filesystem."""

    server_version = GENERATOR.replace(" ", "/")
    sys_version = ""
    protocol_version = "HTTP/1.1"

    @property
    def linked(self) -> LinkedSource:
        return self.server.linked

    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # The whole point of this server is to never answer from a cache.
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, body: dict[str, Any]) -> None:
        self._send(
            HTTPStatus.OK,
            json.dumps(body, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _route(self) -> None:
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        if path in PAGE_PATHS:
            self._send(
                HTTPStatus.OK,
                self.linked.document().encode("utf-8"),
                "text/html; charset=utf-8",
            )
            return
        if path == DATA_PATH:
            self._json(self.linked.data())
            return
        if path == REVISION_PATH:
            self._json({"revision": self.linked.revision()})
            return
        known = ", ".join((*PAGE_PATHS, DATA_PATH, REVISION_PATH))
        self._send(
            HTTPStatus.NOT_FOUND,
            f"flowyaml serve answers {known}".encode("utf-8"),
            "text/plain; charset=utf-8",
        )

    def do_GET(self) -> None:
        self._route()

    def do_HEAD(self) -> None:
        self._route()

    def version_string(self) -> str:
        # The base implementation appends the Python version; this host has no
        # reason to announce the interpreter it happens to run on.
        return self.server_version

    def log_message(self, format: str, *args: Any) -> None:
        if getattr(self.server, "verbose", False):
            super().log_message(format, *args)


class LiveServer(ThreadingHTTPServer):
    """A threading HTTP server that carries the linked source."""

    daemon_threads = True

    def __init__(self, address: tuple[str, int], linked: LinkedSource, verbose: bool):
        super().__init__(address, _Handler)
        self.linked = linked
        self.verbose = verbose

    @property
    def url(self) -> str:
        host, port = self.server_address[0], self.server_address[1]
        return f"http://{host}:{port}/"


def create_server(
    source: str | Path,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    model_id: str | None = None,
    theme: str = DEFAULT_THEME,
    poll_ms: int = DEFAULT_POLL_MS,
    verbose: bool = False,
) -> LiveServer:
    """Return an unstarted server linked to the YAML file at ``source``.

    Pass ``port=0`` to let the operating system choose one; the chosen port is
    then readable from ``server.server_address``.
    """
    linked = LinkedSource(source, model_id=model_id, theme=theme, poll_ms=poll_ms)
    return LiveServer((host, port), linked, verbose)


def _announce(message: str) -> None:
    """Print without waiting for a buffer: this output is watched, not read later."""
    print(message, flush=True)


def serve(
    source: str | Path,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    model_id: str | None = None,
    theme: str = DEFAULT_THEME,
    poll_ms: int = DEFAULT_POLL_MS,
    open_browser: bool = False,
    verbose: bool = False,
    announce: Callable[[str], None] | None = _announce,
) -> None:
    """Serve ``source`` until interrupted.

    Saving an edit to the YAML file updates the open page within ``poll_ms``,
    and always on reload.
    """
    server = create_server(
        source,
        host=host,
        port=port,
        model_id=model_id,
        theme=theme,
        poll_ms=poll_ms,
        verbose=verbose,
    )
    if announce is not None:
        announce(f"flowyaml: serving {Path(source)} at {server.url}")
        follows = f"within {poll_ms} ms" if poll_ms else "on reload"
        announce(f"flowyaml: edit the YAML and save; the page follows it {follows}")
        announce("flowyaml: press Ctrl+C to stop")
    if open_browser:
        webbrowser.open(server.url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        if announce is not None:
            announce("")
            announce("flowyaml: stopped")
    finally:
        server.server_close()
