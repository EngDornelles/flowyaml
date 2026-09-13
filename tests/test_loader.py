"""Multi-document parsing and YAML source positions."""

from __future__ import annotations

import pytest

from flowyaml.loader import parse_documents


def test_parses_every_document_in_a_stream():
    documents, issues = parse_documents("a: 1\n---\nb: 2\n---\nc: 3\n")
    assert not issues
    assert [document.data for document in documents] == [{"a": 1}, {"b": 2}, {"c": 3}]
    assert [document.index for document in documents] == [0, 1, 2]


def test_blank_documents_are_kept_but_marked():
    documents, issues = parse_documents("---\n---\nmeta: {}\n")
    assert not issues
    # The first marker opens an empty document, the second opens the populated one.
    assert [document.is_blank for document in documents] == [True, False]


def test_positions_point_at_the_offending_scalar():
    source = "meta:\n  id: procurement\nnodes:\n  - id: start\n    type: task\n"
    documents, issues = parse_documents(source)
    assert not issues
    document = documents[0]
    assert document.position("meta", "id") == (2, 7)
    assert document.position("nodes", 0, "type") == (5, 11)


def test_position_falls_back_to_the_nearest_known_parent():
    documents, _ = parse_documents("meta:\n  id: x\n")
    document = documents[0]
    # 'name' was never written, so the mapping's own position is reported.
    assert document.position("meta", "name") == document.position("meta")


def test_syntax_error_is_reported_with_a_position():
    documents, issues = parse_documents("meta:\n  id: ok\n\tbad: tab\n")
    assert issues
    issue = issues[0]
    assert issue.code == "yaml.syntax"
    assert issue.line is not None and issue.line >= 1
    assert issue.column is not None


def test_recursive_anchors_are_rejected_rather_than_hanging():
    documents, issues = parse_documents("&loop\nself: *loop\n")
    assert issues
    assert issues[0].code in ("yaml.unsupported", "yaml.syntax")


@pytest.mark.parametrize(
    "source, expected",
    [
        ("value: 1\n", 1),
        ("value: '1'\n", "1"),
        ("value: true\n", True),
        ("value: 1.5\n", 1.5),
        ("value: null\n", None),
    ],
)
def test_scalars_keep_yaml_typing(source, expected):
    documents, issues = parse_documents(source)
    assert not issues
    assert documents[0].data["value"] == expected
