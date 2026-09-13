"""Command line interface behaviour and exit codes."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import flowyaml
from flowyaml.cli import main


def run_module(repo_root: Path, *args: str) -> subprocess.CompletedProcess:
    """Run the real entry point in a child process, as a user would."""
    env = {
        **dict(__import__("os").environ),
        "PYTHONPATH": str(repo_root / "src"),
        "PYTHONIOENCODING": "utf-8",
    }
    return subprocess.run(
        [sys.executable, "-m", "flowyaml", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=repo_root,
    )


def test_module_entry_point_reports_version(repo_root):
    result = run_module(repo_root, "--version")
    assert result.returncode == 0
    assert f"flowyaml {flowyaml.__version__}" in result.stdout


def test_render_writes_a_document(tmp_path, parity_path, repo_root):
    target = tmp_path / "flow.html"
    result = run_module(
        repo_root, "render", str(parity_path), "-o", str(target), "--instance-id", "fy-cli"
    )
    assert result.returncode == 0, result.stderr
    assert "wrote" in result.stdout
    assert target.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_render_writes_to_stdout_when_no_output_given(capsys, parity_path):
    assert main(["render", str(parity_path), "--instance-id", "fy-out"]) == 0
    assert capsys.readouterr().out.startswith("<!doctype html>")


def test_stdout_is_utf8_whatever_the_console_codepage_is(tmp_path, repo_root, fixtures_dir):
    """Regression: the artifact declares UTF-8, so stdout must emit UTF-8.

    Rendering to a file always wrote UTF-8, but the stdout path used the
    locale codec. On a cp1252 console that turned accented labels into
    bytes the browser then read as mojibake, which is exactly the shape of
    the originating source.
    """
    env = {
        **dict(__import__("os").environ),
        "PYTHONPATH": str(repo_root / "src"),
        "PYTHONIOENCODING": "cp1252",
    }
    source = fixtures_dir / "accented_labels.yaml"
    result = subprocess.run(
        [sys.executable, "-m", "flowyaml", "render", str(source)],
        capture_output=True,          # bytes, deliberately not decoded here
        env=env,
        cwd=repo_root,
    )
    assert result.returncode == 0, result.stderr
    document = result.stdout.decode("utf-8")   # raises on any locale bytes
    assert "Distribuição" in document
    assert "�" not in document


def test_render_fragment_mode(capsys, parity_path):
    assert main(
        ["render", str(parity_path), "--output", "fragment", "--instance-id", "fy-frag"]
    ) == 0
    out = capsys.readouterr().out
    assert out.startswith("<style>")
    assert "<!doctype" not in out


def test_render_selects_a_model(capsys, parity_path):
    assert main(["render", str(parity_path), "-m", "dispatch", "--instance-id", "fy-m"]) == 0
    assert "<title>Dispatch and handover</title>" in capsys.readouterr().out


def test_render_rejects_an_unknown_model(capsys, parity_path):
    assert main(["render", str(parity_path), "-m", "nope"]) == 1
    assert "not in this source" in capsys.readouterr().err


def test_validate_reports_success(capsys, parity_path):
    assert main(["validate", str(parity_path)]) == 0
    assert "is valid" in capsys.readouterr().out


def test_validate_reports_structured_issues(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("meta:\n  name: no id\nnodes: []\nedges: []\n", encoding="utf-8")
    assert main(["validate", str(bad)]) == 1
    err = capsys.readouterr().err
    assert "[meta.id.missing]" in err
    assert "1 issue in" in err


def test_models_lists_every_level(capsys, parity_path):
    assert main(["models", str(parity_path)]) == 0
    out = capsys.readouterr().out
    assert "distribution\tMaterial distribution" in out
    assert out.strip().count("\n") == 3


def test_themes_marks_the_default(capsys):
    assert main(["themes"]) == 0
    assert capsys.readouterr().out.strip() == "dornelles_multitech (default)"


def test_missing_file_is_a_clean_failure(capsys, tmp_path):
    assert main(["validate", str(tmp_path / "absent.yaml")]) == 1
    assert "cannot read" in capsys.readouterr().err


def test_unknown_option_value_is_a_usage_error(parity_path):
    with pytest.raises(SystemExit) as caught:
        main(["render", str(parity_path), "--output", "pdf"])
    assert caught.value.code == 2


# --------------------------------------------------------------------------- #
# import
# --------------------------------------------------------------------------- #


def test_import_infers_mermaid_from_the_suffix(capsys, examples_dir):
    assert main(["import", str(examples_dir / "onboarding.mmd")]) == 0
    out = capsys.readouterr().out
    assert "source_format: mermaid" in out
    assert "id: onboarding" in out


def test_import_infers_bpmn_from_the_suffix(capsys, examples_dir):
    assert main(["import", str(examples_dir / "order_handling.bpmn")]) == 0
    out = capsys.readouterr().out
    assert "source_format: bpmn" in out
    assert out.count("meta:") == 2


def test_import_writes_a_file_and_reports_the_model_count(
    tmp_path, capsys, examples_dir
):
    target = tmp_path / "order.yaml"
    assert main(
        ["import", str(examples_dir / "order_handling.bpmn"), "-o", str(target)]
    ) == 0
    assert "2 models" in capsys.readouterr().out
    assert main(["validate", str(target)]) == 0


def test_an_imported_file_renders_through_the_normal_pipeline(
    tmp_path, capsys, examples_dir
):
    yaml_path = tmp_path / "onboarding.yaml"
    assert main(["import", str(examples_dir / "onboarding.mmd"), "-o", str(yaml_path)]) == 0
    capsys.readouterr()
    html_path = tmp_path / "onboarding.html"
    assert main(["render", str(yaml_path), "-o", str(html_path), "--instance-id", "fy-i"]) == 0
    assert html_path.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_import_accepts_an_explicit_format(capsys, tmp_path):
    source = tmp_path / "flow.txt"
    source.write_text("flowchart LR\n    a[A] --> b[B]\n", encoding="utf-8")
    assert main(["import", str(source), "--format", "mermaid"]) == 0
    assert "id: flow" in capsys.readouterr().out


def test_import_can_set_the_model_id_and_name(capsys, examples_dir):
    assert main(
        [
            "import",
            str(examples_dir / "onboarding.mmd"),
            "--id",
            "intake",
            "--name",
            "Intake flow",
        ]
    ) == 0
    out = capsys.readouterr().out
    assert "id: intake" in out
    assert "name: Intake flow" in out


def test_import_refuses_an_unknown_suffix(capsys, tmp_path):
    source = tmp_path / "flow.txt"
    source.write_text("flowchart LR\n    a[A] --> b[B]\n", encoding="utf-8")
    assert main(["import", str(source)]) == 2
    assert "cannot infer the import format" in capsys.readouterr().err


def test_import_reports_a_parse_failure_on_stderr(capsys, tmp_path):
    source = tmp_path / "broken.mmd"
    source.write_text("sequenceDiagram\n    A->>B: hi\n", encoding="utf-8")
    assert main(["import", str(source)]) == 1
    assert "mermaid import failed" in capsys.readouterr().err


def test_import_reports_a_missing_file(capsys, tmp_path):
    assert main(["import", str(tmp_path / "absent.bpmn")]) == 1
    assert "cannot read" in capsys.readouterr().err


def test_import_rejects_an_unknown_format_as_a_usage_error(examples_dir):
    with pytest.raises(SystemExit) as caught:
        main(["import", str(examples_dir / "onboarding.mmd"), "--format", "visio"])
    assert caught.value.code == 2


def test_import_through_the_real_entry_point(repo_root, tmp_path):
    target = tmp_path / "onboarding.yaml"
    result = run_module(
        repo_root,
        "import",
        str(repo_root / "examples" / "onboarding.mmd"),
        "-o",
        str(target),
    )
    assert result.returncode == 0, result.stderr
    assert "1 model" in result.stdout
    assert "Supplier onboarding" in target.read_text(encoding="utf-8")
