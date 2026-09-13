"""Shared pytest fixtures for the FlowYAML test suite."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

EXAMPLES = REPO_ROOT / "examples"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
IMPORT_FIXTURES = FIXTURES / "import"


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def examples_dir() -> Path:
    return EXAMPLES


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def import_fixtures_dir() -> Path:
    """Mermaid and BPMN sources used by the importer suites."""
    return IMPORT_FIXTURES


@pytest.fixture(scope="session")
def parity_path() -> Path:
    """The multi-document parity source with every v0 feature."""
    return EXAMPLES / "distribution.yaml"


@pytest.fixture(scope="session")
def parity_source(parity_path: Path) -> str:
    return parity_path.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def minimal_source() -> str:
    return (EXAMPLES / "minimal.yaml").read_text(encoding="utf-8")


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def parity_document(parity_source: str, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A rendered standalone document, built once for the whole session."""
    import flowyaml

    target = tmp_path_factory.mktemp("artifacts") / "distribution.html"
    target.write_text(
        flowyaml.render(parity_source, instance_id="fy-suite"), encoding="utf-8"
    )
    return target
