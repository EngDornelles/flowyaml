# FlowYAML v0 Import Reference

FlowYAML v0 reads two foreign notations and turns them into its own validated
model: **Mermaid flowcharts** and **BPMN 2.0 XML**.

```python
import flowyaml as fyml

graph = fyml.read_mermaid("workflow.mmd")
other = fyml.read_bpmn("process.bpmn")

fyml.write_html(graph, "workflow.html")
open("workflow.yaml", "w", encoding="utf-8").write(fyml.to_yaml(graph))
```

Both return the same `Diagram` that `load()` returns, so `render`,
`write_html`, `validate`, `models` and `to_yaml` accept it directly.

## Two rules that hold for every importer

1. **The output is always valid.** An importer builds plain FlowYAML
   documents, serializes them with the canonical serializer, and runs them
   through the same loader and validator as a hand written source. There is no
   second code path, so `validate(read_mermaid(...)) == ()` is a property of
   the design, not a promise.
2. **No geometry, ever.** Nothing an importer writes describes a position, a
   size or any other `ui` metadata. FlowYAML measures wrapped labels in the
   browser and runs ELK there, so a stored coordinate would only fight the
   layout engine. BPMN's entire `bpmndi:BPMNDiagram` section is read past and
   discarded.

Identifiers are preserved when they are safe. A Mermaid `check_stock` and a
BPMN `Activity_0x9f2c` stay exactly themselves. Only characters outside
`A-Z a-z 0-9 _ . : -` are folded to `_`, a leading digit gains an `n` prefix,
and a collision gains a `_2`, `_3` suffix in source order.

Edge text is split the same way in both importers: text of 24 characters or
less on one line becomes a `tag`, which the renderer draws verbatim as the
canvas chip. Anything longer or multi-line becomes a `label`, which the
renderer shortens for the chip and shows in full on hover. Neither branch
loses text.

## Mermaid

Supported diagram declarations: `graph`, `flowchart` and `flowchart-elk`, with
an optional `TB`, `TD`, `BT`, `RL` or `LR` direction. The direction is kept as
`meta.source_direction` for provenance; FlowYAML always lays out to the right.

### Shapes

| Mermaid | FlowYAML type |
| --- | --- |
| `A[Text]` rectangle | `task` |
| `A(Text)` rounded | `task` |
| `A([Text])` stadium | event, resolved by degree |
| `A((Text))` circle | event, resolved by degree |
| `A(((Text)))` double circle | `endEvent` |
| `A{Text}` rhombus | `gateway` |
| `A{{Text}}` hexagon | `gateway` |
| `A[[Text]]` subroutine | `subprocess` |
| `A[(Text)]` cylinder | `state` |
| `A[/Text/]`, `A[\Text\]`, `A[/Text\]`, `A[\Text/]` | `state` |
| `A>Text]` asymmetric | `intermediateEvent` |
| bare `A` with no shape | `task` |

"Resolved by degree" means a stadium or a circle becomes a `startEvent` when
nothing reaches it, an `endEvent` when nothing leaves it, and an
`intermediateEvent` otherwise. Mermaid uses one shape for the whole event
family, so the graph is the only thing that can tell them apart.

The **first** explicit declaration of a node wins. A later bare reference in a
chain never erases a shape or a label.

### Links

| Mermaid | FlowYAML |
| --- | --- |
| `-->`, `---`, `--->`, `--o`, `--x`, `<-->` | `sequence` / `solid` |
| `==>`, `===` thick | `sequence` / `solid` |
| `-.->`, `-.-`, `-..->` dotted | `association` / `dotted` |
| `~~~` invisible | `association` / `dotted` |

Edge text is read from `-->|text|`, `-- text -->`, `== text ==>` and
`-. text .->`. Chains (`A --> B --> C`) and `&` groups (`A & B --> C & D`)
expand to every pair, in source order.

A bidirectional `<-->` becomes one edge in the written direction; v0 has no
two-headed arrow.

### Everything else

- YAML frontmatter is read for `title`, which becomes `meta.name`.
- `%%` comments and `%%{init: ...}%%` directives are discarded.
- `classDef`, `class`, `style`, `linkStyle`, `click`, `:::class` and the
  accessibility statements are read and discarded: FlowYAML owns its theme.
- `subgraph` flattens. Every node keeps its subgraph in a non-rendering
  `group` key, and the document keeps a `groups` list of ids and titles. A
  node belongs to the subgraph that mentions it first, which is Mermaid's own
  rule. v0 has no group shape, so a subgraph itself cannot be an edge
  endpoint; that is refused rather than guessed at.
- `;` separates statements, except inside a shape, so `A[Ledger &amp; audit]`
  survives.

### Refused

Any other diagram type (`sequenceDiagram`, `classDiagram`, `gantt`, ...), a
missing `graph`/`flowchart` declaration, an unclosed shape or edge text, a
self-loop, an unbalanced `subgraph`/`end`, a subgraph used as an edge
endpoint, and the Mermaid 11 `A@{ shape: ... }` extended syntax.

The `o--o` and `x--x` bidirectional forms are **not** supported: their leading
marker is indistinguishable from an identifier that ends in `o` or `x`, so it
is read as part of the identifier. Write `--o` or `--x` instead.

## BPMN 2.0 XML

Elements are matched by local name, so `bpmn:`, `bpmn2:`, `semantic:` and a
default namespace all read the same.

### Elements

| BPMN | FlowYAML type |
| --- | --- |
| `startEvent` | `startEvent` |
| `endEvent` | `endEvent` |
| `intermediateCatchEvent`, `intermediateThrowEvent`, `implicitThrowEvent`, `boundaryEvent` | `intermediateEvent` |
| `task`, `userTask`, `manualTask`, `serviceTask`, `scriptTask`, `businessRuleTask`, `sendTask`, `receiveTask` | `task` |
| `subProcess`, `transaction`, `adHocSubProcess`, `callActivity` | `subprocess` |
| `exclusiveGateway`, `inclusiveGateway`, `parallelGateway`, `eventBasedGateway`, `complexGateway` | `gateway` |
| `dataObjectReference`, `dataStoreReference`, `textAnnotation` | `state` |

Each node keeps its BPMN element name in a non-rendering `bpmn` key, and its
lane name in a `lane` key when the process declares lanes. Lanes also become
the document's `actors` list, which v0 preserves without rendering swimlanes.

### Levels

Every `process` that declares a flow node becomes one model. An **expanded**
`subProcess` becomes a model of its own, and the node that contained it
becomes a `subprocess` card whose `ref` opens that model, so BPMN nesting
arrives as FlowYAML's own in-document navigation. A **collapsed**
`subProcess` is a plain destination card with no `ref`. A `callActivity`
whose `calledElement` names a process in the same file gets that `ref` too.

A process with no flow node produces no model, which is what an empty pool for
a black box participant should do. A `participant` name titles the process it
references.

### Edges

| BPMN | FlowYAML |
| --- | --- |
| `sequenceFlow` | `sequence` / `solid`; `@name` becomes the tag or label |
| `association` | `association` / `dotted` |
| `dataInputAssociation`, `dataOutputAssociation` | `association` / `dotted`, between the data reference and the activity |
| `boundaryEvent@attachedToRef` | `association` / `dotted`, from the activity to the event |
| `messageFlow` | `association` / `dotted`, only when both ends sit in one model |

A `sequenceFlow` carries the process, so a missing or unresolved end is an
error. The four decorative kinds above are dropped instead when an end lives
in another level, and duplicates collapse.

### Labels

`@name` becomes the label. A `textAnnotation` uses its `text` child.
`documentation` becomes the `detail` tooltip. An unnamed gateway or
intermediate event keeps an empty label, which is exactly FlowYAML's connector
idiom; every other unnamed element falls back to its BPMN id rather than
inventing text.

### Ignored

`bpmndi:BPMNDiagram` and everything under it, `extensionElements`,
`ioSpecification`, `property`, `dataObject`, `incoming`/`outgoing`, `group`,
loop characteristics and resource roles.

### Refused

XML that does not parse, a root that is not `definitions`, a file with no
process, a file where no process declares a flow node, an unmapped element
whose name still reads like a flow node (so a step is never silently lost), a
`sequenceFlow` with a missing or unresolved end, a self-loop, a duplicated
flow element id, and any document that declares a DTD. A DTD is refused rather
than expanded because `xml.etree.ElementTree` resolves internal entities, and
a BPMN file has no legitimate use for one.

## Command line

```bash
flowyaml import workflow.mmd -o workflow.yaml
flowyaml import process.bpmn --format bpmn > process.yaml
flowyaml import process.bpmn --id intake --name "Intake flow" -o intake.yaml
flowyaml render workflow.yaml -o workflow.html
```

The format is inferred from the suffix (`.mmd`, `.mermaid`; `.bpmn`,
`.bpmn20.xml`, `.xml`) and can be forced with `--format`. Exit codes match the
rest of the CLI: `0` success, `1` import failure, `2` usage.

## What an import is not

An importer is a translator into the v0 graph model, not a compliance layer.
FlowYAML still renders seven node types, two edge kinds and two edge styles;
it still has no swimlane, no group shape, no pool boundary and no BPMN
execution semantics. What a notation says beyond that is preserved where it
fits a non-rendering key, and refused where it would change the contract.

## Examples

- `examples/onboarding.mmd` exercises the Mermaid surface above.
- `examples/order_handling.bpmn` exercises the BPMN surface, including an
  expanded sub-process, lanes, a boundary event, a data association, a text
  annotation and a `bpmndi` section that is read past.
