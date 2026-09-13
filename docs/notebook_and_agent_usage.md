# Notebook and agent usage

FlowYAML is a Python library with a deterministic command-line interface. It
does not depend on Jupyter, IPython, an LLM framework, or an agent runtime.

## Notebook kernel

Install FlowYAML into the environment backing the selected notebook kernel:

```python
%pip install flowyaml
```

During repository development, use an editable install instead:

```python
%pip install -e "/path/to/flowyaml"
```

Restart the kernel after installation. The notebook server may live in a
different environment; only the active kernel needs FlowYAML.

```python
from pathlib import Path

import flowyaml

source = Path("flow.yaml")
issues = flowyaml.validate(source)
if issues:
    raise ValueError("\n".join(str(issue) for issue in issues))

artifact = flowyaml.write_html(source, "flow.html")
artifact
```

The most reliable notebook preview is the written standalone HTML file. A
notebook frontend may sanitize or decline to execute JavaScript inserted
directly into a cell, while the standalone file contains everything it needs.
In Jupyter, an iframe can display a file reachable through the notebook server:

```python
from IPython.display import IFrame

IFrame("flow.html", width="100%", height=720)
```

IPython is needed only for that display helper and is not a FlowYAML dependency.

## LLM or agent invocation

Give an agent the FlowYAML contract or point it to `README.md` and
`docs/flowyaml_v0_spec.md`. The stable command sequence is:

```bash
flowyaml validate flow.yaml
flowyaml render flow.yaml -o flow.html
```

Validation exits with status `0` when the source is valid and status `1` when
it reports issues. Rendering also fails rather than producing a partial graph.
This makes both commands safe to wrap as subprocess tools.

For machine-side integration, prefer the Python API. Validation issues are
frozen dataclasses with stable fields:

```python
from dataclasses import asdict

import flowyaml

result = {
    "valid": not (issues := flowyaml.validate("flow.yaml")),
    "issues": [asdict(issue) for issue in issues],
}
```

Useful deterministic discovery commands are:

```bash
flowyaml --version
flowyaml --help
flowyaml models flow.yaml
flowyaml themes
flowyaml data flow.yaml -o flow.data.json
```

An agent may also import supported Mermaid or BPMN input before validation and
rendering:

```bash
flowyaml import process.bpmn -o process.yaml
flowyaml validate process.yaml
flowyaml render process.yaml -o process.html
```

Treat `flowyaml serve` as a local authoring helper. It has no authentication and
must not be exposed as a production or untrusted-network service.
