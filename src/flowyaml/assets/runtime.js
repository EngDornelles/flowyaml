/* FlowYAML v0 browser runtime.
 *
 * One immediately invoked function per mounted instance. The only global it
 * reads is window.ELK, provided by the vendored bundle. Every identifier it
 * creates (DOM ids, SVG marker ids, listeners, navigation state) is derived
 * from the instance prefix, so several instances can share one page.
 *
 * All label text reaches the DOM through textContent or createTextNode.
 * Nothing from the YAML source is ever assigned to innerHTML.
 */
(function () {
  "use strict";

  var DATA_ID = "__FLOWYAML_DATA_ID__";

  var SVG_NS = "http://www.w3.org/2000/svg";
  var MIN_SCALE = 0.2;
  var MAX_SCALE = 2.6;
  var FIT_MAX_SCALE = 1.4;
  var FIT_MARGIN = 28;
  var LINE_HEIGHT = 16;
  var CORNER_RADIUS = 6;
  var PAN_STEP = 48;
  var CLICK_SLOP = 4;

  /* Per type geometry. Sizes are computed from the wrapped label so the
     browser's own font metrics decide the box, exactly as the source app did. */
  var GEOMETRY = {
    task: { maxText: 190, padX: 16, padY: 12, minW: 132, minH: 52, shape: "card" },
    state: { maxText: 190, padX: 16, padY: 12, minW: 132, minH: 52, shape: "card" },
    subprocess: { maxText: 190, padX: 18, padY: 14, minW: 148, minH: 60, shape: "card" },
    startEvent: { maxText: 150, padX: 18, padY: 12, minW: 104, minH: 46, shape: "stadium" },
    endEvent: { maxText: 150, padX: 18, padY: 12, minW: 104, minH: 46, shape: "stadium" },
    intermediateEvent: {
      maxText: 150, padX: 20, padY: 13, minW: 108, minH: 50, shape: "stadium"
    },
    gateway: { maxText: 132, padX: 14, padY: 12, minW: 104, minH: 76, shape: "diamond" }
  };

  var GLYPH = {
    startEvent: "\u25B6",
    endEvent: "\u25A0",
    intermediateEvent: "\u25CE"
  };

  var boot = document.getElementById(DATA_ID);
  if (!boot) {
    return;
  }

  var config;
  try {
    config = JSON.parse(boot.textContent || "{}");
  } catch (error) {
    return;
  }

  var root = document.getElementById(config.instance);
  if (!root) {
    return;
  }

  var strings = config.strings || {};

  /* Linked mode: the models are not embedded. A companion loader (live.js)
     fetches them from the host and hands them over through a DOM event on
     this instance's root, so this file never touches the network itself. */
  var linked =
    config.source && config.source.data ? config.source : null;

  var models = {};
  var modelOrder = [];

  function adoptModels(list) {
    models = {};
    modelOrder = [];
    var index;
    var incoming = list || [];
    for (index = 0; index < incoming.length; index += 1) {
      if (!incoming[index] || !incoming[index].id) {
        continue;
      }
      models[incoming[index].id] = incoming[index];
      modelOrder.push(incoming[index].id);
    }
  }

  adoptModels(config.models);

  /* ------------------------------------------------------------------ DOM */

  function el(tag, className) {
    var node = document.createElement(tag);
    if (className) {
      node.className = className;
    }
    return node;
  }

  function svg(tag, className) {
    var node = document.createElementNS(SVG_NS, tag);
    if (className) {
      node.setAttribute("class", className);
    }
    return node;
  }

  function text(node, value) {
    node.textContent = value == null ? "" : String(value);
    return node;
  }

  function attrs(node, table) {
    var key;
    for (key in table) {
      if (Object.prototype.hasOwnProperty.call(table, key)) {
        node.setAttribute(key, String(table[key]));
      }
    }
    return node;
  }

  function clear(node) {
    while (node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  function clamp(value, low, high) {
    return value < low ? low : value > high ? high : value;
  }

  function id(suffix) {
    return config.instance + "-" + suffix;
  }

  /* -------------------------------------------------------- text measuring */

  var measureContext = null;
  var measureCache = {};

  function fontStack() {
    var computed = window.getComputedStyle(root).getPropertyValue("--fy-font-sans");
    return (computed || "sans-serif").trim() || "sans-serif";
  }

  function measure(value, weight, size) {
    var font = weight + " " + size + "px " + fontStack();
    var key = font + "\u0000" + value;
    if (measureCache[key] !== undefined) {
      return measureCache[key];
    }
    if (measureContext === null) {
      try {
        measureContext = document.createElement("canvas").getContext("2d");
      } catch (error) {
        measureContext = false;
      }
    }
    var width;
    if (measureContext) {
      measureContext.font = font;
      width = measureContext.measureText(value).width;
    } else {
      width = value.length * size * 0.55;
    }
    measureCache[key] = width;
    return width;
  }

  function wrap(value, maxWidth, weight, size) {
    var normalized = String(value == null ? "" : value).replace(/\s+/g, " ").trim();
    if (!normalized) {
      return [];
    }
    var words = normalized.split(" ");
    var lines = [];
    var current = "";
    var index;

    for (index = 0; index < words.length; index += 1) {
      var word = words[index];
      var candidate = current ? current + " " + word : word;
      if (measure(candidate, weight, size) <= maxWidth || !current) {
        if (!current && measure(word, weight, size) > maxWidth) {
          var broken = breakWord(word, maxWidth, weight, size);
          var last = broken.pop();
          lines = lines.concat(broken);
          current = last;
          continue;
        }
        current = candidate;
      } else {
        lines.push(current);
        current = word;
        if (measure(word, weight, size) > maxWidth) {
          var pieces = breakWord(word, maxWidth, weight, size);
          current = pieces.pop();
          lines = lines.concat(pieces);
        }
      }
    }
    if (current) {
      lines.push(current);
    }
    return lines;
  }

  function breakWord(word, maxWidth, weight, size) {
    var out = [];
    var buffer = "";
    var index;
    for (index = 0; index < word.length; index += 1) {
      var next = buffer + word.charAt(index);
      if (buffer && measure(next, weight, size) > maxWidth) {
        out.push(buffer);
        buffer = word.charAt(index);
      } else {
        buffer = next;
      }
    }
    out.push(buffer);
    return out;
  }

  function widestLine(lines, weight, size) {
    var widest = 0;
    var index;
    for (index = 0; index < lines.length; index += 1) {
      widest = Math.max(widest, measure(lines[index], weight, size));
    }
    return widest;
  }

  /* --------------------------------------------------------- node geometry */

  function sizeNode(node) {
    var spec = GEOMETRY[node.type] || GEOMETRY.task;
    var lines = wrap(node.label, spec.maxText, "500", 12.5);
    var textWidth = widestLine(lines, "500", 12.5);
    var textHeight = Math.max(LINE_HEIGHT, lines.length * LINE_HEIGHT);
    var width;
    var height;

    if (spec.shape === "diamond") {
      /* A rectangle of tw x th fits a diamond of W x H when tw/W + th/H <= 1.
         Fix the height first, then solve for the width that keeps the label
         inside the rhombus rather than clipping its corners. */
      height = Math.max(spec.minH, textHeight + 44);
      var ratio = 1 - textHeight / height;
      width = Math.max(spec.minW, Math.ceil(textWidth / Math.max(ratio, 0.35)) + spec.padX);
    } else {
      var glyphRoom = GLYPH[node.type] ? 22 : 0;
      var markerRoom = node.type === "subprocess" ? 10 : 0;
      width = Math.max(spec.minW, Math.ceil(textWidth) + spec.padX * 2 + glyphRoom);
      height = Math.max(spec.minH, textHeight + spec.padY * 2 + markerRoom);
    }

    return {
      width: Math.ceil(width),
      height: Math.ceil(height),
      lines: lines,
      shape: spec.shape,
      glyphRoom: GLYPH[node.type] ? 22 : 0
    };
  }

  function sizeChip(value) {
    var width = Math.ceil(measure(value, "600", 11)) + 16;
    return { width: Math.max(22, width), height: 19 };
  }

  /* ------------------------------------------------------------ page shell */

  root.setAttribute("data-fy-output", config.output || "document");

  var shell = el("div", "fy-shell");
  var toolbar = el("header", "fy-toolbar");
  var titleBlock = el("div", "fy-title-block");
  var modelName = el("span", "fy-model-name");
  var versionBadge = el("span", "fy-badge");
  var breadcrumb = el("nav", "fy-breadcrumb");
  breadcrumb.setAttribute("aria-label", strings.levels || "Flow levels");

  var controls = el("div", "fy-controls");
  var backButton = el("button", "fy-btn");
  backButton.type = "button";
  text(backButton, strings.back || "Back");
  backButton.setAttribute("aria-label", strings.backAria || "Go up one flow level");

  var zoomOut = el("button", "fy-btn");
  zoomOut.type = "button";
  text(zoomOut, "\u2212");
  zoomOut.setAttribute("aria-label", strings.zoomOut || "Zoom out");

  var zoomReadout = el("span", "fy-zoom-readout");
  text(zoomReadout, "100%");

  var zoomIn = el("button", "fy-btn");
  zoomIn.type = "button";
  text(zoomIn, "+");
  zoomIn.setAttribute("aria-label", strings.zoomIn || "Zoom in");

  var fitButton = el("button", "fy-btn");
  fitButton.type = "button";
  text(fitButton, strings.fit || "Fit");
  fitButton.setAttribute("aria-label", strings.fitAria || "Fit the diagram to the view");

  controls.appendChild(backButton);
  controls.appendChild(zoomOut);
  controls.appendChild(zoomReadout);
  controls.appendChild(zoomIn);
  controls.appendChild(fitButton);

  titleBlock.appendChild(modelName);
  titleBlock.appendChild(versionBadge);
  toolbar.appendChild(titleBlock);
  toolbar.appendChild(breadcrumb);
  toolbar.appendChild(controls);

  var canvas = el("div", "fy-canvas");
  var surface = svg("svg", "fy-svg");
  surface.setAttribute("role", "application");
  surface.setAttribute("tabindex", "0");
  surface.setAttribute("id", id("svg"));
  surface.setAttribute("aria-label", strings.canvasAria || "Process flow diagram");
  surface.setAttribute("preserveAspectRatio", "xMidYMid meet");

  var defs = svg("defs");
  surface.appendChild(defs);

  var viewport = svg("g", "fy-viewport");
  var edgeLayer = svg("g", "fy-edges");
  var nodeLayer = svg("g", "fy-nodes");
  var chipLayer = svg("g", "fy-chips");
  viewport.appendChild(edgeLayer);
  viewport.appendChild(nodeLayer);
  viewport.appendChild(chipLayer);
  surface.appendChild(viewport);

  var tooltip = el("div", "fy-tooltip");
  /* Purely visual: every detail it can show is already part of the accessible
     name of the node or chip that owns it, so announcing it again from a
     shared element would only duplicate or, worse, mismatch. */
  tooltip.setAttribute("aria-hidden", "true");
  tooltip.id = id("tooltip");
  tooltip.hidden = true;

  var status = el("div", "fy-status");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");

  var hint = el("div", "fy-hint");
  text(hint, strings.hint || "Drag to pan \u00b7 wheel to zoom \u00b7 Enter opens a subprocess");

  var empty = el("div", "fy-empty");
  empty.hidden = true;

  canvas.appendChild(surface);
  canvas.appendChild(tooltip);
  canvas.appendChild(status);
  canvas.appendChild(hint);
  canvas.appendChild(empty);

  /* ------------------------------------------------ next levels, and above */

  /* The drawer lists the subprocesses of the current level. They are already
     on the canvas, but only for a reader who can find them there; this is the
     same navigation for a keyboard, a screen reader and a narrow screen. */
  var nextDrawer = el("details", "fy-next");
  var nextSummary = el("summary", "fy-next-summary");
  var nextGrid = el("div", "fy-next-grid");
  nextDrawer.appendChild(nextSummary);
  nextDrawer.appendChild(nextGrid);
  nextDrawer.hidden = true;

  /* Where the reader came from: the toolbar breadcrumb, or a stripe of the
     levels above with a picture of the nearest one. One or the other, never
     both, because they answer the same question. */
  var levelsMode = config.levels === "snapshot" ? "snapshot" : "breadcrumb";
  var snapshots = {};
  var stripe = null;
  var levelCounter = null;

  if (levelsMode === "snapshot") {
    breadcrumb.hidden = true;
    levelCounter = el("span", "fy-level");
    titleBlock.appendChild(levelCounter);
    stripe = el("nav", "fy-stripe");
    stripe.setAttribute("aria-label", strings.previousLevels || "Previous levels");
  }

  shell.appendChild(toolbar);
  shell.appendChild(canvas);
  shell.appendChild(nextDrawer);
  clear(root);
  if (stripe) {
    root.appendChild(stripe);
  }
  root.appendChild(shell);

  buildMarkers();

  function buildMarkers() {
    var solid = svg("marker");
    attrs(solid, {
      id: id("arrow"),
      viewBox: "0 0 10 10",
      refX: "10",
      refY: "5",
      markerWidth: "9",
      markerHeight: "9",
      markerUnits: "userSpaceOnUse",
      orient: "auto-start-reverse"
    });
    var solidPath = svg("path", "fy-arrow");
    solidPath.setAttribute("d", "M0,1 L10,5 L0,9 Z");
    solid.appendChild(solidPath);

    var dotted = svg("marker");
    attrs(dotted, {
      id: id("arrow-assoc"),
      viewBox: "0 0 10 10",
      refX: "10",
      refY: "5",
      markerWidth: "9",
      markerHeight: "9",
      markerUnits: "userSpaceOnUse",
      orient: "auto-start-reverse"
    });
    var dottedPath = svg("path", "fy-arrow fy-arrow--dotted");
    dottedPath.setAttribute("d", "M0,1 L10,5 L0,9 Z");
    dotted.appendChild(dottedPath);

    defs.appendChild(solid);
    defs.appendChild(dotted);
  }

  /* ------------------------------------------------------------- node draw */

  function cardPath(width, height, radius) {
    var r = Math.min(radius, width / 2, height / 2);
    return (
      "M" + r + ",0 H" + (width - r) +
      " A" + r + "," + r + " 0 0 1 " + width + "," + r +
      " V" + (height - r) +
      " A" + r + "," + r + " 0 0 1 " + (width - r) + "," + height +
      " H" + r +
      " A" + r + "," + r + " 0 0 1 0," + (height - r) +
      " V" + r +
      " A" + r + "," + r + " 0 0 1 " + r + ",0 Z"
    );
  }

  function diamondPath(width, height) {
    return (
      "M" + width / 2 + ",0 L" + width + "," + height / 2 +
      " L" + width / 2 + "," + height +
      " L0," + height / 2 + " Z"
    );
  }

  function shapePath(shape, width, height) {
    if (shape === "diamond") {
      return diamondPath(width, height);
    }
    if (shape === "stadium") {
      return cardPath(width, height, height / 2);
    }
    return cardPath(width, height, 8);
  }

  function drawNode(node, layout) {
    var size = node.__size;
    var group = svg("g", "fy-node fy-node--" + node.type);
    group.setAttribute("transform", "translate(" + layout.x + "," + layout.y + ")");
    group.setAttribute("data-fy-node", node.id);

    var navigable = Boolean(node.ref && models[node.ref]);
    var destination = node.type === "subprocess" && !navigable;
    if (navigable) {
      group.setAttribute("class", "fy-node fy-node--subprocess fy-node--navigable");
      group.setAttribute("role", "button");
      group.setAttribute("tabindex", "0");
      group.setAttribute("aria-label", (strings.open || "Open subprocess") + ": " + node.label);
      group.setAttribute("data-fy-ref", node.ref);
    } else if (destination) {
      group.setAttribute("class", "fy-node fy-node--subprocess fy-node--destination");
      group.setAttribute("aria-label", (strings.destination || "Destination") + ": " + node.label);
    }

    var shape = svg("path", "fy-node-shape");
    shape.setAttribute("d", shapePath(size.shape, size.width, size.height));
    group.appendChild(shape);

    if (node.type === "intermediateEvent") {
      var inner = svg("path", "fy-node-shape-inner");
      inner.setAttribute(
        "d",
        shapePath("stadium", size.width - 8, size.height - 8)
      );
      inner.setAttribute("transform", "translate(4,4)");
      group.appendChild(inner);
    }

    var textLeft = size.glyphRoom;
    if (GLYPH[node.type]) {
      var glyph = svg("text", "fy-node-glyph");
      attrs(glyph, { x: 15, y: size.height / 2 });
      text(glyph, GLYPH[node.type]);
      group.appendChild(glyph);
    }

    var lines = size.lines;
    var block = svg("text", "fy-node-text");
    var centerX = textLeft ? textLeft + (size.width - textLeft) / 2 : size.width / 2;
    var firstY = size.height / 2 - ((lines.length - 1) * LINE_HEIGHT) / 2;
    if (node.type === "subprocess") {
      firstY -= 4;
    }
    attrs(block, { x: centerX, y: firstY });
    var lineIndex;
    for (lineIndex = 0; lineIndex < lines.length; lineIndex += 1) {
      var span = svg("tspan");
      attrs(span, { x: centerX, dy: lineIndex === 0 ? 0 : LINE_HEIGHT });
      text(span, lines[lineIndex]);
      block.appendChild(span);
    }
    group.appendChild(block);

    if (node.type === "subprocess") {
      /* BPMN style collapsed marker: meaning that does not depend on colour. */
      var marker = svg("g", "fy-node-marker");
      var box = svg("rect");
      attrs(box, {
        x: size.width / 2 - 6,
        y: size.height - 16,
        width: 12,
        height: 12,
        rx: 2
      });
      var plusH = svg("path");
      plusH.setAttribute(
        "d",
        "M" + (size.width / 2 - 3) + "," + (size.height - 10) +
        " H" + (size.width / 2 + 3)
      );
      var plusV = svg("path");
      plusV.setAttribute(
        "d",
        "M" + (size.width / 2) + "," + (size.height - 13) +
        " V" + (size.height - 7)
      );
      marker.appendChild(box);
      marker.appendChild(plusH);
      marker.appendChild(plusV);
      group.appendChild(marker);
    }

    var focusRing = svg("path", "fy-node-focus");
    focusRing.setAttribute(
      "d",
      shapePath(size.shape, size.width + 8, size.height + 8)
    );
    focusRing.setAttribute("transform", "translate(-4,-4)");
    group.appendChild(focusRing);

    if (node.detail) {
      group.setAttribute("data-fy-tooltip", node.detail);
      /* One instance owns exactly one tooltip element, and its text is
         whatever was pointed at last, so it cannot be a per-element
         aria-describedby target. The detail joins the accessible name of the
         element that owns it, which is stable and never borrows a neighbour's
         text. */
      if (navigable) {
        group.setAttribute(
          "aria-label",
          (strings.open || "Open subprocess") + ": " + node.label + ". " + node.detail
        );
      } else {
        group.setAttribute("tabindex", "0");
        group.setAttribute("role", "note");
        group.setAttribute("aria-label", node.label + ". " + node.detail);
      }
    }

    return group;
  }

  /* ------------------------------------------------------------- edge draw */

  function roundedPath(points) {
    if (points.length < 2) {
      return "";
    }
    var d = "M" + points[0].x + "," + points[0].y;
    var index;
    for (index = 1; index < points.length - 1; index += 1) {
      var previous = points[index - 1];
      var corner = points[index];
      var next = points[index + 1];
      var inLength = Math.hypot(corner.x - previous.x, corner.y - previous.y);
      var outLength = Math.hypot(next.x - corner.x, next.y - corner.y);
      var radius = Math.min(CORNER_RADIUS, inLength / 2, outLength / 2);
      if (radius < 0.5) {
        d += " L" + corner.x + "," + corner.y;
        continue;
      }
      var enterX = corner.x - ((corner.x - previous.x) / inLength) * radius;
      var enterY = corner.y - ((corner.y - previous.y) / inLength) * radius;
      var exitX = corner.x + ((next.x - corner.x) / outLength) * radius;
      var exitY = corner.y + ((next.y - corner.y) / outLength) * radius;
      d += " L" + enterX + "," + enterY;
      d += " Q" + corner.x + "," + corner.y + " " + exitX + "," + exitY;
    }
    var last = points[points.length - 1];
    d += " L" + last.x + "," + last.y;
    return d;
  }

  function sectionPoints(section) {
    var points = [section.startPoint];
    if (section.bendPoints) {
      points = points.concat(section.bendPoints);
    }
    points.push(section.endPoint);
    return points;
  }

  function drawEdge(edge, laidOut) {
    var group = svg("g", "fy-edge" + (edge.dotted ? " fy-edge--dotted" : ""));
    group.setAttribute("data-fy-edge", edge.id);
    var sections = laidOut.sections || [];
    var index;
    for (index = 0; index < sections.length; index += 1) {
      var points = sectionPoints(sections[index]);
      var d = roundedPath(points);
      if (!d) {
        continue;
      }
      var hit = svg("path", "fy-edge-hit");
      hit.setAttribute("d", d);
      group.appendChild(hit);

      var path = svg("path", "fy-edge-path");
      path.setAttribute("d", d);
      if (index === sections.length - 1) {
        path.setAttribute(
          "marker-end",
          "url(#" + (edge.dotted ? id("arrow-assoc") : id("arrow")) + ")"
        );
      }
      group.appendChild(path);
    }
    return group;
  }

  function chipCenter(edge, laidOut) {
    var labels = laidOut.labels || [];
    if (labels.length && typeof labels[0].x === "number") {
      return {
        x: labels[0].x + (labels[0].width || 0) / 2,
        y: labels[0].y + (labels[0].height || 0) / 2
      };
    }
    var sections = laidOut.sections || [];
    if (!sections.length) {
      return null;
    }
    var points = sectionPoints(sections[0]);
    var middle = Math.floor((points.length - 1) / 2);
    var a = points[middle];
    var b = points[middle + 1] || a;
    return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 - 12 };
  }

  function drawChip(edge, laidOut) {
    if (!edge.chip) {
      return null;
    }
    var center = chipCenter(edge, laidOut);
    if (!center) {
      return null;
    }
    var hasTooltip = Boolean(edge.tooltip);
    var size = sizeChip(edge.chip);
    var width = size.width + (hasTooltip ? 13 : 0);
    var height = size.height;

    var group = svg("g", "fy-chip" + (hasTooltip ? " fy-chip--detailed" : ""));
    group.setAttribute(
      "transform",
      "translate(" + (center.x - width / 2) + "," + (center.y - height / 2) + ")"
    );

    var box = svg("rect", "fy-chip-box");
    attrs(box, { x: 0, y: 0, width: width, height: height, rx: 4, ry: 4 });
    group.appendChild(box);

    var label = svg("text", "fy-chip-text");
    attrs(label, { x: (hasTooltip ? width - 13 : width) / 2, y: height / 2 + 0.5 });
    text(label, edge.chip);
    group.appendChild(label);

    if (hasTooltip) {
      var more = svg("text", "fy-chip-more");
      attrs(more, { x: width - 7, y: height / 2 + 0.5 });
      text(more, "\u2261");
      group.appendChild(more);

      var focusRing = svg("rect", "fy-chip-focus");
      attrs(focusRing, {
        x: -3, y: -3, width: width + 6, height: height + 6, rx: 6, ry: 6
      });
      group.appendChild(focusRing);

      group.setAttribute("tabindex", "0");
      group.setAttribute("role", "note");
      group.setAttribute("data-fy-tooltip", edge.tooltip);
      group.setAttribute("aria-label", edge.chip + ". " + edge.tooltip);
    } else {
      group.setAttribute("aria-hidden", "true");
    }
    return group;
  }

  /* ---------------------------------------------------------------- layout */

  var engine = null;
  var layoutCache = {};
  var renderToken = 0;
  var graphSize = { width: 0, height: 0 };

  function getEngine() {
    if (engine === null) {
      engine = window.ELK ? new window.ELK() : false;
    }
    return engine;
  }

  function buildGraph(model) {
    var children = [];
    var edges = [];
    var index;
    for (index = 0; index < model.nodes.length; index += 1) {
      var node = model.nodes[index];
      if (!node.__size) {
        node.__size = sizeNode(node);
      }
      children.push({
        id: node.id,
        width: node.__size.width,
        height: node.__size.height
      });
    }
    for (index = 0; index < model.edges.length; index += 1) {
      var edge = model.edges[index];
      var entry = {
        id: edge.id,
        sources: [edge.from],
        targets: [edge.to]
      };
      if (edge.chip) {
        var chipSize = sizeChip(edge.chip);
        entry.labels = [
          {
            id: edge.id + "-label",
            text: edge.chip,
            width: chipSize.width + (edge.tooltip ? 13 : 0),
            height: chipSize.height
          }
        ];
      }
      edges.push(entry);
    }
    return {
      id: "root",
      layoutOptions: config.layout,
      children: children,
      edges: edges
    };
  }

  function layoutModel(model) {
    if (layoutCache[model.id]) {
      return Promise.resolve(layoutCache[model.id]);
    }
    var elk = getEngine();
    if (!elk) {
      return Promise.reject(new Error("ELK runtime is not available"));
    }
    return elk.layout(buildGraph(model)).then(function (result) {
      layoutCache[model.id] = result;
      return result;
    });
  }

  function paint(model, laidOut) {
    clear(edgeLayer);
    clear(nodeLayer);
    clear(chipLayer);

    var placed = {};
    var laidEdges = {};
    var index;
    var children = laidOut.children || [];
    for (index = 0; index < children.length; index += 1) {
      placed[children[index].id] = children[index];
    }
    var resultEdges = laidOut.edges || [];
    for (index = 0; index < resultEdges.length; index += 1) {
      laidEdges[resultEdges[index].id] = resultEdges[index];
    }

    for (index = 0; index < model.edges.length; index += 1) {
      var edge = model.edges[index];
      var laidEdge = laidEdges[edge.id];
      if (!laidEdge) {
        continue;
      }
      edgeLayer.appendChild(drawEdge(edge, laidEdge));
      var chip = drawChip(edge, laidEdge);
      if (chip) {
        chipLayer.appendChild(chip);
      }
    }

    for (index = 0; index < model.nodes.length; index += 1) {
      var node = model.nodes[index];
      var box = placed[node.id];
      if (!box) {
        continue;
      }
      nodeLayer.appendChild(drawNode(node, box));
    }

    graphSize = {
      width: laidOut.width || 0,
      height: laidOut.height || 0
    };
  }

  /* -------------------------------------------------------------- viewport */

  var view = { k: 1, x: 0, y: 0 };
  var userAdjusted = false;

  function applyView() {
    viewport.setAttribute(
      "transform",
      "translate(" + view.x + "," + view.y + ") scale(" + view.k + ")"
    );
    text(zoomReadout, Math.round(view.k * 100) + "%");
  }

  function viewportSize() {
    return {
      width: canvas.clientWidth || root.clientWidth || 800,
      height: canvas.clientHeight || 480
    };
  }

  function fit() {
    var size = viewportSize();
    var width = graphSize.width || 1;
    var height = graphSize.height || 1;
    var scale = Math.min(
      (size.width - FIT_MARGIN * 2) / width,
      (size.height - FIT_MARGIN * 2) / height
    );
    view.k = clamp(scale, MIN_SCALE, FIT_MAX_SCALE);
    view.x = (size.width - width * view.k) / 2;
    view.y = (size.height - height * view.k) / 2;
    userAdjusted = false;
    applyView();
  }

  function zoomAround(factor, pointX, pointY) {
    var next = clamp(view.k * factor, MIN_SCALE, MAX_SCALE);
    if (next === view.k) {
      return;
    }
    view.x = pointX - ((pointX - view.x) * next) / view.k;
    view.y = pointY - ((pointY - view.y) * next) / view.k;
    view.k = next;
    userAdjusted = true;
    hideTooltip();
    applyView();
  }

  function zoomCentre(factor) {
    var size = viewportSize();
    zoomAround(factor, size.width / 2, size.height / 2);
  }

  /* --------------------------------------------------------------- tooltip */

  function showTooltip(target) {
    var value = target.getAttribute("data-fy-tooltip");
    if (!value) {
      return;
    }
    text(tooltip, value);
    tooltip.hidden = false;
    var canvasBox = canvas.getBoundingClientRect();
    var targetBox = target.getBoundingClientRect();
    var width = tooltip.offsetWidth;
    var height = tooltip.offsetHeight;
    var left = targetBox.left - canvasBox.left + targetBox.width / 2 - width / 2;
    var top = targetBox.bottom - canvasBox.top + 10;
    if (top + height > canvasBox.height - 4) {
      top = targetBox.top - canvasBox.top - height - 10;
    }
    tooltip.style.left = clamp(left, 6, Math.max(6, canvasBox.width - width - 6)) + "px";
    tooltip.style.top = clamp(top, 6, Math.max(6, canvasBox.height - height - 6)) + "px";
  }

  function hideTooltip() {
    tooltip.hidden = true;
  }

  /* ------------------------------------------------------------ navigation */

  var trail = [];
  var activeId = null;

  function hashPairs() {
    var raw = window.location.hash.replace(/^#/, "");
    var table = {};
    if (!raw) {
      return table;
    }
    var parts = raw.split("&");
    var index;
    for (index = 0; index < parts.length; index += 1) {
      var piece = parts[index];
      if (!piece) {
        continue;
      }
      var split = piece.indexOf("=");
      if (split < 0) {
        continue;
      }
      table[decodeURIComponent(piece.slice(0, split))] =
        decodeURIComponent(piece.slice(split + 1));
    }
    return table;
  }

  function writeHash(modelId) {
    var table = hashPairs();
    table[config.hashKey] = modelId;
    var out = [];
    var key;
    for (key in table) {
      if (Object.prototype.hasOwnProperty.call(table, key)) {
        out.push(encodeURIComponent(key) + "=" + encodeURIComponent(table[key]));
      }
    }
    window.location.hash = out.join("&");
  }

  function referencedBy(parentId, childId) {
    var parent = models[parentId];
    if (!parent) {
      return false;
    }
    var index;
    for (index = 0; index < parent.nodes.length; index += 1) {
      if (parent.nodes[index].ref === childId) {
        return true;
      }
    }
    return false;
  }

  function updateTrail(modelId) {
    var position = trail.indexOf(modelId);
    if (position >= 0) {
      trail = trail.slice(0, position + 1);
      return;
    }
    if (trail.length && referencedBy(trail[trail.length - 1], modelId)) {
      trail.push(modelId);
      return;
    }
    trail = [modelId];
  }

  function paintBreadcrumb() {
    clear(breadcrumb);
    var index;
    for (index = 0; index < trail.length; index += 1) {
      if (index > 0) {
        var separator = el("span", "fy-crumb-sep");
        text(separator, "\u203a");
        breadcrumb.appendChild(separator);
      }
      var crumb = el("button", "fy-crumb");
      crumb.type = "button";
      var model = models[trail[index]];
      text(crumb, model ? model.title : trail[index]);
      if (index === trail.length - 1) {
        crumb.setAttribute("aria-current", "page");
        crumb.disabled = true;
      } else {
        crumb.setAttribute("data-fy-goto", trail[index]);
      }
      breadcrumb.appendChild(crumb);
    }
    backButton.disabled = trail.length < 2;
  }

  function levelNumber(index) {
    var number = String(index + 1);
    return number.length < 2 ? "0" + number : number;
  }

  function openableNodes(model) {
    var out = [];
    var index;
    for (index = 0; index < model.nodes.length; index += 1) {
      var node = model.nodes[index];
      if (node.ref && models[node.ref]) {
        out.push(node);
      }
    }
    return out;
  }

  /* The drawer is rebuilt per level and closes with it: a list left open from
     the level before would be answering a question the reader has moved past. */
  function paintNext(model) {
    var choices = openableNodes(model);
    clear(nextGrid);
    nextDrawer.open = false;
    nextDrawer.hidden = choices.length === 0;
    if (!choices.length) {
      return;
    }
    text(
      nextSummary,
      (strings.nextSteps || "Explore next steps") + " (" + choices.length + ")"
    );
    var index;
    for (index = 0; index < choices.length; index += 1) {
      var node = choices[index];
      var item = el("button", "fy-next-item");
      item.type = "button";
      item.setAttribute("data-fy-goto", node.ref);
      item.setAttribute(
        "aria-label",
        (strings.open || "Open subprocess") + ": " + node.label
      );
      item.appendChild(text(el("span", "fy-next-label"), node.label));
      item.appendChild(text(el("span", "fy-next-arrow"), "\u203a"));
      nextGrid.appendChild(item);
    }
  }

  /* A snapshot of the level as it was drawn, kept so the stripe can show the
     reader what they came from rather than only what it was called. */
  function captureSnapshot(modelId) {
    if (levelsMode !== "snapshot" || !graphSize.width) {
      return;
    }
    var copy = surface.cloneNode(true);
    copy.removeAttribute("id");
    copy.removeAttribute("tabindex");
    copy.removeAttribute("role");
    copy.setAttribute("aria-hidden", "true");
    copy.setAttribute("focusable", "false");
    copy.setAttribute("viewBox", "0 0 " + graphSize.width + " " + graphSize.height);
    var port = copy.querySelector(".fy-viewport");
    if (port) {
      port.removeAttribute("transform");
    }

    /* The clone carries the live marker and clip ids with it. Two elements
       sharing one id on a page is a cross-wired reference, so each one is
       renamed and every url(#id) that pointed at it follows. */
    var renamed = {};
    var owners = copy.querySelectorAll("[id]");
    var index;
    for (index = 0; index < owners.length; index += 1) {
      var previous = owners[index].getAttribute("id");
      renamed[previous] = "snap-" + modelId + "-" + previous;
      owners[index].setAttribute("id", renamed[previous]);
    }

    var members = copy.querySelectorAll("*");
    for (index = 0; index < members.length; index += 1) {
      var member = members[index];
      member.removeAttribute("tabindex");
      member.removeAttribute("data-fy-ref");
      member.removeAttribute("role");
      var attributes = member.attributes;
      var position;
      for (position = 0; position < attributes.length; position += 1) {
        var attribute = attributes[position];
        var rewritten = attribute.value.replace(
          /url\(#([^)]*)\)/g,
          function (whole, target) {
            return renamed[target] ? "url(#" + renamed[target] + ")" : whole;
          }
        );
        if (rewritten !== attribute.value) {
          member.setAttribute(attribute.name, rewritten);
        }
      }
    }

    snapshots[modelId] = copy;
  }

  function paintStripe() {
    if (!stripe) {
      return;
    }
    clear(stripe);
    var index;
    for (index = 0; index < trail.length - 1; index += 1) {
      var modelId = trail[index];
      var model = models[modelId];
      var title = model ? model.title : modelId;
      var panel = el("section", "fy-ancestor");
      var button = el("button", "fy-ancestor-btn");
      button.type = "button";
      button.setAttribute("data-fy-goto", modelId);
      button.setAttribute(
        "aria-label",
        (strings.returnTo || "Return to") + " " + title
      );
      var head = el("span", "fy-ancestor-head");
      head.appendChild(text(el("span", "fy-ancestor-step"), levelNumber(index)));
      head.appendChild(text(el("span", "fy-ancestor-title"), title));
      head.appendChild(text(el("span", "fy-ancestor-action"), "\u2191"));
      button.appendChild(head);
      /* Only the level immediately above gets a picture. Further back, the
         name is what the reader is navigating by anyway. */
      if (index === trail.length - 2 && snapshots[modelId]) {
        var thumb = el("span", "fy-thumb");
        thumb.setAttribute("aria-hidden", "true");
        thumb.appendChild(snapshots[modelId].cloneNode(true));
        button.appendChild(thumb);
      }
      panel.appendChild(button);
      stripe.appendChild(panel);
    }
    stripe.scrollTop = stripe.scrollHeight;
    if (levelCounter) {
      text(
        levelCounter,
        (strings.level || "Level") + " " + levelNumber(trail.length - 1)
      );
    }
  }

  function showMessage(message) {
    text(empty, message);
    empty.hidden = false;
  }

  function activate(modelId) {
    var model = models[modelId] || models[config.defaultModel];
    if (!model) {
      showMessage(strings.noModel || "This document contains no renderable model.");
      return;
    }
    activeId = model.id;
    root.setAttribute("data-fy-model", model.id);
    updateTrail(model.id);
    paintBreadcrumb();
    paintStripe();
    paintNext(model);
    hideTooltip();

    text(modelName, model.title);
    if (linked && config.output === "document") {
      /* The head title was written from the YAML as it stood when the shell
         was rendered; in linked mode the source can have moved on since. */
      document.title = model.title;
    }
    if (model.version) {
      text(versionBadge, "v" + model.version);
      versionBadge.hidden = false;
    } else {
      versionBadge.hidden = true;
    }
    surface.setAttribute(
      "aria-label",
      (strings.canvasAria || "Process flow diagram") + ": " + model.title
    );
    text(status, (strings.showing || "Showing") + " " + model.title);

    var token = (renderToken += 1);
    layoutModel(model).then(
      function (laidOut) {
        if (token !== renderToken) {
          return;
        }
        empty.hidden = true;
        paint(model, laidOut);
        fit();
        /* After the draw, so the stripe of the next level down can show this
           one as it actually ended up on screen. */
        captureSnapshot(model.id);
      },
      function (error) {
        if (token !== renderToken) {
          return;
        }
        showMessage(
          (strings.layoutFailed || "The layout engine could not draw this model.") +
            " " + (error && error.message ? error.message : "")
        );
      }
    );
  }

  function goTo(modelId) {
    if (!models[modelId]) {
      return;
    }
    if (hashPairs()[config.hashKey] === modelId) {
      activate(modelId);
      return;
    }
    writeHash(modelId);
  }

  function goUp() {
    if (trail.length > 1) {
      goTo(trail[trail.length - 2]);
    }
  }

  /* ----------------------------------------------------- linked YAML data */

  /* One delivery from the companion loader. `detail.models` replaces the whole
     model table, so an edited YAML source can add, rename or drop models. The
     view returns to the model the reader was on whenever it survived the edit,
     then to the hash, the payload default and finally the first model. */
  function receiveData(detail) {
    if (!detail) {
      return;
    }
    if (detail.revision) {
      root.setAttribute("data-fy-revision", String(detail.revision));
    }
    if (detail.error) {
      showMessage(String(detail.error));
      return;
    }
    var previous = activeId;
    adoptModels(detail.models);
    /* Every laid out graph belongs to the model objects it was built from,
       down to the size memo on each node, so an edited source invalidates all
       of it. Keeping it would redraw the previous graph. */
    layoutCache = {};
    if (detail.defaultModel && models[detail.defaultModel]) {
      config.defaultModel = detail.defaultModel;
    }
    if (!modelOrder.length) {
      showMessage(strings.noModel || "This document contains no renderable model.");
      return;
    }
    var wanted = hashPairs()[config.hashKey];
    if (!models[wanted]) {
      wanted = previous;
    }
    if (!models[wanted]) {
      wanted = config.defaultModel;
    }
    if (!models[wanted]) {
      wanted = modelOrder[0];
    }
    /* The trail is a path through a model set that may no longer exist, and
       the snapshots are pictures of models that may have just been edited. */
    trail = [];
    snapshots = {};
    activeId = null;
    activate(wanted);
  }

  if (linked) {
    root.addEventListener("flowyaml:data", function (event) {
      receiveData(event.detail);
    });
  }

  /* ---------------------------------------------------------------- events */

  function closestWith(target, attribute) {
    var node = target;
    while (node && node !== surface) {
      if (node.getAttribute && node.getAttribute(attribute) !== null) {
        return node;
      }
      node = node.parentNode;
    }
    return null;
  }

  var pointers = {};
  var pointerCount = 0;
  var panning = false;
  var panOrigin = null;
  var pinchStart = null;
  var moved = 0;
  /* Pointer capture retargets later events to the svg itself, so the pressed
     control has to be remembered from pointerdown. */
  var pressedControl = null;

  surface.addEventListener("pointerdown", function (event) {
    if (event.button !== undefined && event.button !== 0 && event.pointerType === "mouse") {
      return;
    }
    pointers[event.pointerId] = { x: event.clientX, y: event.clientY };
    pointerCount += 1;
    moved = 0;
    pressedControl = closestWith(event.target, "data-fy-ref");
    if (pointerCount === 1) {
      panning = true;
      panOrigin = { x: event.clientX, y: event.clientY, viewX: view.x, viewY: view.y };
      surface.setAttribute("data-fy-panning", "true");
      try {
        surface.setPointerCapture(event.pointerId);
      } catch (error) {
        /* capture is best effort */
      }
    } else if (pointerCount === 2) {
      panning = false;
      pinchStart = pinchState();
    }
  });

  function pinchState() {
    var keys = Object.keys(pointers);
    if (keys.length < 2) {
      return null;
    }
    var a = pointers[keys[0]];
    var b = pointers[keys[1]];
    var box = canvas.getBoundingClientRect();
    return {
      distance: Math.max(1, Math.hypot(a.x - b.x, a.y - b.y)),
      centreX: (a.x + b.x) / 2 - box.left,
      centreY: (a.y + b.y) / 2 - box.top,
      scale: view.k
    };
  }

  surface.addEventListener("pointermove", function (event) {
    if (!(event.pointerId in pointers)) {
      return;
    }
    pointers[event.pointerId] = { x: event.clientX, y: event.clientY };

    if (pointerCount >= 2 && pinchStart) {
      var now = pinchState();
      if (!now) {
        return;
      }
      var factor = now.distance / pinchStart.distance;
      var target = clamp(pinchStart.scale * factor, MIN_SCALE, MAX_SCALE);
      zoomAround(target / view.k, now.centreX, now.centreY);
      return;
    }

    if (!panning || !panOrigin) {
      return;
    }
    var dx = event.clientX - panOrigin.x;
    var dy = event.clientY - panOrigin.y;
    moved = Math.max(moved, Math.hypot(dx, dy));
    if (moved > CLICK_SLOP) {
      hideTooltip();
    }
    view.x = panOrigin.viewX + dx;
    view.y = panOrigin.viewY + dy;
    userAdjusted = true;
    applyView();
  });

  function endPointer(event) {
    if (event.pointerId in pointers) {
      delete pointers[event.pointerId];
      pointerCount = Math.max(0, pointerCount - 1);
    }
    if (pointerCount < 2) {
      pinchStart = null;
    }
    if (pointerCount === 0) {
      panning = false;
      panOrigin = null;
      surface.removeAttribute("data-fy-panning");
    }
  }

  surface.addEventListener("pointerup", function (event) {
    var wasDrag = moved > CLICK_SLOP;
    var control = pressedControl || closestWith(event.target, "data-fy-ref");
    endPointer(event);
    pressedControl = null;
    if (wasDrag || !control) {
      return;
    }
    goTo(control.getAttribute("data-fy-ref"));
  });

  surface.addEventListener("pointercancel", function (event) {
    pressedControl = null;
    endPointer(event);
  });
  surface.addEventListener("pointerleave", function (event) {
    if (event.pointerType === "mouse" && pointerCount === 0) {
      hideTooltip();
    }
  });

  surface.addEventListener(
    "wheel",
    function (event) {
      event.preventDefault();
      var box = canvas.getBoundingClientRect();
      var factor = Math.exp(-event.deltaY * (event.deltaMode === 1 ? 0.02 : 0.0016));
      zoomAround(factor, event.clientX - box.left, event.clientY - box.top);
    },
    { passive: false }
  );

  surface.addEventListener("mouseover", function (event) {
    var target = closestWith(event.target, "data-fy-tooltip");
    if (target) {
      showTooltip(target);
    }
  });

  surface.addEventListener("mouseout", function (event) {
    var target = closestWith(event.target, "data-fy-tooltip");
    if (target) {
      hideTooltip();
    }
  });

  surface.addEventListener("focusin", function (event) {
    var focusable = closestWith(event.target, "tabindex");
    if (!focusable) {
      return;
    }
    focusable.setAttribute("class", focusable.getAttribute("class") + " fy-is-focused");
    if (focusable.getAttribute("data-fy-tooltip")) {
      showTooltip(focusable);
    }
  });

  surface.addEventListener("focusout", function (event) {
    var focusable = closestWith(event.target, "tabindex");
    if (focusable) {
      focusable.setAttribute(
        "class",
        (focusable.getAttribute("class") || "").replace(/\s*fy-is-focused/g, "")
      );
    }
    hideTooltip();
  });

  surface.addEventListener("keydown", function (event) {
    var control = closestWith(event.target, "data-fy-ref");
    var key = event.key;

    if (control && (key === "Enter" || key === " " || key === "Spacebar")) {
      event.preventDefault();
      goTo(control.getAttribute("data-fy-ref"));
      return;
    }
    if (key === "+" || key === "=") {
      event.preventDefault();
      zoomCentre(1.2);
      return;
    }
    if (key === "-" || key === "_") {
      event.preventDefault();
      zoomCentre(1 / 1.2);
      return;
    }
    if (key === "0") {
      event.preventDefault();
      fit();
      return;
    }
    if (key === "Escape") {
      hideTooltip();
      return;
    }
    if (key === "Backspace") {
      event.preventDefault();
      goUp();
      return;
    }

    var dx = 0;
    var dy = 0;
    if (key === "ArrowLeft") {
      dx = PAN_STEP;
    } else if (key === "ArrowRight") {
      dx = -PAN_STEP;
    } else if (key === "ArrowUp") {
      dy = PAN_STEP;
    } else if (key === "ArrowDown") {
      dy = -PAN_STEP;
    } else {
      return;
    }
    event.preventDefault();
    view.x += dx;
    view.y += dy;
    userAdjusted = true;
    hideTooltip();
    applyView();
  });

  /* One delegation for every control that names a destination: the toolbar
     breadcrumb, the stripe of levels above, and the drawer of levels below. */
  function delegateGoTo(container) {
    if (!container) {
      return;
    }
    container.addEventListener("click", function (event) {
      var target = null;
      var node = event.target;
      while (node && node !== container) {
        if (node.getAttribute && node.getAttribute("data-fy-goto")) {
          target = node;
          break;
        }
        node = node.parentNode;
      }
      if (target && target.getAttribute("data-fy-goto")) {
        goTo(target.getAttribute("data-fy-goto"));
      }
    });
  }

  delegateGoTo(breadcrumb);
  delegateGoTo(stripe);
  delegateGoTo(nextGrid);

  backButton.addEventListener("click", goUp);
  zoomIn.addEventListener("click", function () {
    zoomCentre(1.2);
  });
  zoomOut.addEventListener("click", function () {
    zoomCentre(1 / 1.2);
  });
  fitButton.addEventListener("click", fit);

  window.addEventListener("hashchange", function () {
    var wanted = hashPairs()[config.hashKey];
    if (!wanted) {
      wanted = config.defaultModel;
    }
    if (wanted !== activeId) {
      activate(wanted);
    }
  });

  if (typeof window.ResizeObserver === "function") {
    var observer = new window.ResizeObserver(function () {
      if (!userAdjusted) {
        fit();
      }
    });
    observer.observe(canvas);
  } else {
    window.addEventListener("resize", function () {
      if (!userAdjusted) {
        fit();
      }
    });
  }

  window.addEventListener("beforeprint", fit);

  /* ------------------------------------------------------------------ boot */

  if (!window.ELK) {
    showMessage(strings.noEngine || "The bundled layout engine did not load.");
  } else if (linked) {
    /* Nothing to draw yet: live.js runs next and delivers the payload. */
    root.setAttribute("data-fy-linked", "true");
    showMessage(strings.loading || "Loading the linked YAML source\u2026");
  } else {
    var initial = hashPairs()[config.hashKey];
    activate(models[initial] ? initial : config.defaultModel);
  }

  root.setAttribute("data-fy-ready", "true");
})();
