# Changelog

All notable FlowYAML changes are recorded here.

## 0.1.0.0 - 2026-09-13

First public-package candidate and second implementation build.

- Render YAML-defined process flows as standalone, self-sufficient HTML.
- Render instance-scoped fragments for host applications.
- Keep an HTTP-served page linked to an actively edited YAML source.
- Import supported Mermaid flowcharts and BPMN 2.0 XML into the FlowYAML model.
- Navigate embedded subprocess levels without network access.
- Provide a Python API and `flowyaml` command-line interface.
- Bundle `elkjs` 0.9.3 with its EPL-2.0 notice for offline layout.
- Cover rendering, validation, serialization, imports, live updates, browser
  behavior, accessibility, and offline operation with automated tests.

The internal `0.0.0.0` build used YAML-linked delivery by default and did not
yet include standalone HTML output.
