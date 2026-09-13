"""Offline completeness of the generated artifact.

These checks run without a browser. They prove the document declares no
external resource and carries the whole vendored runtime. The headless
counterpart in ``test_browser.py`` proves the same thing by aborting every
non ``file://`` request.
"""

from __future__ import annotations

import re

import pytest

import flowyaml
from flowyaml.renderer import read_asset

#: XML/EMF namespace URIs are identifiers, not fetches. The vendored bundle
#: carries a handful of them plus its own licence URL, and nothing else.
ALLOWED_URL_PREFIXES = (
    "http://www.w3.org/",
    "http://www.eclipse.org/",
    "http://www.apache.org/licenses/",
    "https://www.eclipse.org/",
    "http:///",  # EMF namespace with an empty authority; not addressable
)

FORBIDDEN_MARKUP = (
    "<script src=",
    "<link ",
    "<img ",
    "<iframe",
    "<object",
    "<embed",
    "@import",
    "url(http",
    "url(//",
    "srcset=",
    "@font-face",
)


@pytest.fixture(scope="module")
def html(parity_source):
    return flowyaml.render(parity_source, instance_id="fy-offline")


def test_no_external_resource_is_declared(html):
    lowered = html.lower()
    for marker in FORBIDDEN_MARKUP:
        assert marker not in lowered, marker


def test_no_runtime_fetch_primitive_is_used(html):
    """The vendored bundle and the runtime must not reach the network."""
    runtime = read_asset("runtime.js")
    for marker in ("fetch(", "XMLHttpRequest", "importScripts", "navigator.sendBeacon"):
        assert marker not in runtime, marker
    assert "new Worker(" not in runtime


def test_the_default_document_carries_no_network_code_at_all(html):
    """The linked-source loader exists, and the inline artifact never ships it.

    ``data="url"`` puts one fetch into the generated page on purpose. This is
    the check that the default render is untouched by that: the loader is a
    separate asset, so the offline artifact stays offline by construction, not
    by inspection.
    """
    assert "FlowYAML linked-source loader" in read_asset("live.js")
    for marker in ("fetch(", "XMLHttpRequest", "FlowYAML linked-source loader"):
        assert marker not in html, marker


def test_flowyaml_generated_text_names_only_the_svg_namespace(html):
    """Strictest check: everything FlowYAML itself writes, bundle excluded."""
    generated = html.replace(read_asset("elk.bundled.js"), "")
    urls = set(re.findall(r"https?://[^\s\"'\)<>]+", generated))
    assert urls == {"http://www.w3.org/2000/svg"}


def test_every_absolute_url_is_an_identifier_not_a_resource(html):
    for url in re.findall(r"https?://[^\s\"'\)<>]+", html):
        assert url.startswith(ALLOWED_URL_PREFIXES), url


def test_the_vendored_elk_bundle_is_embedded_whole(html):
    bundle = read_asset("elk.bundled.js")
    assert len(bundle) > 1_000_000
    assert bundle in html
    assert "elkjs 0.9.3" in html


def test_the_runtime_and_stylesheet_are_embedded_whole(html):
    assert read_asset("runtime.js").replace(
        "__FLOWYAML_DATA_ID__", "fy-offline-data"
    ) in html
    assert "--fy-canvas: #F7F5F1;" in html


def test_assets_carry_their_licence_and_version_record():
    licence = read_asset("elk.LICENSE.md")
    version = read_asset("elk.VERSION.txt")
    assert "Eclipse Public License" in licence
    assert "elkjs 0.9.3" in version


@pytest.mark.parametrize("asset", ["elk.bundled.js", "runtime.js", "styles.css"])
def test_no_vendored_asset_can_close_the_element_that_carries_it(asset):
    """A vendored file is inlined verbatim, so it must carry no closing token.

    ``</script`` anywhere in the bundle would end the element early and
    spill the rest of the file into the page as markup. This is the check
    that has to fail loudly if the vendored ELK build is ever bumped to one
    that contains such a string.
    """
    source = read_asset(asset).lower()
    for token in ("</script", "</style", "<!--"):
        assert token not in source, f"{asset} carries {token!r}"


def test_no_placeholder_survives_into_the_output(html):
    assert "__ROOT__" not in html
    assert "__FLOWYAML_DATA_ID__" not in html


def test_url_asset_mode_is_reserved_but_not_implemented(minimal_source):
    assert flowyaml.ASSET_MODES == ("inline",)
    with pytest.raises(flowyaml.FlowYAMLOptionError) as caught:
        flowyaml.render(minimal_source, assets="url")
    assert "inline" in str(caught.value)


def test_document_is_self_sufficient_from_disk(tmp_path, parity_source):
    """Everything needed is in one file; nothing sits beside it."""
    target = tmp_path / "solo" / "flow.html"
    flowyaml.write_html(parity_source, target, instance_id="fy-solo")
    assert [item.name for item in target.parent.iterdir()] == ["flow.html"]
    assert target.stat().st_size > 1_000_000


def test_the_runtime_never_assigns_innerhtml():
    """Spec rule: YAML labels reach the DOM only as text nodes."""
    code = re.sub(r"/\*.*?\*/", "", read_asset("runtime.js"), flags=re.DOTALL)
    for marker in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert marker not in code, marker


def test_the_runtime_creates_no_global_of_its_own():
    """Only window.ELK is read; nothing is written to the global scope."""
    runtime = read_asset("runtime.js")
    assert runtime.lstrip().startswith("/*")
    assert "(function () {" in runtime
    assert runtime.rstrip().endswith("})();")
    for marker in ("window.flowyaml", "window.FlowYAML", "globalThis."):
        assert marker not in runtime, marker


def test_every_dom_identifier_is_derived_from_the_instance_prefix(parity_source):
    """Ids, marker ids and the tooltip id all carry the instance prefix."""
    import re as _re

    html = flowyaml.render(parity_source, instance_id="fy-ids")
    for element_id in _re.findall(r'id="([^"]+)"', html):
        assert element_id.startswith("fy-ids"), element_id
