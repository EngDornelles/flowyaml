from __future__ import annotations

import json

import flowyaml


def test_quest_for_x_directory_contains_only_published_example_files(examples_dir):
    directory = examples_dir / "notebooks" / "quest_for_x"

    assert {path.name for path in directory.iterdir()} == {
        "build_quest_for_x.ipynb",
        "quest_for_x.html",
        "quest_for_x.yaml",
    }


def test_quest_for_x_yaml_is_valid_and_navigable(examples_dir):
    source = examples_dir / "notebooks" / "quest_for_x" / "quest_for_x.yaml"

    assert flowyaml.validate(source) == ()
    assert flowyaml.models(source) == (
        "quest_for_x",
        "vandermonde_passage",
        "solver_guild",
        "residual_guardian",
    )

    html = flowyaml.render_file(
        source,
        model_id="quest_for_x",
        instance_id="quest-for-x-test",
    )
    assert "The Quest for x" in html
    assert "vandermonde_passage" in html
    assert "residual_guardian" in html


def test_quest_for_x_notebook_is_clean_and_uses_the_public_api(examples_dir):
    path = examples_dir / "notebooks" / "quest_for_x" / "build_quest_for_x.ipynb"
    notebook = json.loads(path.read_text(encoding="utf-8"))
    code = "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    )

    assert notebook["nbformat"] == 4
    assert "flowyaml.validate(source)" in code
    assert "flowyaml.models(source)" in code
    assert "flowyaml.write_html(" in code
    assert all(cell.get("execution_count") is None for cell in notebook["cells"] if cell["cell_type"] == "code")
    assert all(not cell.get("outputs") for cell in notebook["cells"] if cell["cell_type"] == "code")
