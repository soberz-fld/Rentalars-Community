/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * Rentalars – scanning bar codes and QR codes in the browser (UIX-006, MAT-027, PCK-010; PCK-011).
 *
 * A button with data-scan-open opens a dialog (<dialog>, keyboard operable, closes with Escape):
 *
 *   - the camera, where the browser can read codes from its picture (the BarcodeDetector API: QR, Code 128,
 *     EAN/UPC, Code 39) and the page is served over HTTPS (browsers give the camera to secure pages only –
 *     http://localhost counts as secure). No code is bundled: browsers without BarcodeDetector (Firefox, Safari
 *     at the time of writing) use the way below. The camera pictures stay in the browser: only the decoded text
 *     is sent to the server, and only when the page asks for it. The camera stops when the dialog closes, when
 *     the page is left and when the tab is hidden.
 *   - a field for typing the code, always there: a hand scanner that types like a keyboard (and ends with Enter)
 *     is read by it as well as a person typing an ID. The field has the focus when the dialog opens.
 *   - a button for the torch if the camera has one.
 *
 * What a code does depends on the button's data attributes (set by templates/material/_scan.html):
 *
 *   data-scan-mode="submit"  put the code into the field data-scan-input (a CSS selector) and send its form
 *                            (the item field of the material pages; the packing list, htmx).
 *   data-scan-mode="plan"    ask data-scan-resolve what the code is, and send its product to data-scan-post with
 *                            htmx (adds the item to the planning as a wish).
 *   data-scan-continuous     keep the dialog open for the next code (packing a case item by item).
 *
 * The texts come from data-t-* attributes (translated by the server). Before acting on a code the widget fires
 * "scan:code" on the button (detail: {code, source}); calling preventDefault takes the code over.
 * No inline scripts: the content security policy forbids them.
 */
(function () {
  "use strict";

  var FORMATS = ["qr_code", "code_128", "ean_13", "ean_8", "upc_a", "upc_e", "code_39"];
  var SAME_CODE_MS = 2500;   // the same code in front of the camera is read once
  var POLL_MS = 220;

  var session = null;

  function text(config, key, fallback) { return config["t" + key] || fallback; }

  function element(tag, className, content) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (content) { node.textContent = content; }
    return node;
  }

  /* ---- The dialog ----------------------------------------------------- */

  function open(button) {
    if (session) { close(); }
    var config = Object.assign({}, button.dataset);
    var dialog = element("dialog", "dialog scan-dialog");
    dialog.setAttribute("aria-labelledby", "scan-title");

    var head = element("div", "dialog-head");
    var title = element("h2", "", text(config, "Title", "Scan a code"));
    title.id = "scan-title";
    var closeButton = element("button", "icon-btn", "×");
    closeButton.type = "button";
    closeButton.setAttribute("aria-label", text(config, "Close", "Close"));
    head.appendChild(title);
    head.appendChild(closeButton);

    var body = element("div", "dialog-body");
    var status = element("p", "scan-status");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    var frame = element("div", "scan-frame hidden");
    var video = element("video");
    video.setAttribute("playsinline", "");
    video.muted = true;
    video.setAttribute("aria-hidden", "true");
    frame.appendChild(video);
    frame.appendChild(element("span", "scan-aim"));
    var torch = element("button", "btn secondary small hidden", text(config, "Torch", "Torch"));
    torch.type = "button";
    torch.setAttribute("aria-pressed", "false");

    var form = element("form", "scan-manual");
    form.setAttribute("autocomplete", "off");
    var label = element("label", "", text(config, "Manual", "Type or scan the code"));
    label.setAttribute("for", "scan-manual-code");
    var row = element("div", "scan-manual-row");
    var field = element("input");
    field.type = "text";
    field.id = "scan-manual-code";
    field.setAttribute("autocomplete", "off");
    field.setAttribute("autocapitalize", "off");
    field.setAttribute("spellcheck", "false");
    field.setAttribute("enterkeyhint", "go");
    var ok = element("button", "btn", text(config, "Ok", "OK"));
    ok.type = "submit";
    row.appendChild(field);
    row.appendChild(ok);
    var hint = element("p", "muted small", text(config, "ManualHint", ""));
    form.appendChild(label);
    form.appendChild(row);
    if (hint.textContent) { form.appendChild(hint); }

    body.appendChild(status);
    body.appendChild(frame);
    body.appendChild(torch);
    body.appendChild(form);

    var foot = element("div", "dialog-foot");
    var done = element("button", "btn secondary", text(config, "Close", "Close"));
    done.type = "button";
    foot.appendChild(done);

    dialog.appendChild(head);
    dialog.appendChild(body);
    dialog.appendChild(foot);
    document.body.appendChild(dialog);

    session = {
      button: button, config: config, dialog: dialog, status: status, video: video, frame: frame, torch: torch,
      field: field, stream: null, timer: null, busy: false, last: "", lastAt: 0, torchOn: false, closed: false
    };

    closeButton.addEventListener("click", close);
    done.addEventListener("click", close);
    dialog.addEventListener("close", close);
    dialog.addEventListener("cancel", function () { /* Escape closes through the close event */ });
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var code = field.value.trim();
      field.value = "";
      if (code) { handle(code, "manual"); }
      field.focus();
    });
    torch.addEventListener("click", toggleTorch);

    dialog.showModal();
    field.focus();
    setStatus("info", text(config, "Starting", "Starting the camera …"));
    startCamera();
  }

  function setStatus(level, message) {
    if (!session) { return; }
    session.status.textContent = message;
    session.status.className = "scan-status is-" + level;
  }

  function close() {
    var current = session;
    if (!current || current.closed) { return; }
    current.closed = true;
    session = null;
    stopCamera(current);
    if (current.dialog.open) { current.dialog.close(); }
    if (current.dialog.parentNode) { current.dialog.parentNode.removeChild(current.dialog); }
    var opener = document.contains(current.button) ? current.button : document.querySelector("[data-scan-open]");
    if (opener) { opener.focus(); }
  }

  /* ---- The camera ------------------------------------------------------ */

  function stopCamera(target) {
    if (target.timer) { window.clearInterval(target.timer); target.timer = null; }
    if (target.stream) {
      target.stream.getTracks().forEach(function (track) { track.stop(); });
      target.stream = null;
    }
    target.video.srcObject = null;
  }

  function startCamera() {
    var current = session;
    var config = current.config;
    if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setStatus("warning", text(config, "Insecure", "The camera needs a secure connection (HTTPS). Type the code or use a hand scanner."));
      return;
    }
    if (!("BarcodeDetector" in window)) {
      setStatus("warning", text(config, "Unsupported", "This browser cannot read codes from the camera. Type the code or use a hand scanner."));
      return;
    }
    var supported = window.BarcodeDetector.getSupportedFormats ? window.BarcodeDetector.getSupportedFormats() : Promise.resolve(FORMATS);
    supported.then(function (formats) {
      var usable = FORMATS.filter(function (format) { return formats.indexOf(format) !== -1; });
      if (!usable.length) { throw new Error("no formats"); }
      return new window.BarcodeDetector({ formats: usable });
    }).then(function (detector) {
      if (current.closed) { return null; }
      return navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false }).then(function (stream) {
        if (current.closed) { stream.getTracks().forEach(function (track) { track.stop(); }); return; }
        current.stream = stream;
        current.video.srcObject = stream;
        current.frame.classList.remove("hidden");
        var play = current.video.play();
        if (play && play.catch) { play.catch(function () { /* autoplay is allowed for muted video */ }); }
        offerTorch(current, stream);
        setStatus("info", text(config, "Ready", "Hold the code in front of the camera."));
        current.timer = window.setInterval(function () { look(current, detector); }, POLL_MS);
      });
    }).catch(function (error) {
      if (current.closed) { return; }
      var name = error && error.name;
      if (name === "NotAllowedError" || name === "SecurityError") {
        setStatus("warning", text(config, "Denied", "The camera is not allowed. Allow it in the settings of the browser, or type the code."));
      } else if (name === "NotFoundError" || name === "OverconstrainedError" || name === "DevicesNotFoundError") {
        setStatus("warning", text(config, "NoCamera", "No camera found. Type the code or use a hand scanner."));
      } else {
        setStatus("warning", text(config, "Failed", "The camera could not be started. Type the code or use a hand scanner."));
      }
    });
  }

  function look(current, detector) {
    if (current.closed || current.busy || current.video.readyState < 2) { return; }
    current.busy = true;
    detector.detect(current.video).then(function (codes) {
      current.busy = false;
      if (current.closed || !codes || !codes.length) { return; }
      var value = String(codes[0].rawValue || "").trim();
      var now = Date.now();
      if (!value || (value === current.last && now - current.lastAt < SAME_CODE_MS)) {
        if (value) { current.lastAt = now; }
        return;
      }
      current.last = value;
      current.lastAt = now;
      handle(value, "camera");
    }).catch(function () { current.busy = false; });
  }

  function offerTorch(current, stream) {
    var track = stream.getVideoTracks()[0];
    var capabilities = track && track.getCapabilities ? track.getCapabilities() : {};
    if (capabilities && capabilities.torch) { current.torch.classList.remove("hidden"); }
  }

  function toggleTorch() {
    var current = session;
    if (!current || !current.stream) { return; }
    var track = current.stream.getVideoTracks()[0];
    var wanted = !current.torchOn;
    track.applyConstraints({ advanced: [{ torch: wanted }] }).then(function () {
      current.torchOn = wanted;
      current.torch.setAttribute("aria-pressed", wanted ? "true" : "false");
    }).catch(function () { /* the camera refuses the torch: the button stays off */ });
  }

  /* ---- What a code does ------------------------------------------------- */

  function handle(code, source) {
    var current = session;
    if (!current) { return; }
    var config = current.config;
    var taken = new CustomEvent("scan:code", { bubbles: true, cancelable: true, detail: { code: code, source: source } });
    if (!current.button.dispatchEvent(taken)) { return; }
    var continuous = "scanContinuous" in config;
    if (config.scanMode === "plan") {
      planCode(current, code, continuous);
      return;
    }
    var input = document.querySelector(config.scanInput || "");
    if (!input) { return; }
    input.value = code;
    setStatus("info", text(config, "Working", "Checking …") + " " + code);
    var form = input.form;
    if (!continuous) { close(); }
    if (form && form.requestSubmit) { form.requestSubmit(); } else if (form) { form.submit(); }
  }

  function planCode(current, code, continuous) {
    var config = current.config;
    setStatus("info", text(config, "Working", "Checking …") + " " + code);
    fetch(config.scanResolve + "?code=" + encodeURIComponent(code), { headers: { "Accept": "application/json" }, credentials: "same-origin" })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (result) {
        if (!session || session !== current) { return; }
        if (!result || !result.plan_token) {
          var message = result && result.found !== false && result.title
            ? result.title + ": " + text(config, "NotPlannable", "cannot be planned.")
            : (result && result.message) || text(config, "Nothing", "Nothing is known under this code.");
          setStatus("warning", message);
          return;
        }
        setStatus("success", text(config, "Added", "Added:") + " " + (result.plan_label || result.title));
        window.htmx.ajax("POST", config.scanPost, {
          target: "#planning", swap: "outerHTML",
          values: { product: result.plan_token, quantity: "1", group: "" }
        });
        if (!continuous) { close(); }
      })
      .catch(function () { setStatus("warning", text(config, "Failed", "The camera could not be started.")); });
  }

  /* ---- Answers of the packing list --------------------------------------- */
  // The server announces what a scan did ("scanResult" in HX-Trigger): the dialog says it aloud and with a short
  // vibration, because the packing list below the dialog cannot be seen.
  document.addEventListener("scanResult", function (event) {
    var detail = event.detail || {};
    if (session) {
      setStatus(detail.level || "info", detail.message || "");
      session.field.focus();
    }
    if (navigator.vibrate) { navigator.vibrate(detail.level === "success" ? 60 : [80, 60, 80]); }
  });

  /* ---- After the packing list was swapped in ----------------------------- */
  var refocus = false;
  document.addEventListener("htmx:beforeRequest", function (event) {
    var source = event.detail && event.detail.elt;
    refocus = !!(source && source.matches && source.matches("[data-scan-form]"));
  });
  document.addEventListener("htmx:afterSettle", function () {
    var hit = document.querySelector(".pack-row.is-scanned");
    if (hit && hit.scrollIntoView && !session) { hit.scrollIntoView({ block: "center", behavior: "smooth" }); }
    if (refocus && !session) {
      var again = document.querySelector("[data-scan-form] [data-scan-field]");
      if (again) { again.focus(); }
    }
    refocus = false;
  });

  /* ---- Opening and leaving ------------------------------------------------ */
  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-scan-open]");
    if (button) { event.preventDefault(); open(button); }
  });
  window.addEventListener("pagehide", close);
  document.addEventListener("visibilitychange", function () { if (document.hidden) { close(); } });
})();
