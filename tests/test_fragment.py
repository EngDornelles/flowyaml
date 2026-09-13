"""Host-safe fragment output."""

from __future__ import annotations

import re

import flowyaml


def test_fragment_has_no_document_chrome(parity_source):
    fragment = flowyaml.render(parity_source, output="fragment", instance_id="fy-a")
    for forbidden in ("<!doctype", "<html", "</html>", "<head", "<body", "<title"):
        assert forbidden not in fragment.lower()


def test_fragment_carries_its_own_style_data_and_runtime(parity_source):
    fragment = flowyaml.render(parity_source, output="fragment", instance_id="fy-a")
    assert fragment.count("<style>") == 1
    assert '<div id="fy-a" class="fy-root"' in fragment
    assert '<script id="fy-a-data" type="application/json">' in fragment
    assert "elkjs 0.9.3" in fragment
    assert 'var DATA_ID = "fy-a-data";' in fragment


def test_every_css_rule_is_scoped_to_the_mount_root(parity_source):
    fragment = flowyaml.render(parity_source, output="fragment", instance_id="fy-a")
    sheet = re.search(r"<style>(.*?)</style>", fragment, re.DOTALL).group(1)

    # Strip comments and at-rule headers, then check every remaining selector.
    body = re.sub(r"/\*.*?\*/", "", sheet, flags=re.DOTALL)
    body = re.sub(r"@media[^{]*\{", "", body)
    selectors = re.findall(r"(^|\})\s*([^{}@]+)\{", body)
    assert selectors
    for _, selector in selectors:
        selector = selector.strip()
        if not selector:
            continue
        for part in selector.split(","):
            assert part.strip().startswith("#fy-a"), part


def test_two_fragments_share_one_page_without_collisions(parity_source):
    first = flowyaml.render(parity_source, output="fragment", instance_id="fy-one")
    second = flowyaml.render(parity_source, output="fragment", instance_id="fy-two")
    page = first + second

    ids = re.findall(r'id="([^"]+)"', page)
    assert len(ids) == len(set(ids)), ids
    assert 'id="fy-one"' in page and 'id="fy-two"' in page
    assert 'id="fy-one-data"' in page and 'id="fy-two-data"' in page


def test_fragment_hash_key_is_instance_scoped(parity_source):
    fragment = flowyaml.render(parity_source, output="fragment", instance_id="fy-a")
    payload = re.search(
        r'<script id="fy-a-data" type="application/json">(.*?)</script>',
        fragment,
        re.DOTALL,
    ).group(1)
    import json

    data = json.loads(payload)
    assert data["hashKey"] == "fy-a"
    assert data["output"] == "fragment"


def test_document_hash_key_is_the_stable_word_model(parity_source):
    import json

    html = flowyaml.render(parity_source, instance_id="fy-doc")
    payload = re.search(
        r'<script id="fy-doc-data" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    ).group(1)
    assert json.loads(payload)["hashKey"] == "model"


def test_elk_bundle_is_guarded_against_double_evaluation(parity_source):
    fragment = flowyaml.render(parity_source, output="fragment", instance_id="fy-a")
    assert 'if (typeof window.ELK === "undefined") {' in fragment


def test_fragment_is_pure_ascii_outside_of_nothing(parity_source):
    """A host page may declare any encoding, so the fragment stays ASCII."""
    fragment = flowyaml.render(parity_source, output="fragment", instance_id="fy-a")
    fragment.encode("ascii")
