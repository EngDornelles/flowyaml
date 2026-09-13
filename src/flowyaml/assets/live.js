/* FlowYAML linked-source loader.
 *
 * Emitted only for a data="url" render. The standalone inline artifact never
 * carries this file, which is what keeps that artifact provably network free.
 *
 * The loader fetches the model payload the host serves, hands it to the
 * runtime through a DOM event on the instance root, and re-fetches whenever a
 * cheap revision probe reports that the YAML source has changed on the host.
 * The runtime owns no network code: this file is the only place a request is
 * made, and it speaks to the runtime through that one event.
 *
 * Payload contract (host side, see flowyaml.payload):
 *   { "revision": "...", "defaultModel": "...", "models": [ ... ] }
 *   { "revision": "...", "error": "...", "issues": [ "...", ... ] }
 */
(function () {
  "use strict";

  var DATA_ID = "__FLOWYAML_DATA_ID__";

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

  var source = config.source;
  if (!source || !source.data) {
    return;
  }

  var root = document.getElementById(config.instance);
  if (!root) {
    return;
  }

  var strings = config.strings || {};

  function send(detail) {
    var event;
    try {
      event = new window.CustomEvent("flowyaml:data", { detail: detail });
    } catch (error) {
      /* Engines without the CustomEvent constructor. */
      event = document.createEvent("CustomEvent");
      event.initCustomEvent("flowyaml:data", false, false, detail);
    }
    root.dispatchEvent(event);
  }

  function fail(message) {
    send({ error: message });
  }

  function describe(payload) {
    /* Validation issues are shown on the canvas so whoever is editing the
       YAML sees what broke without leaving the page. The canvas message is a
       single line, so the issues are joined rather than listed. */
    var message = String(payload.error || strings.sourceUnavailable || "");
    var issues = payload.issues;
    if (issues && issues.length) {
      var shown = [];
      var index;
      for (index = 0; index < issues.length && index < 6; index += 1) {
        shown.push(String(issues[index]));
      }
      if (issues.length > shown.length) {
        shown.push("+" + (issues.length - shown.length) + " more");
      }
      message = message + " \u2014 " + shown.join(" \u00b7 ");
    }
    return message;
  }

  /* A browser will not fetch a sibling file over file://: the page has an
     opaque origin there, so the request is refused before it reaches the
     disk. Saying so plainly beats a silently empty canvas. */
  if (window.location.protocol === "file:") {
    fail(strings.fileSource || "This page reads its data over http.");
    return;
  }

  if (typeof window.fetch !== "function") {
    fail(strings.noFetch || "This browser cannot load the linked source.");
    return;
  }

  var revision = null;
  var busy = false;

  function get(url) {
    return window
      .fetch(url, { cache: "no-store", credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        return response.json();
      });
  }

  function deliver(payload) {
    if (!payload) {
      return;
    }
    if (payload.revision !== undefined && payload.revision !== null) {
      revision = payload.revision;
    }
    if (payload.error) {
      send({ error: describe(payload), revision: revision });
      return;
    }
    send(payload);
  }

  function load() {
    return get(source.data).then(deliver, function (error) {
      fail(
        (strings.sourceUnavailable || "The linked source could not be read.") +
          " " +
          (error && error.message ? error.message : "")
      );
    });
  }

  /* A failed probe means the host is momentarily away (a restart, a save in
     flight). The last good drawing stays on screen and the next tick tries
     again, which is quieter and more useful than an error every second. */
  function tick() {
    if (busy || (document.hidden && revision !== null)) {
      return;
    }
    busy = true;
    var done = function () {
      busy = false;
    };

    if (source.revision) {
      get(source.revision).then(function (info) {
        var next = info ? info.revision : null;
        if (next === null || next === undefined || next === revision) {
          done();
          return null;
        }
        return load().then(done, done);
      }, done);
      return;
    }

    /* No revision endpoint: the payload itself is the probe. */
    get(source.data).then(function (payload) {
      if (payload && payload.revision !== undefined && payload.revision === revision) {
        done();
        return;
      }
      deliver(payload);
      done();
    }, done);
  }

  load().then(function () {
    var poll = Number(source.poll || 0);
    if (poll > 0) {
      window.setInterval(tick, poll);
    }
  });
})();
