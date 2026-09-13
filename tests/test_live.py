"""The YAML-linked update path.

``data="inline"`` is a snapshot: the graph is embedded once and the artifact
never asks anything of anyone. ``data="url"`` is the ERP DINFRA arrangement:
the page carries no graph and reads it from a host that re-reads the YAML file
per request, so an edit reaches an open browser.

These tests hold both halves of that boundary in place - the inline artifact
must stay offline, and the linked one must actually follow the file.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import flowyaml
from flowyaml.errors import FlowYAMLOptionError, FlowYAMLValidationError
from flowyaml.live import DATA_PATH, MISSING_REVISION, REVISION_PATH, LinkedSource, create_server

DATA_SCRIPT = re.compile(
    r'<script id="[^"]+-data" type="application/json">(.*?)</script>', re.S
)

#: The banner of the linked-source loader. The runtime, which ships in every
#: render, mentions the event name itself, so the banner is the honest probe
#: for whether the loader was emitted.
LIVE_MARKER = "FlowYAML linked-source loader"


def config_of(document: str) -> dict:
    """The parsed boot payload of a rendered document or fragment."""
    match = DATA_SCRIPT.search(document)
    assert match is not None, "no boot payload in the rendered output"
    return json.loads(match.group(1))


@pytest.fixture
def source_file(tmp_path: Path, parity_source: str) -> Path:
    path = tmp_path / "flow.yaml"
    path.write_text(parity_source, encoding="utf-8")
    return path


# --------------------------------------------------------------- render modes


class TestInlineStaysASnapshot:
    def test_the_default_embeds_the_graph_and_asks_for_nothing(self, parity_source):
        document = flowyaml.render(parity_source, instance_id="fy-inline")
        config = config_of(document)
        assert config["models"], "the inline payload carries the graph"
        assert "source" not in config
        assert LIVE_MARKER not in document
        assert "fetch(" not in document

    def test_a_fragment_is_a_snapshot_too(self, parity_source):
        fragment = flowyaml.render(
            parity_source, output="fragment", instance_id="fy-frag"
        )
        assert "source" not in config_of(fragment)
        assert LIVE_MARKER not in fragment

    @pytest.mark.parametrize("option", ["data_url", "revision_url"])
    def test_a_url_option_without_url_mode_is_refused(self, parity_source, option):
        with pytest.raises(FlowYAMLOptionError) as caught:
            flowyaml.render(parity_source, **{option: "/flowyaml/data.json"})
        assert option in str(caught.value)


class TestLinkedRenders:
    def test_the_graph_is_left_out_and_a_source_block_takes_its_place(
        self, parity_source
    ):
        document = flowyaml.render(
            parity_source,
            data="url",
            data_url="/flowyaml/data.json",
            revision_url="/flowyaml/revision.json",
            poll_ms=750,
            instance_id="fy-linked",
        )
        config = config_of(document)
        assert "models" not in config, "a linked page must not carry a stale graph"
        assert config["source"] == {
            "data": "/flowyaml/data.json",
            "revision": "/flowyaml/revision.json",
            "poll": 750,
        }
        assert LIVE_MARKER in document, "the linked loader is emitted"
        assert "fetch(" in document

    def test_the_document_still_opens_the_selected_model(self, parity_source):
        document = flowyaml.render(
            parity_source,
            model_id="quotation",
            data="url",
            data_url="/d.json",
            instance_id="fy-pick",
        )
        assert config_of(document)["defaultModel"] == "quotation"

    def test_polling_can_be_turned_off(self, parity_source):
        config = config_of(
            flowyaml.render(parity_source, data="url", data_url="/d.json", poll_ms=0)
        )
        assert config["source"]["poll"] == 0
        assert "revision" not in config["source"]

    def test_url_mode_needs_a_url(self, parity_source):
        with pytest.raises(FlowYAMLOptionError) as caught:
            flowyaml.render(parity_source, data="url")
        assert "data_url" in str(caught.value)

    def test_an_unknown_data_mode_is_refused(self, parity_source):
        with pytest.raises(FlowYAMLOptionError):
            flowyaml.render(parity_source, data="websocket")

    @pytest.mark.parametrize(
        "url",
        [
            "javascript:alert(1)",
            "data:application/json,{}",
            "file:///etc/passwd",
            "/data.json?q=a b",
            "",
            "   ",
        ],
    )
    def test_an_unsafe_data_url_is_refused(self, parity_source, url):
        with pytest.raises(FlowYAMLOptionError):
            flowyaml.render(parity_source, data="url", data_url=url)

    @pytest.mark.parametrize("url", ["/flowyaml/data.json", "data.json", "https://host/d"])
    def test_a_relative_or_http_url_is_accepted(self, parity_source, url):
        config = config_of(
            flowyaml.render(parity_source, data="url", data_url=url)
        )
        assert config["source"]["data"] == url

    @pytest.mark.parametrize("poll", [-1, 50, 1.5, True, "1000"])
    def test_an_unusable_poll_interval_is_refused(self, parity_source, poll):
        with pytest.raises(FlowYAMLOptionError):
            flowyaml.render(parity_source, data="url", data_url="/d.json", poll_ms=poll)


# -------------------------------------------------------------- host payload


class TestPayload:
    def test_it_carries_the_models_the_runtime_consumes(self, parity_source):
        body = flowyaml.payload(parity_source)
        assert [model["id"] for model in body["models"]] == list(
            flowyaml.models(parity_source)
        )
        assert body["defaultModel"] == body["models"][0]["id"]
        assert "revision" not in body

    def test_the_revision_is_passed_through_untouched(self, parity_source):
        assert flowyaml.payload(parity_source, revision="abc123")["revision"] == "abc123"

    def test_it_honours_the_selected_model(self, parity_source):
        assert flowyaml.payload(parity_source, model_id="dispatch")["defaultModel"] == (
            "dispatch"
        )

    def test_json_form_round_trips(self, parity_source):
        text = flowyaml.payload_json(parity_source, revision="r1")
        assert json.loads(text) == flowyaml.payload(parity_source, revision="r1")

    def test_an_invalid_source_raises(self):
        with pytest.raises(FlowYAMLValidationError):
            flowyaml.payload("meta:\n  id: x\nnodes: []\n")


# ------------------------------------------------------------- linked source


class TestLinkedSource:
    def test_it_reads_the_file_again_on_every_ask(self, source_file: Path):
        linked = LinkedSource(source_file)
        before = linked.data()
        first = before["models"][0]["name"]

        source_file.write_text(
            source_file.read_text(encoding="utf-8").replace(first, "Edited in place", 1),
            encoding="utf-8",
        )

        after = linked.data()
        assert after["models"][0]["name"] == "Edited in place"
        assert after["revision"] != before["revision"]

    def test_the_revision_only_moves_when_the_content_does(self, source_file: Path):
        linked = LinkedSource(source_file)
        first = linked.revision()
        source_file.write_text(source_file.read_text(encoding="utf-8"), encoding="utf-8")
        assert linked.revision() == first

    def test_a_broken_source_is_an_answer_not_a_failure(self, source_file: Path):
        linked = LinkedSource(source_file)
        assert linked.data()["models"]

        source_file.write_text("meta:\n  id: broken\nnodes: []\n", encoding="utf-8")
        broken = linked.data()
        assert "error" in broken and broken["issues"]
        assert broken["revision"] != MISSING_REVISION

    def test_a_missing_file_reports_a_missing_revision(self, tmp_path: Path):
        linked = LinkedSource(tmp_path / "gone.yaml")
        body = linked.data()
        assert body["revision"] == MISSING_REVISION
        assert "error" in body

    def test_the_shell_is_cached_per_revision(self, source_file: Path):
        linked = LinkedSource(source_file)
        first = linked.document()
        assert first is linked.document(), "an unchanged source is not re-rendered"

        source_file.write_text(
            source_file.read_text(encoding="utf-8").replace(
                "Material distribution", "Renamed", 1
            ),
            encoding="utf-8",
        )
        assert linked.document() is not first

    def test_a_break_keeps_the_last_good_shell_alive(self, source_file: Path):
        linked = LinkedSource(source_file)
        good = linked.document()
        source_file.write_text("nodes: [\n", encoding="utf-8")
        assert linked.document() == good, "the open page must survive a broken save"

    def test_a_source_that_was_never_valid_gets_a_self_refreshing_page(
        self, tmp_path: Path
    ):
        path = tmp_path / "bad.yaml"
        path.write_text("meta:\n  id: bad\nnodes: []\n", encoding="utf-8")
        page = LinkedSource(path).document()
        assert "not renderable" in page
        assert "http-equiv" in page


# -------------------------------------------------------------------- server


@pytest.fixture
def host(source_file: Path):
    """A started server on an ephemeral port, linked to ``source_file``."""
    server = create_server(source_file, port=0, poll_ms=200)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def fetch(server, path: str):
    with urllib.request.urlopen(f"http://127.0.0.1:{server.server_address[1]}{path}") as answer:
        return answer.status, answer.headers, answer.read().decode("utf-8")


class TestServer:
    def test_the_page_is_linked_not_embedded(self, host):
        status, headers, body = fetch(host, "/")
        assert status == 200
        assert headers["Content-Type"].startswith("text/html")
        config = config_of(body)
        assert config["source"]["data"] == DATA_PATH
        assert config["source"]["revision"] == REVISION_PATH
        assert "models" not in config

    def test_the_data_route_answers_the_graph(self, host):
        status, headers, body = fetch(host, DATA_PATH)
        payload = json.loads(body)
        assert status == 200
        assert headers["Content-Type"].startswith("application/json")
        assert "no-store" in headers["Cache-Control"]
        assert [model["id"] for model in payload["models"]]

    def test_an_edit_reaches_the_next_request(self, host, source_file: Path):
        """The requirement, end to end: save the YAML, ask again, see it."""
        before = json.loads(fetch(host, DATA_PATH)[2])
        original = before["models"][0]["name"]

        source_file.write_text(
            source_file.read_text(encoding="utf-8").replace(original, "Live edit", 1),
            encoding="utf-8",
        )

        after = json.loads(fetch(host, DATA_PATH)[2])
        assert after["models"][0]["name"] == "Live edit"
        assert after["revision"] != before["revision"]

    def test_the_revision_route_tracks_the_data_route(self, host, source_file: Path):
        revision = json.loads(fetch(host, REVISION_PATH)[2])["revision"]
        assert revision == json.loads(fetch(host, DATA_PATH)[2])["revision"]

        source_file.write_text(
            source_file.read_text(encoding="utf-8") + "\n# touched\n", encoding="utf-8"
        )
        assert json.loads(fetch(host, REVISION_PATH)[2])["revision"] != revision

    def test_a_broken_save_does_not_take_the_page_down(self, host, source_file: Path):
        source_file.write_text("meta:\n  id: broken\nnodes: []\n", encoding="utf-8")
        assert fetch(host, "/")[0] == 200
        body = json.loads(fetch(host, DATA_PATH)[2])
        assert body["issues"]

    def test_nothing_else_is_served(self, host):
        for path in ("/nope", "/../pyproject.toml", "/flowyaml/", "/index.htm"):
            with pytest.raises(urllib.error.HTTPError) as caught:
                fetch(host, path)
            assert caught.value.code == 404

    def test_head_carries_the_headers_without_the_body(self, host):
        request = urllib.request.Request(
            f"http://127.0.0.1:{host.server_address[1]}{DATA_PATH}", method="HEAD"
        )
        with urllib.request.urlopen(request) as answer:
            assert answer.status == 200
            assert answer.read() == b""

    def test_the_url_names_the_bound_port(self, host):
        assert host.url.endswith(f":{host.server_address[1]}/")


# ----------------------------------------------------------------------- cli


class TestCli:
    def test_render_can_emit_a_linked_document(self, tmp_path: Path, source_file: Path):
        from flowyaml.cli import main

        target = tmp_path / "linked.html"
        code = main(
            [
                "render",
                str(source_file),
                "-o",
                str(target),
                "--data",
                "url",
                "--data-url",
                "/flowyaml/data.json",
                "--poll-ms",
                "0",
            ]
        )
        assert code == 0
        config = config_of(target.read_text(encoding="utf-8"))
        assert config["source"] == {"data": "/flowyaml/data.json", "poll": 0}
        assert "models" not in config

    def test_render_url_without_a_url_fails(self, source_file: Path, capsys):
        from flowyaml.cli import main

        assert main(["render", str(source_file), "--data", "url"]) == 1
        assert "data_url" in capsys.readouterr().err

    def test_data_writes_the_host_payload(self, tmp_path: Path, source_file: Path):
        from flowyaml.cli import main

        target = tmp_path / "flow.data.json"
        assert main(["data", str(source_file), "-o", str(target), "--revision", "r7"]) == 0
        body = json.loads(target.read_text(encoding="utf-8"))
        assert body["revision"] == "r7"
        assert [model["id"] for model in body["models"]]

    def test_data_reports_validation_issues(self, tmp_path: Path, capsys):
        from flowyaml.cli import main

        broken = tmp_path / "broken.yaml"
        broken.write_text("meta:\n  id: broken\nnodes: []\n", encoding="utf-8")
        assert main(["data", str(broken)]) == 1
        assert capsys.readouterr().err.strip()

    def test_serve_refuses_a_missing_file(self, tmp_path: Path, capsys):
        from flowyaml.cli import main

        assert main(["serve", str(tmp_path / "nothing.yaml")]) == 1
        assert "cannot read" in capsys.readouterr().err

    def test_serve_parses_with_the_documented_defaults(self, source_file: Path):
        from flowyaml.cli import build_parser
        from flowyaml.live import DEFAULT_HOST, DEFAULT_PORT
        from flowyaml.renderer import DEFAULT_POLL_MS

        args = build_parser().parse_args(["serve", str(source_file)])
        assert (args.host, args.port, args.poll_ms) == (
            DEFAULT_HOST,
            DEFAULT_PORT,
            DEFAULT_POLL_MS,
        )
        assert args.open is False
