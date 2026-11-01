/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * Rentalars – the small amount of JavaScript the pages need (UIX-009).
 *
 * Pages are rendered by the server. This file only adds what must react at
 * once: the menu on phones, search-as-you-type fields, the dialog for
 * editing a line, sorting lines by dragging, copying amounts, and the
 * running stopwatch.
 *
 * Everything is wired through "data-" attributes in the HTML. There are no
 * inline scripts; the content security policy forbids them.
 */
(function () {
  "use strict";

  var csrfToken = document.body.dataset.csrf || "";

  /* ---- Menu on narrow screens ---------------------------------------- */

  // UIX-017: the menu begins right below the header; its height depends on font size and zoom.
  function placeMenu() {
    var bar = document.querySelector(".topbar");
    if (bar) { document.documentElement.style.setProperty("--topbar-height", bar.getBoundingClientRect().bottom + "px"); }
  }

  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-toggle-nav]")) {
      placeMenu();
      document.body.classList.toggle("nav-open");
    }
    // UIX-027: on the pages of the tabs "Back" at the top goes to wherever one came from in this
    // application; arriving from elsewhere, it leads to the start page.
    var back = event.target.closest("[data-history-back]");
    if (back && window.history.length > 1 && document.referrer) {
      var cameFrom = null;
      try { cameFrom = new URL(document.referrer); } catch (error) { cameFrom = null; }
      if (cameFrom && cameFrom.origin === window.location.origin && cameFrom.pathname.indexOf("/login") !== 0) {
        event.preventDefault();
        window.history.back();
        return;
      }
    }
    // UIX-019: on the phone the search sits in the menu; the magnifier opens it there.
    if (event.target.closest("[data-open-search]")) {
      placeMenu();
      document.body.classList.add("nav-open");
      var field = document.getElementById("nav-search");
      if (field) { field.focus(); }
    }
  });
  window.addEventListener("resize", placeMenu);

  // UIX-027: on a narrow screen the tabs scroll sideways; the current one is always in view.
  document.querySelectorAll("nav.tabs").forEach(function (bar) {
    var current = bar.querySelector('[aria-current="page"]');
    if (!current || bar.scrollWidth <= bar.clientWidth) { return; }
    var frame = bar.getBoundingClientRect();
    var tab = current.getBoundingClientRect();
    if (tab.right > frame.right) {
      bar.scrollLeft += tab.right - frame.right + 24;
    } else if (tab.left < frame.left) {
      bar.scrollLeft -= frame.left - tab.left + 24;
    }
  });

  // "/" puts the cursor into the search, as in many web applications – unless one is typing.
  document.addEventListener("keydown", function (event) {
    if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) { return; }
    var target = event.target;
    if (target.closest("input, textarea, select, [contenteditable], dialog[open]")) { return; }
    var field = document.getElementById("nav-search");
    if (!field) { return; }
    event.preventDefault();
    // UIX-045: on the phone the closed menu is out of view (hidden), not "display: none".
    if (window.getComputedStyle(field).display === "none" || window.getComputedStyle(field).visibility === "hidden" || !field.offsetParent) {
      placeMenu();
      document.body.classList.add("nav-open");
    }
    field.focus();
    field.select();
  });

  /* ---- Warn before leaving a form with unsaved changes (B1) ------- */
  // <form data-warn-unsaved>: changing a field marks the form; leaving the page without sending it asks first.
  document.querySelectorAll("form[data-warn-unsaved]").forEach(function (form) {
    var dirty = false;
    var sending = false;
    form.addEventListener("input", function () { dirty = true; });
    form.addEventListener("change", function () { dirty = true; });
    form.addEventListener("submit", function () { sending = true; });
    window.addEventListener("beforeunload", function (event) {
      if (dirty && !sending) { event.preventDefault(); event.returnValue = ""; }
    });
  });

  /* ---- Confirmation before destructive actions (UIX-018) ---------------- */
  // <button data-confirm="Really delete?"> asks before the form is sent, and
  // so does htmx's hx-confirm – in a dialog of the application, not in the
  // grey box of the browser. A button with class "danger" or a text about
  // deleting gets a red confirm button.

  function askDialog(text, confirmLabel, danger) {
    return new Promise(function (resolve) {
      var box = document.createElement("dialog");
      box.className = "dialog confirm" + (danger ? " danger" : "");
      box.setAttribute("aria-labelledby", "confirm-text");
      var body = document.createElement("div");
      body.className = "dialog-body";
      body.id = "confirm-text";
      body.textContent = text;
      var foot = document.createElement("div");
      foot.className = "dialog-foot";
      var cancel = document.createElement("button");
      cancel.type = "button";
      cancel.className = "btn secondary";
      cancel.textContent = document.body.dataset.textCancel || "Cancel";
      var ok = document.createElement("button");
      ok.type = "button";
      ok.className = danger ? "btn danger" : "btn";
      ok.textContent = confirmLabel || (danger && document.body.dataset.textDelete) || document.body.dataset.textConfirm || "OK";
      foot.appendChild(cancel);
      foot.appendChild(ok);
      box.appendChild(body);
      box.appendChild(foot);
      document.body.appendChild(box);
      var answer = false;
      cancel.addEventListener("click", function () { box.close(); });
      ok.addEventListener("click", function () { answer = true; box.close(); });
      box.addEventListener("close", function () { box.remove(); resolve(answer); });
      box.showModal();
      ok.focus();
    });
  }

  function looksDangerous(element, text) {
    return element.classList.contains("danger") || /lösch|entfern|delete|remove/i.test(text || "");
  }

  document.addEventListener("click", function (event) {
    var trigger = event.target.closest("[data-confirm]");
    if (!trigger) { return; }
    if (trigger.dataset.confirmed === "1") { delete trigger.dataset.confirmed; return; }
    event.preventDefault();
    event.stopPropagation();
    var label = (trigger.textContent || "").trim();
    askDialog(trigger.dataset.confirm, label.length < 40 ? label : "", looksDangerous(trigger, trigger.dataset.confirm)).then(function (yes) {
      if (!yes) { return; }
      trigger.dataset.confirmed = "1";
      if (trigger.form && (trigger.type === "submit" || trigger.tagName === "BUTTON")) {
        trigger.form.requestSubmit(trigger);
        delete trigger.dataset.confirmed;
      } else {
        trigger.click();
      }
    });
  }, true);

  // PRJ-078: the status of a project is chosen from a list; cancelling asks first, as its button did.
  function prepareStatusForm(form) {
    var choice = form.querySelector("select[name=status]");
    var button = form.querySelector("button[type=submit]");
    if (!choice || !button) { return; }
    function follow() {
      button.disabled = !choice.value;
      if (choice.value === "cancelled") {
        button.dataset.confirm = choice.dataset.cancelConfirm;
      } else {
        delete button.dataset.confirm;
      }
    }
    choice.addEventListener("change", follow);
    follow();
  }
  document.querySelectorAll("[data-status-form]").forEach(prepareStatusForm);

  // A small menu (<details class="menu">) closes when something else is clicked or Escape is pressed.
  document.addEventListener("click", function (event) {
    document.querySelectorAll("details.menu[open]").forEach(function (menu) {
      if (!menu.contains(event.target)) { menu.open = false; }
    });
  });
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") { return; }
    document.querySelectorAll("details.menu[open]").forEach(function (menu) {
      menu.open = false;
      var summary = menu.querySelector("summary");
      if (summary && menu.contains(document.activeElement)) { summary.focus(); }
    });
  });

  document.body.addEventListener("htmx:confirm", function (event) {
    var question = event.detail.question;
    if (!question) { return; }
    event.preventDefault();
    var element = event.detail.elt;
    askDialog(question, "", looksDangerous(element, question)).then(function (yes) {
      if (yes) { event.detail.issueRequest(true); }
    });
  });

  // Short messages that disappear by themselves, instead of the browser's alert box.
  function toast(text) {
    var note = document.createElement("div");
    note.className = "toast";
    note.setAttribute("role", "alert");
    note.textContent = text;
    document.body.appendChild(note);
    window.setTimeout(function () { note.remove(); }, 6000);
  }

  /* ---- Filters that apply as soon as a value is chosen ---------------- */

  document.addEventListener("change", function (event) {
    if (event.target.matches("[data-autosubmit]")) {
      event.target.form.requestSubmit();
    }
  });

  /* ---- Reload a form with a chosen value -------------------------------- */
  // <select data-reload-param="category"> reloads the page with
  // ?category=<value>, so that the server can prefill the rest of the form.

  document.addEventListener("change", function (event) {
    var name = event.target.dataset ? event.target.dataset.reloadParam : null;
    if (name && event.target.value) {
      window.location.search = "?" + name + "=" + encodeURIComponent(event.target.value);
    }
  });

  /* ---- Tick on the packlist ---------------------------------------------- */
  // Rows with a quantity field: the tick writes the full (or zero) quantity
  // into the field before the row's form is sent.

  document.addEventListener("click", function (event) {
    var tick = event.target.closest("button.tick[data-set-quantity]");
    if (!tick) { return; }
    var field = tick.form.querySelector('input[type="number"][name="quantity"]');
    if (field) { field.value = tick.dataset.setQuantity; }
  }, true);

  /* ---- Print button --------------------------------------------------------- */

  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-print]")) { window.print(); }
  });

  /* ---- Copy a value to the clipboard (PRJ-035) ------------------------ */
  // <span class="copy" data-copy="1.234,50"> copies its value on click.

  document.addEventListener("click", function (event) {
    var element = event.target.closest("[data-copy]");
    if (!element || !navigator.clipboard) { return; }
    navigator.clipboard.writeText(element.dataset.copy).then(function () {
      element.classList.add("copied");
      window.setTimeout(function () { element.classList.remove("copied"); }, 900);
    });
  });

  /* ---- Dialog ---------------------------------------------------------- */
  // Links with hx-target="#dialog" load a form into the dialog element.
  // After the content arrived, the dialog opens. A response with the header
  // "HX-Trigger: closeDialog" (sent after a successful save) closes it.

  var dialog = document.getElementById("dialog");

  document.body.addEventListener("htmx:afterSwap", function (event) {
    if (dialog && event.detail.target === dialog && !dialog.open) {
      dialog.showModal();
    }
  });

  // New content may contain search fields and sortable lists; elements that
  // were set up before are skipped (they carry data-ready).
  document.body.addEventListener("htmx:afterSettle", function () {
    initialise(document);
  });

  // A dialog created a record for a field of the page (PRJ-070): put it there.
  document.body.addEventListener("objectCreated", function (event) {
    var detail = event.detail && event.detail.value ? event.detail.value : event.detail;
    if (!detail || !detail.field) { return; }
    // A list (the contact of the project): the new record joins its choices, before "Neuer Ansprechpartner …".
    document.querySelectorAll('select[name="' + detail.field + '"]').forEach(function (select) {
      var create = select.querySelector("option[data-create-url]");
      if (!create) { return; }  // only a list that offers "new …" takes the record
      var option = document.createElement("option");
      option.value = detail.id;
      option.textContent = detail.label;
      select.insertBefore(option, create);
      select.value = String(detail.id);
      select.dataset.before = select.value;
    });
    document.querySelectorAll('[data-typeahead-value][name="' + detail.field + '"]').forEach(function (hidden) {
      var root = hidden.closest("[data-typeahead]");
      var input = root ? root.querySelector("[data-typeahead-input]") : null;
      if (input) { input.value = detail.label; }
      hidden.value = detail.id;
      hidden.dispatchEvent(new Event("change", { bubbles: true }));
    });
  });

  // PRJ-140: the last choice of a list ("Neuer Ansprechpartner …") carries data-create-url: choosing it opens
  // the dialog that creates the record, and the list goes back to what it showed.
  document.addEventListener("focusin", function (event) {
    if (event.target.tagName === "SELECT") { event.target.dataset.before = event.target.value; }
  });
  document.addEventListener("change", function (event) {
    var select = event.target;
    if (!select || select.tagName !== "SELECT" || !select.selectedOptions.length) { return; }
    var url = select.selectedOptions[0].dataset.createUrl;
    if (!url || !window.htmx) { return; }
    select.value = select.dataset.before || "";
    window.htmx.ajax("GET", url, { target: "#dialog", swap: "innerHTML" });
  });

  document.body.addEventListener("closeDialog", function () {
    if (dialog && dialog.open) { dialog.close(); }
  });

  // The same block can stand on a page of its own (the quick entry of time
  // tracking). There is no dialog to close then; the button leads to the
  // page named in data-href instead.
  document.addEventListener("click", function (event) {
    var closer = event.target.closest("[data-close-dialog]");
    if (!closer) { return; }
    if (dialog && dialog.open) {
      dialog.close();
    } else if (closer.dataset.href) {
      window.location.href = closer.dataset.href;
    }
  });

  // Pages that list time entries without refreshing themselves (the report,
  // the deployment view) carry data-reload-after-times. When a time was
  // recorded or corrected in the dialog, they are loaded again once the
  // dialog closes – not earlier, so that its confirmation can be read.
  var timesChanged = false;
  document.body.addEventListener("timesChanged", function () { timesChanged = true; });

  if (dialog) {
    dialog.addEventListener("close", function () {
      dialog.innerHTML = "";
      if (timesChanged && document.querySelector("[data-reload-after-times]")) {
        window.location.reload();
      }
      timesChanged = false;
    });
  }

  /* ---- Show server errors of background requests ----------------------- */

  document.body.addEventListener("htmx:responseError", function (event) {
    var status = event.detail.xhr.status;
    var text = status === 403
      ? document.body.dataset.textForbidden || "Not allowed."
      : document.body.dataset.textError || "The request failed.";
    toast(text);
  });

  /* ---- Search-as-you-type (type-ahead) ---------------------------------- */
  //
  // <div class="typeahead" data-typeahead data-url="/products/suggest/">
  //   <input type="search" data-typeahead-input>
  //   <input type="hidden" name="product" data-typeahead-value>
  // </div>
  //
  // The server answers with JSON: [{"id": 5, "label": "K-005 XLR 5 m", "hint": "9 Stk."}]
  // A result may carry "detail": a second line below the label, e.g. the
  // model or item that was found for the product.

  var typeaheadCount = 0;

  function setUpTypeahead(root) {
    var input = root.querySelector("[data-typeahead-input]");
    var hidden = root.querySelector("[data-typeahead-value]");
    var list = document.createElement("ul");
    var timer = null;
    var selected = -1;
    var results = [];

    list.className = "typeahead-list hidden";
    list.setAttribute("role", "listbox");
    root.appendChild(list);
    // The combobox pattern, as in the address fields (VFG-025): screen readers
    // hear that suggestions open and which one is highlighted.
    typeaheadCount += 1;
    list.id = "typeahead-list-" + typeaheadCount;
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-controls", list.id);

    function close() {
      list.classList.add("hidden");
      selected = -1;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
    }

    function choose(result) {
      if (result.create_url) {
        // PRJ-070: "create … as a new customer" – the form for it opens in the dialog; when it is
        // saved, the answer names the new record ("objectCreated") and it lands in this field.
        close();
        var url = result.create_url + (result.create_url.indexOf("?") === -1 ? "?" : "&") + "field=" + encodeURIComponent(hidden.name);
        // PRJ-101: inside a dialog the form opens over it instead (see the block "create from a type-ahead in a dialog").
        var asked = new CustomEvent("typeaheadCreate", { bubbles: true, cancelable: true, detail: { url: url, input: input } });
        if (root.dispatchEvent(asked)) { htmx.ajax("GET", url, { target: "#dialog" }); }
        return;
      }
      input.value = result.detail ? result.label + " – " + result.detail : result.label;
      hidden.value = result.id;
      close();
      // Other parts of the page (availability check) listen for this.
      hidden.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function render() {
      list.innerHTML = "";
      results.forEach(function (result, index) {
        var item = document.createElement("li");
        var label = document.createElement("span");
        label.textContent = result.label;
        if (result.detail) {
          var detail = document.createElement("small");
          detail.textContent = result.detail;
          label.appendChild(detail);
        }
        item.appendChild(label);
        if (result.hint) {
          var hint = document.createElement("span");
          hint.className = "hint";
          hint.textContent = result.hint;
          item.appendChild(hint);
        }
        if (result.create) { item.classList.add("create"); }
        // Model search: a row that only tells something ("no model without product found").
        if (result.disabled) { item.classList.add("disabled"); item.setAttribute("aria-disabled", "true"); }
        item.id = list.id + "-" + index;
        item.setAttribute("role", "option");
        item.setAttribute("aria-selected", index === selected ? "true" : "false");
        item.addEventListener("mousedown", function (event) {
          event.preventDefault();
          if (!result.disabled) { choose(result); }
        });
        list.appendChild(item);
      });
      var open = results.length > 0;
      list.classList.toggle("hidden", !open);
      input.setAttribute("aria-expanded", open ? "true" : "false");
      if (open && selected >= 0) {
        input.setAttribute("aria-activedescendant", list.id + "-" + selected);
      } else {
        input.removeAttribute("aria-activedescendant");
      }
    }

    function search() {
      var text = input.value.trim();
      if (text.length < 1 && !offersOnFocus) { results = []; render(); return; }
      var url = root.dataset.url + (root.dataset.url.indexOf("?") === -1 ? "?" : "&") + "q=" + encodeURIComponent(text);
      fetch(url, { headers: { "Accept": "application/json" }, credentials: "same-origin" })
        .then(function (response) { return response.ok ? response.json() : []; })
        .then(function (data) {
          // Only the answer to the text that is in the field now counts (an older one may arrive later).
          if (input.value.trim() !== text) { return; }
          results = data;
          selected = firstEnabled(0, 1);
          render();
        });
    }

    // Model search: with data-typeahead-on-focus the field already suggests when it is entered,
    // before anything is typed. Rows with "disabled" only inform; arrow keys and Enter skip them.
    var offersOnFocus = root.hasAttribute("data-typeahead-on-focus");

    function firstEnabled(from, step) {
      for (var index = from; index >= 0 && index < results.length; index += step) {
        if (!results[index].disabled) { return index; }
      }
      return -1;
    }

    // With data-typeahead-free the typed text itself is a valid value (an ID
    // typed in full); without it only a chosen suggestion counts.
    var acceptsTypedText = root.hasAttribute("data-typeahead-free");

    input.addEventListener("input", function () {
      hidden.value = acceptsTypedText ? input.value.trim() : "";
      window.clearTimeout(timer);
      timer = window.setTimeout(search, 180);
    });

    input.addEventListener("keydown", function (event) {
      if (list.classList.contains("hidden")) { return; }
      if (event.key === "ArrowDown") { var down = firstEnabled(selected + 1, 1); if (down >= 0) { selected = down; } render(); event.preventDefault(); }
      else if (event.key === "ArrowUp") { var up = firstEnabled(selected - 1, -1); if (up >= 0) { selected = up; } render(); event.preventDefault(); }
      else if (event.key === "Enter" && selected >= 0) { choose(results[selected]); event.preventDefault(); }
      else if (event.key === "Escape") { close(); }
    });

    input.addEventListener("blur", function () { window.setTimeout(close, 120); });
    if (offersOnFocus) { input.addEventListener("focus", search); }
  }

  /* ---- Sorting lines by dragging (PRJ-014) ------------------------------ */
  //
  // Every group body is <tbody data-sortable data-group="3">. After a drop,
  // the order of all groups is sent to the server, which stores it and
  // returns the refreshed planning.

  // NFA-025: the handle is a button; with the arrow keys it moves its line up
  // or down within the group, for everybody who does not use a mouse.

  function saveLayout(planning, focusLine) {
    var layout = [];
    planning.querySelectorAll("[data-sortable]").forEach(function (body) {
      var ids = [];
      body.querySelectorAll("tr[data-line]").forEach(function (row) { ids.push(Number(row.dataset.line)); });
      layout.push({ group: body.dataset.group ? Number(body.dataset.group) : null, lines: ids });
    });
    fetch(planning.dataset.arrangeUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
      body: JSON.stringify({ layout: layout })
    }).then(function () {
      return htmx.ajax("GET", planning.dataset.refreshUrl, { target: "#planning", swap: "outerHTML" });
    }).then(function () {
      if (!focusLine) { return; }
      var handle = document.querySelector('tr[data-line="' + focusLine + '"] .drag-handle');
      if (handle) { handle.focus(); }
    });
  }

  function setUpSorting(container) {
    var planning = container.closest("[data-arrange-url]");
    if (!planning) { return; }
    container.addEventListener("keydown", function (event) {
      var handle = event.target.closest(".drag-handle");
      if (!handle || (event.key !== "ArrowUp" && event.key !== "ArrowDown")) { return; }
      var row = handle.closest("tr[data-line]");
      var other = event.key === "ArrowUp" ? row.previousElementSibling : row.nextElementSibling;
      while (other && !other.matches("tr[data-line]")) {
        other = event.key === "ArrowUp" ? other.previousElementSibling : other.nextElementSibling;
      }
      event.preventDefault();
      if (!other) { return; }
      row.parentNode.insertBefore(row, event.key === "ArrowUp" ? other : other.nextSibling);
      handle.focus();
      saveLayout(planning, row.dataset.line);
    });
    if (typeof Sortable === "undefined") { return; }
    Sortable.create(container, {
      group: "lines",
      handle: ".drag",
      animation: 120,
      draggable: "tr[data-line]",
      onEnd: function () { saveLayout(planning, null); }
    });
  }

  /* ---- Rows that appear only for certain choices ------------------------ */
  // <div data-show-if="kind=kit"> is shown while the field named "kind" has
  // the value "kit". Several values: data-show-if="kind=rental|sale".

  // <input data-require-if="status=defective"> must be filled in while the
  // field named "status" has that value (the reason for "defective", MAT-044).
  // The server checks the rule in any case; this only asks earlier.

  // UIX-035: "a=x&b=y" holds when both hold, "a=x;b=y" when one of them does (";" binds weaker than "&").

  function oneConditionHolds(element, condition) {
    var parts = condition.split("=");
    var field = (element.closest("form") || document).querySelector('[name="' + parts[0] + '"]');
    if (!field) { return null; }
    var value = field.type === "checkbox" ? (field.checked ? "on" : "") : field.value;
    return parts[1].split("|").indexOf(value) !== -1;
  }

  function conditionHolds(element, condition) {
    var result = null;
    condition.split(";").forEach(function (alternative) {
      var all = null;
      alternative.split("&").forEach(function (part) {
        var holds = oneConditionHolds(element, part);
        if (holds !== null) { all = all === null ? holds : all && holds; }
      });
      if (all !== null) { result = result === null ? all : result || all; }
    });
    return result;
  }

  function applyConditions(root) {
    root.querySelectorAll("[data-show-if]").forEach(function (element) {
      var holds = conditionHolds(element, element.dataset.showIf);
      if (holds !== null) { element.classList.toggle("hidden", !holds); }
    });
    root.querySelectorAll("[data-require-if]").forEach(function (element) {
      var holds = conditionHolds(element, element.dataset.requireIf);
      if (holds !== null) { element.required = holds; }
    });
  }

  document.addEventListener("change", function (event) {
    var form = event.target.closest("form");
    if (form) { applyConditions(form); }
  });

  /* ---- Product descriptions follow the kind of document ----------- */
  // <input type="checkbox" data-description-defaults='{"offer": true, "invoice": false}'> takes the choice the
  // template of the kind chosen in the field "kind" makes – until somebody ticks or clears it by hand.

  document.addEventListener("change", function (event) {
    var field = event.target;
    var form = field.closest ? field.closest("form") : null;
    if (!form) { return; }
    if (field.matches("[data-description-defaults]")) { field.dataset.touched = "1"; return; }
    if (field.name !== "kind") { return; }
    var box = form.querySelector("[data-description-defaults]");
    if (!box || box.dataset.touched) { return; }
    var defaults = {};
    try { defaults = JSON.parse(box.dataset.descriptionDefaults || "{}"); } catch (error) { return; }
    if (field.value in defaults) { box.checked = !!defaults[field.value]; }
  });

  /* ---- People for the chosen job function (PER-025) ---------------------- */
  // <select data-people-for="job_function"> lists people whose options carry
  // data-functions="3,7". Only the people with the job function chosen in the
  // same form are offered; with data-any="1" (the right to plan outside the
  // job functions) the others stay choosable, set apart by a class.

  function filterPeople(select, resetHidden) {
    var form = select.closest("form");
    var functionField = form && form.querySelector('[name="' + select.dataset.peopleFor + '"]');
    if (!functionField) { return; }
    var chosen = functionField.value;
    var any = select.dataset.any === "1";
    Array.prototype.forEach.call(select.options, function (option) {
      if (!option.value) { return; }
      var has = !chosen || (option.dataset.functions || "").split(",").indexOf(chosen) !== -1;
      option.hidden = !has && !any;
      option.disabled = !has && !any;
      option.classList.toggle("other-function", !has);
    });
    var current = select.options[select.selectedIndex];
    if (resetHidden && current && current.disabled) { select.value = ""; }
  }

  document.addEventListener("change", function (event) {
    var form = event.target.closest("form");
    if (!form || !event.target.name) { return; }
    form.querySelectorAll('select[data-people-for="' + event.target.name + '"]').forEach(function (select) {
      filterPeople(select, true);
    });
  });

  /* ---- A phase brings its period (PRJ-080) -------------------------------- */
  // <select data-fills-period="start,end"> lists phases whose options carry
  // data-start and data-end. Choosing one fills the two named fields of the
  // same form with its period; the server does the same for a form sent
  // without this script.

  document.addEventListener("change", function (event) {
    var select = event.target;
    if (!select.matches || !select.matches("select[data-fills-period]")) { return; }
    var option = select.options[select.selectedIndex];
    var form = select.closest("form");
    if (!form || !option || !option.dataset.start) { return; }
    var names = select.dataset.fillsPeriod.split(",");
    var values = [option.dataset.start, option.dataset.end];
    var fields = names.map(function (name) { return form.querySelector('[name="' + name + '"]'); });
    fields.forEach(function (field, index) {
      if (field && values[index]) { field.value = values[index]; }
    });
    // PRJ-092: a phase may lie before the period typed so far (a planning meeting before the rental
    // period). "Until" must not stay bound to the former "from" (UIX-025), or the browser refuses to send
    // the form; the change of "until" lets the pair keep the phase's length from now on.
    if (fields[0] && fields[1] && fields[1].min && fields[0].value) {
      fields[1].min = fields[0].value;
      fields[1].dispatchEvent(new Event("change", { bubbles: true }));
    }
  });

  /* ---- Running stopwatch (ZEI-005) ---------------------------------------- */
  // <strong data-timer-since="2027-03-01T08:00:00+01:00">08:00</strong> shows
  // how long the stopwatch has been running, counted up every second. The
  // server stores only the start; closing the page loses nothing.

  function twoDigits(number) { return (number < 10 ? "0" : "") + number; }

  function tickTimers() {
    document.querySelectorAll("[data-timer-since]").forEach(function (element) {
      var since = Date.parse(element.dataset.timerSince);
      if (isNaN(since)) { return; }
      var seconds = Math.max(0, Math.floor((Date.now() - since) / 1000));
      element.textContent = Math.floor(seconds / 3600) + ":" + twoDigits(Math.floor(seconds / 60) % 60) + ":" + twoDigits(seconds % 60);
    });
  }

  window.setInterval(tickTimers, 1000);

  /* ---- Choosing many rows at once (MAT-029) ----------------------------- */
  // <input data-check-all="items"> ticks or clears every box named "items";
  // [data-chosen-count="items"] shows how many are ticked.

  // UIX-048: <form data-bulk-bar="items" hidden> – the actions for the ticked rows – shows only while a
  // box named "items" is ticked, like the "chosen lines" of the planning; [data-bulk-clear="items"] unticks all.
  function countChosen(name) {
    var count = document.querySelectorAll('input[type="checkbox"][name="' + name + '"]:checked').length;
    document.querySelectorAll('[data-chosen-count="' + name + '"]').forEach(function (element) {
      element.textContent = count;
    });
    document.querySelectorAll('[data-bulk-bar="' + name + '"]').forEach(function (bar) {
      bar.hidden = count === 0;
    });
  }

  document.addEventListener("click", function (event) {
    var clear = event.target.closest ? event.target.closest("[data-bulk-clear]") : null;
    if (!clear) { return; }
    var name = clear.dataset.bulkClear;
    document.querySelectorAll('input[type="checkbox"][name="' + name + '"], [data-check-all="' + name + '"]').forEach(function (box) {
      box.checked = false;
    });
    countChosen(name);
  });

  // A page shown again from the browser's history may come with ticked boxes: the bar follows them.
  function countAllChosen() {
    document.querySelectorAll("[data-bulk-bar]").forEach(function (bar) { countChosen(bar.dataset.bulkBar); });
  }
  countAllChosen();
  window.addEventListener("pageshow", countAllChosen);

  document.addEventListener("change", function (event) {
    var all = event.target.closest("[data-check-all]");
    if (all) {
      document.querySelectorAll('input[type="checkbox"][name="' + all.dataset.checkAll + '"]').forEach(function (box) {
        box.checked = all.checked;
      });
      countChosen(all.dataset.checkAll);
      return;
    }
    if (event.target.matches('input[type="checkbox"][name]')) { countChosen(event.target.name); }
  });

  /* ---- Sorting small tables in the browser (UIX-015) -------------------- */
  // <table data-sort-table>: every heading becomes a button that sorts the
  // rows by that column; a second press reverses the order. A cell may carry
  // data-sort-value with a value to sort by (a date as 2027-03-01). Lists
  // with pages are sorted by the server instead.

  function sortValue(cell) {
    var text = (cell.dataset.sortValue !== undefined ? cell.dataset.sortValue : cell.textContent).trim();
    // UIX-029: 16.10.2026 in German, 16/10/2026 in English; English numbers have a decimal point.
    var date = text.match(/^(\d{1,2})[./](\d{1,2})[./](\d{2,4})/);
    if (date) { return { number: Number(date[3]) * 10000 + Number(date[2]) * 100 + Number(date[1]) }; }
    var english = /^en/i.test(document.documentElement.lang || "");
    var number = english
      ? text.replace(/\s|€|%|,/g, "")
      : text.replace(/\s|€|%/g, "").replace(/\./g, "").replace(",", ".");
    if (number !== "" && !isNaN(Number(number))) { return { number: Number(number) }; }
    return { text: text.toLowerCase() };
  }

  function setUpTableSorting(table) {
    var headings = table.tHead ? table.tHead.rows[0].cells : [];
    Array.prototype.forEach.call(headings, function (heading, index) {
      if (!heading.textContent.trim()) { return; }
      var button = document.createElement("button");
      button.type = "button";
      button.className = "sort-btn";
      while (heading.firstChild) { button.appendChild(heading.firstChild); }
      heading.appendChild(button);
      button.addEventListener("click", function () {
        var ascending = heading.getAttribute("aria-sort") !== "ascending";
        Array.prototype.forEach.call(headings, function (other) { other.removeAttribute("aria-sort"); });
        heading.setAttribute("aria-sort", ascending ? "ascending" : "descending");
        Array.prototype.forEach.call(table.tBodies, function (body) {
          var rows = Array.prototype.slice.call(body.rows);
          rows.sort(function (first, second) {
            var a = sortValue(first.cells[index] || first), b = sortValue(second.cells[index] || second);
            var result = (a.number !== undefined && b.number !== undefined) ? a.number - b.number
              : String(a.text !== undefined ? a.text : a.number).localeCompare(String(b.text !== undefined ? b.text : b.number), "de");
            return ascending ? result : -result;
          });
          rows.forEach(function (row) { body.appendChild(row); });
        });
      });
    });
  }

  /* ---- Periods: "until" after "from", chosen in a calendar (UIX-025) ---- */
  // Every pair of date or date-time fields named "…start" and "…end" in one
  // form: the end can never lie before the start, a moved start takes the
  // end along (the length stays), and a button opens a calendar in which the
  // first click sets the first day and the second the last – instead of
  // choosing day and time in two separate fields.

  var texts = document.body.dataset;

  function pad(number) { return (number < 10 ? "0" : "") + number; }
  function isoDay(date) { return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate()); }
  function parseField(input) {
    if (!input.value) { return null; }
    var parts = input.value.split("T");
    var day = parts[0].split("-");
    var time = (parts[1] || "00:00").split(":");
    return new Date(Number(day[0]), Number(day[1]) - 1, Number(day[2]), Number(time[0]), Number(time[1]));
  }
  function writeField(input, date) {
    var value = isoDay(date);
    if (input.type === "datetime-local") { value += "T" + pad(date.getHours()) + ":" + pad(date.getMinutes()); }
    input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function setUpRange(start, end) {
    var length = null;
    // Lengths are counted in wall-clock time, so that noon to noon stays noon to noon
    // across the change to and from summer time.
    function wall(date) {
      return Date.UTC(date.getFullYear(), date.getMonth(), date.getDate(), date.getHours(), date.getMinutes());
    }
    function fromWall(milliseconds) {
      var date = new Date(milliseconds);
      return new Date(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate(), date.getUTCHours(), date.getUTCMinutes());
    }
    function remember() {
      var a = parseField(start), b = parseField(end);
      if (a && b && b > a) { length = wall(b) - wall(a); }
    }
    function limit() { if (start.value) { end.min = start.value; } }
    remember();
    limit();
    // Moving the start moves the end along, keeping the length: "until" follows "from".
    start.addEventListener("change", function () {
      var a = parseField(start), b = parseField(end);
      limit();
      if (!a) { return; }
      if (length !== null || !b || b <= a) {
        var fallback = start.type === "datetime-local" ? 24 * 3600 * 1000 : 0;
        writeField(end, fromWall(wall(a) + (length !== null ? length : fallback)));
      }
      remember();
    });
    end.addEventListener("change", function () {
      var a = parseField(start), b = parseField(end);
      if (a && b && b < a) { writeField(end, a); }
      remember();
    });

    var button = document.createElement("button");
    button.type = "button";
    button.className = "btn secondary small range-btn";
    button.textContent = texts.textRange || "Choose the period";
    // PRJ-099: a form may keep a place for the button in the row of the fields (data-range-slot="…start").
    var slot = start.form && start.form.querySelector('[data-range-slot="' + start.name + '"]');
    if (slot) {
      slot.appendChild(button);
    } else {
      var holder = end.closest(".field") || end.parentNode;
      holder.parentNode.insertBefore(button, holder.nextSibling);
    }
    button.addEventListener("click", function () { openRangePicker(start, end); });
  }

  function openRangePicker(start, end) {
    var locale = document.documentElement.lang || "de";
    var withTime = start.type === "datetime-local";
    var first = parseField(start), last = parseField(end);
    var shown = first ? new Date(first.getFullYear(), first.getMonth(), 1) : new Date(new Date().getFullYear(), new Date().getMonth(), 1);
    var pickedFrom = first ? new Date(first.getFullYear(), first.getMonth(), first.getDate()) : null;
    var pickedUntil = last ? new Date(last.getFullYear(), last.getMonth(), last.getDate()) : null;

    var box = document.createElement("dialog");
    box.className = "dialog range-picker";
    box.setAttribute("aria-label", texts.textRange || "Choose the period");
    var head = document.createElement("div");
    head.className = "dialog-head";
    var title = document.createElement("strong");
    var hint = document.createElement("span");
    hint.className = "muted small";
    head.appendChild(title);
    var body = document.createElement("div");
    body.className = "dialog-body";
    var nav = document.createElement("div");
    nav.className = "range-nav";
    var previous = document.createElement("button");
    previous.type = "button"; previous.className = "icon-btn"; previous.textContent = "‹";
    previous.setAttribute("aria-label", texts.textEarlier || "Earlier");
    var next = document.createElement("button");
    next.type = "button"; next.className = "icon-btn"; next.textContent = "›";
    next.setAttribute("aria-label", texts.textLater || "Later");
    nav.appendChild(previous); nav.appendChild(hint); nav.appendChild(next);
    var months = document.createElement("div");
    months.className = "range-months";
    body.appendChild(nav); body.appendChild(months);
    var times = document.createElement("div");
    times.className = "form-row pair keep range-times";
    function timeField(label, date, fallback) {
      var field = document.createElement("label");
      field.className = "field";
      var caption = document.createElement("span");
      caption.className = "label";
      caption.textContent = label;
      var input = document.createElement("input");
      input.type = "time";
      input.value = date ? pad(date.getHours()) + ":" + pad(date.getMinutes()) : fallback;
      field.appendChild(caption); field.appendChild(input);
      times.appendChild(field);
      return input;
    }
    var fromTime = null, untilTime = null;
    // PRJ-099: the other periods of the form (rental, event) hatched, with a legend (UIX-036 block below).
    var calendarTools = window.Rentalars && window.Rentalars.calendar;
    var marks = calendarTools ? calendarTools.marks(start, [start.name, end.name]) : [];
    var legend = calendarTools ? calendarTools.legend(marks) : null;
    if (legend) { body.appendChild(legend); }
    if (withTime) {
      fromTime = timeField(texts.textFromTime || "From", first, "12:00");
      untilTime = timeField(texts.textUntilTime || "Until", last, "12:00");
      body.appendChild(times);
      // UIX-036: the two times get the clock face as well.
      if (window.Rentalars && window.Rentalars.enhancePickers) { window.Rentalars.enhancePickers(times); }
    }
    var foot = document.createElement("div");
    foot.className = "dialog-foot";
    var cancel = document.createElement("button");
    cancel.type = "button"; cancel.className = "btn secondary"; cancel.textContent = texts.textCancel || "Cancel";
    var apply = document.createElement("button");
    apply.type = "button"; apply.className = "btn"; apply.textContent = texts.textApply || "Apply";
    foot.appendChild(cancel); foot.appendChild(apply);
    box.appendChild(head); box.appendChild(body); box.appendChild(foot);
    document.body.appendChild(box);

    var monthFormat = new Intl.DateTimeFormat(locale, { month: "long", year: "numeric" });
    var dayFormat = new Intl.DateTimeFormat(locale, { weekday: "short" });
    var longFormat = new Intl.DateTimeFormat(locale, { weekday: "short", day: "numeric", month: "numeric", year: "numeric" });

    function describe() {
      title.textContent = pickedFrom
        ? longFormat.format(pickedFrom) + " – " + (pickedUntil ? longFormat.format(pickedUntil) : "…")
        : (texts.textPickStart || "Click the first day");
      hint.textContent = pickedFrom && !pickedUntil ? (texts.textPickEnd || "now the last day") : "";
      apply.disabled = !pickedFrom;
    }

    function renderMonth(firstOfMonth) {
      var table = document.createElement("table");
      table.className = "range-month";
      var caption = document.createElement("caption");
      caption.textContent = monthFormat.format(firstOfMonth);
      table.appendChild(caption);
      var headRow = document.createElement("tr");
      for (var weekday = 0; weekday < 7; weekday++) {
        var th = document.createElement("th");
        th.scope = "col";
        th.textContent = dayFormat.format(new Date(2024, 0, 1 + weekday));  // 1 Jan 2024 was a Monday
        headRow.appendChild(th);
      }
      var thead = document.createElement("thead");
      thead.appendChild(headRow);
      table.appendChild(thead);
      var tbody = document.createElement("tbody");
      var day = new Date(firstOfMonth);
      day.setDate(1 - ((firstOfMonth.getDay() + 6) % 7));
      var today = isoDay(new Date());
      for (var week = 0; week < 6; week++) {
        var row = document.createElement("tr");
        for (var column = 0; column < 7; column++) {
          var cell = document.createElement("td");
          if (day.getMonth() === firstOfMonth.getMonth()) {
            var pick = document.createElement("button");
            pick.type = "button";
            pick.textContent = day.getDate();
            pick.dataset.day = isoDay(day);
            pick.setAttribute("aria-label", longFormat.format(day));
            if (calendarTools) { calendarTools.markDay(pick, day, marks); }
            var time = day.getTime();
            var inRange = pickedFrom && pickedUntil && time >= pickedFrom.getTime() && time <= pickedUntil.getTime();
            var isEdge = (pickedFrom && time === pickedFrom.getTime()) || (pickedUntil && time === pickedUntil.getTime());
            if (inRange) { pick.classList.add("in-range"); }
            if (isEdge) { pick.classList.add("edge"); pick.setAttribute("aria-pressed", "true"); }
            if (isoDay(day) === today) { pick.classList.add("today"); }
            cell.appendChild(pick);
          }
          row.appendChild(cell);
          day.setDate(day.getDate() + 1);
        }
        tbody.appendChild(row);
      }
      table.appendChild(tbody);
      return table;
    }

    function render() {
      months.innerHTML = "";
      months.appendChild(renderMonth(shown));
      if (window.matchMedia("(min-width: 640px)").matches) {
        months.appendChild(renderMonth(new Date(shown.getFullYear(), shown.getMonth() + 1, 1)));
      }
      describe();
    }

    months.addEventListener("click", function (event) {
      var pick = event.target.closest("button[data-day]");
      if (!pick) { return; }
      var parts = pick.dataset.day.split("-");
      var chosen = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
      if (!pickedFrom || pickedUntil) {
        pickedFrom = chosen; pickedUntil = null;
      } else if (chosen < pickedFrom) {
        pickedUntil = pickedFrom; pickedFrom = chosen;
      } else {
        pickedUntil = chosen;
      }
      render();
      var again = months.querySelector('button[data-day="' + pick.dataset.day + '"]');
      if (again) { again.focus(); }
    });
    previous.addEventListener("click", function () { shown = new Date(shown.getFullYear(), shown.getMonth() - 1, 1); render(); });
    next.addEventListener("click", function () { shown = new Date(shown.getFullYear(), shown.getMonth() + 1, 1); render(); });
    cancel.addEventListener("click", function () { box.close(); });
    apply.addEventListener("click", function () {
      var until = pickedUntil || pickedFrom;
      var from = new Date(pickedFrom);
      var to = new Date(until);
      if (withTime) {
        var a = fromTime.value.split(":"), b = untilTime.value.split(":");
        from.setHours(Number(a[0]) || 0, Number(a[1]) || 0);
        to.setHours(Number(b[0]) || 0, Number(b[1]) || 0);
        if (to <= from) { to.setDate(to.getDate() + 1); }  // noon to noon on one day: until the next
      }
      writeField(start, from);
      writeField(end, to);
      box.close();
    });
    box.addEventListener("close", function () { box.remove(); start.focus(); });
    render();
    box.showModal();
    var focusDay = months.querySelector("button.edge") || months.querySelector("button[data-day]");
    if (focusDay) { focusDay.focus(); }
  }

  function setUpRanges(root) {
    root.querySelectorAll('input[type="datetime-local"][name$="start"], input[type="date"][name$="start"]').forEach(function (start) {
      if (start.dataset.rangeReady) { return; }
      var form = start.form || start.closest("form");
      if (!form) { return; }
      var end = form.querySelector('input[name="' + start.name.replace(/start$/, "end") + '"]');
      if (!end || end.type !== start.type) { return; }
      start.dataset.rangeReady = "1";
      setUpRange(start, end);
    });
  }

  /* ---- Pages that follow changes (UIX-020) ------------------------------ */
  // <main data-watch="project:42,notifications" data-changes-url="/changes/">
  // asks every twenty seconds whether what the page shows has changed – a
  // mail arrived, a colleague added a line. If so, the page loads itself
  // again, keeping the scroll position; while somebody types in it or a
  // dialog is open, a note offers to do so instead. The page's own requests
  // that change something are taken over as the state it shows, so that
  // one's own saving never reloads the page.

  var POLL_SECONDS = 20;
  var watchRoot = document.getElementById("content");
  var watchedKeys = watchRoot && watchRoot.dataset.watch ? watchRoot.dataset.watch : "";
  var knownStamps = null;
  var lastInput = 0;
  var SCROLL_KEY = "rentalars-scroll";

  document.addEventListener("input", function () { lastInput = Date.now(); }, true);
  document.addEventListener("keydown", function () { lastInput = Date.now(); }, true);

  function isBusy() {
    var active = document.activeElement;
    if (active && active.closest && active.closest("input, textarea, select, [contenteditable]") && active.id !== "nav-search") { return true; }
    if (document.querySelector("dialog[open]")) { return true; }
    if (document.body.classList.contains("nav-open")) { return true; }
    if (window.getSelection && String(window.getSelection()).length > 0) { return true; }
    return Date.now() - lastInput < 15000;
  }

  function updateBell(count) {
    document.querySelectorAll(".bell .count, .bell-link .badge").forEach(function (badge) {
      badge.textContent = count;
      badge.classList.toggle("hidden", !count);
    });
  }

  function reloadKeepingPlace() {
    try { window.sessionStorage.setItem(SCROLL_KEY, JSON.stringify({ path: location.pathname + location.search, y: window.scrollY })); } catch (error) { /* private mode */ }
    window.location.reload();
  }

  // PER-033: a project's stamp reads "<newest change>.<newest change by somebody else>". After
  // the page's own change only the second part counts – an answer by mail or a colleague's
  // change that came in just before is not swallowed with one's own.
  function othersPart(stamp) {
    var dot = (stamp || "").indexOf(".");
    return dot < 0 ? null : stamp.slice(dot + 1);
  }

  // Stock refresh: puts the availability cells, the wishes and the hints above the lines of the open
  // planning in place, one by one. Nothing else of the page is touched: typed text, the scroll position, open
  // dialogs and the focus stay. One request, built from the page's own url (data-stock-url).
  //
  // (R3-7) The stamp is global (any save anywhere moves it), so the tab protects the server and
  // itself: at most one refresh every STOCK_MIN_INTERVAL ms however many changes it sees; a change that arrives
  // while the figures are being fetched runs one more refresh afterwards; a request that hangs is given up after
  // STOCK_TIMEOUT ms and the tab can ask again; a cell the user has the focus in, or that the page has put in place
  // anew since the request started (it is fresher than the answer), is left alone.
  var STOCK_MIN_INTERVAL = 20000;
  var STOCK_TIMEOUT = 15000;
  var stockRequest = null;
  var stockWanted = false;
  var stockTimer = null;
  var lastStockStart = 0;

  function refreshStock() {
    stockWanted = true;
    if (stockRequest || stockTimer) { return; }
    var wait = lastStockStart + STOCK_MIN_INTERVAL - Date.now();
    if (wait > 0) {
      stockTimer = window.setTimeout(function () { stockTimer = null; if (stockWanted) { refreshStock(); } }, wait);
      return;
    }
    fetchStock();
  }

  function fetchStock() {
    var planning = document.getElementById("planning");
    if (!planning || !planning.dataset.stockUrl) { stockWanted = false; return; }
    stockWanted = false;
    lastStockStart = Date.now();
    var token = {};
    stockRequest = token;
    var controller = window.AbortController ? new AbortController() : null;
    var finished = false;
    function finish() {
      if (finished) { return; }
      finished = true;
      window.clearTimeout(giveUp);
      if (stockRequest === token) { stockRequest = null; }
      if (stockWanted) { refreshStock(); }
    }
    var giveUp = window.setTimeout(function () { if (controller) { controller.abort(); } finish(); }, STOCK_TIMEOUT);
    // What the page shows now: whatever is replaced before the answer comes is fresher than the answer.
    var cellsThen = new Set(planning.querySelectorAll("[data-stock-cell], [data-stock-wish]"));
    var notesThen = document.getElementById("planning-notes");
    fetch(planning.dataset.stockUrl, { credentials: "same-origin", headers: { "HX-Request": "true" }, signal: controller ? controller.signal : undefined })
      .then(function (response) { return response.ok ? response.text() : ""; })
      .then(function (html) {
        if (!html || finished) { return; }
        var holder = document.createElement("div");
        holder.innerHTML = html;
        function mayReplace(element, fresh) {
          if (element.innerHTML.trim() === fresh.innerHTML.trim()) { return false; }  // nothing to put in
          if (!cellsThen.has(element) || !document.contains(element)) { return false; }
          if (element.contains(document.activeElement)) { stockWanted = true; return false; }  // later
          return true;
        }
        holder.querySelectorAll("template[data-stock-line]").forEach(function (template) {
          var row = document.getElementById("line-" + template.dataset.stockLine);
          if (!row) { return; }
          var cell = row.querySelector("[data-stock-cell]");
          var wish = row.querySelector("[data-stock-wish]");
          var cellHtml = template.content.querySelector('[data-part="cell"]');
          var wishHtml = template.content.querySelector('[data-part="wish"]');
          if (cell && cellHtml && mayReplace(cell, cellHtml)) {
            cell.innerHTML = cellHtml.innerHTML;
            if (window.htmx) { window.htmx.process(cell); }
          }
          if (wish && wishHtml && mayReplace(wish, wishHtml)) { wish.innerHTML = wishHtml.innerHTML; }
        });
        var notes = holder.querySelector("template[data-stock-notes]");
        var shown = document.getElementById("planning-notes");
        var fresh = notes && notes.content.querySelector("#planning-notes");
        if (shown && shown === notesThen && fresh && shown.innerHTML.trim() !== fresh.innerHTML.trim()) {
          if (shown.contains(document.activeElement)) { stockWanted = true; } else {
            shown.innerHTML = fresh.innerHTML;
            if (window.htmx) { window.htmx.process(shown); }
          }
        }
      })
      .catch(function () { /* the next change asks again */ })
      .then(finish);
  }

  var lastPoll = 0;
  function pollChanges(adoptOnly) {
    if (!watchedKeys || document.hidden) { return; }
    lastPoll = Date.now();
    fetch(watchRoot.dataset.changesUrl + "?keys=" + encodeURIComponent(watchedKeys), { credentials: "same-origin", headers: { "Accept": "application/json" } })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (data) {
        if (!data) { return; }
        updateBell(data.unread);
        var stamps = data.stamps || {};
        // UIX-010: the chat follows its own key in place (block "Chat in the project" at the end).
        document.dispatchEvent(new CustomEvent("rentalars:stamps", { detail: stamps }));
        if (knownStamps === null) { knownStamps = stamps; return; }
        // Stock refresh: "stock:" moves when material, models or other projects change what the
        // planning shows as availability; the cells are fetched in place, the page is not loaded again.
        var stockMoved = Object.keys(stamps).some(function (key) {
          return !adoptOnly && key.indexOf("stock:") === 0 && stamps[key] && stamps[key] !== knownStamps[key];
        });
        var changed = Object.keys(stamps).some(function (key) {
          if (key === "notifications" || key.indexOf("chat:") === 0 || key.indexOf("stock:") === 0 || !stamps[key]) { return false; }
          if (adoptOnly) {
            var others = othersPart(stamps[key]);
            return others !== null && others !== othersPart(knownStamps[key]);
          }
          return stamps[key] !== knownStamps[key];
        });
        knownStamps = stamps;
        if (!changed) { if (stockMoved) { refreshStock(); } return; }
        if (stockMoved) { refreshStock(); }
        if (isBusy()) {
          document.getElementById("changed-note").classList.remove("hidden");
        } else {
          reloadKeepingPlace();
        }
      })
      .catch(function () { /* offline for a moment: the next round asks again */ });
  }

  if (watchedKeys) {
    pollChanges(true);
    window.setInterval(function () { pollChanges(false); }, POLL_SECONDS * 1000);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) { pollChanges(false); } });
    // Stock refresh: two windows side by side never hide a tab – coming back to one asks as well (at most every 3 s).
    window.addEventListener("focus", function () { if (Date.now() - lastPoll > 3000) { pollChanges(false); } });
    // After the page's own changes, their state is the one it shows.
    document.body.addEventListener("htmx:afterRequest", function (event) {
      var verb = (event.detail.requestConfig && event.detail.requestConfig.verb) || "get";
      if (verb.toLowerCase() !== "get") { window.setTimeout(function () { pollChanges(true); }, 300); }
    });
  }

  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-reload-page]")) { reloadKeepingPlace(); }
  });

  try {
    var place = JSON.parse(window.sessionStorage.getItem(SCROLL_KEY) || "null");
    window.sessionStorage.removeItem(SCROLL_KEY);
    if (place && place.path === location.pathname + location.search) {
      window.addEventListener("load", function () { window.scrollTo(0, place.y); });
    }
  } catch (error) { /* no storage */ }

  /* ---- Start-up ----------------------------------------------------------- */

  function initialise(root) {
    root.querySelectorAll("[data-typeahead]").forEach(function (element) {
      if (!element.dataset.ready) { element.dataset.ready = "1"; setUpTypeahead(element); }
    });
    root.querySelectorAll("[data-sortable]").forEach(function (element) {
      if (!element.dataset.ready) { element.dataset.ready = "1"; setUpSorting(element); }
    });
    root.querySelectorAll("table[data-sort-table]").forEach(function (element) {
      if (!element.dataset.ready) { element.dataset.ready = "1"; setUpTableSorting(element); }
    });
    root.querySelectorAll("select[data-people-for]").forEach(function (select) { filterPeople(select, false); });
    setUpRanges(root);
    applyConditions(root);
    tickTimers();
    var focus = root.querySelector("[data-autofocus]");
    if (focus) { focus.focus(); }
  }

  initialise(document);
})();

/*
 * Mail (chapter 5.15).
 *
 *  - suggestions in the address fields To, CC and BCC (EML-037);
 *  - placeholders and a live preview in the signature editor (EML-034);
 *  - the conversation of a project opens at the newest message (EML-036);
 *  - the crew or the customer into "To" with one click (EML-043).
 *
 * Wired through data- attributes; no inline scripts (the content security
 * policy forbids them). Everything works without this file as well: the
 * fields take typed addresses, the preview has a button.
 */
(function () {
  "use strict";

  /* ---- Address suggestions (EML-037) ------------------------------------ */
  //
  // <input data-address-suggest="/projects/mail-addresses/"> holds several addresses,
  // separated by commas or semicolons. From three characters on, the part
  // the cursor stands in is sent to the server, which answers with JSON:
  // [{"id": "Anna Becker <anna@x.example>", "label": "…", "hint": "Kontakt", "detail": "Firma"}].
  // Choosing one replaces only that part and adds ", " for the next address.

  var MIN_LENGTH = 3;

  // The part around the cursor: from the separator before it to the one after
  // it. A comma inside quotes ("Müller, Hans" <h@x.example>) separates nothing.
  function partAround(value, cursor) {
    var start = 0;
    var end = value.length;
    var quoted = false;
    var index;
    for (index = 0; index < value.length; index++) {
      var character = value.charAt(index);
      if (character === "\"") {
        quoted = !quoted;
      } else if (!quoted && (character === "," || character === ";")) {
        if (index < cursor) {
          start = index + 1;
        } else {
          end = index;
          break;
        }
      }
    }
    return { start: start, end: end, text: value.slice(start, end).trim() };
  }

  function cursorOf(input) {
    return input.selectionStart === null || input.selectionStart === undefined ? input.value.length : input.selectionStart;
  }

  function setUpAddressField(input) {
    var wrapper = document.createElement("div");
    var list = document.createElement("ul");
    var results = [];
    var selected = -1;
    var timer = null;
    var asked = 0;

    wrapper.className = "address-suggest";
    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);
    list.className = "typeahead-list hidden";
    list.id = (input.id || input.name) + "-suggestions";
    list.setAttribute("role", "listbox");
    wrapper.appendChild(list);
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-controls", list.id);

    function close() {
      results = [];
      selected = -1;
      list.classList.add("hidden");
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
    }

    function choose(result) {
      var value = input.value;
      var part = partAround(value, cursorOf(input));
      var before = value.slice(0, part.start).replace(/\s+$/, "");
      var after = value.slice(part.end).replace(/^[\s,;]+/, "");
      var head = (before ? before + " " : "") + result.id + ", ";
      input.value = head + after;
      input.setSelectionRange(head.length, head.length);
      close();
      input.focus();
    }

    function render() {
      list.innerHTML = "";
      results.forEach(function (result, index) {
        var item = document.createElement("li");
        var label = document.createElement("span");
        item.id = list.id + "-" + index;
        item.setAttribute("role", "option");
        item.setAttribute("aria-selected", index === selected ? "true" : "false");
        label.textContent = result.label;
        if (result.detail) {
          var detail = document.createElement("small");
          detail.textContent = result.detail;
          label.appendChild(detail);
        }
        item.appendChild(label);
        if (result.hint) {
          var hint = document.createElement("span");
          hint.className = "hint";
          hint.textContent = result.hint;
          item.appendChild(hint);
        }
        item.addEventListener("mousedown", function (event) {
          event.preventDefault();
          choose(result);
        });
        list.appendChild(item);
      });
      var open = results.length > 0;
      list.classList.toggle("hidden", !open);
      input.setAttribute("aria-expanded", open ? "true" : "false");
      if (open && selected >= 0) {
        input.setAttribute("aria-activedescendant", list.id + "-" + selected);
      } else {
        input.removeAttribute("aria-activedescendant");
      }
    }

    function search() {
      var part = partAround(input.value, cursorOf(input));
      if (part.text.length < MIN_LENGTH) { close(); return; }
      var number = ++asked;
      var url = input.dataset.addressSuggest + "?q=" + encodeURIComponent(part.text);
      fetch(url, { headers: { "Accept": "application/json" }, credentials: "same-origin" })
        .then(function (response) { return response.ok ? response.json() : []; })
        .then(function (data) {
          if (number !== asked) { return; }  // an answer to an older question
          results = data;
          selected = data.length ? 0 : -1;
          render();
        })
        .catch(close);
    }

    input.addEventListener("input", function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(search, 200);
    });

    input.addEventListener("keydown", function (event) {
      if (list.classList.contains("hidden")) { return; }
      if (event.key === "ArrowDown") {
        selected = Math.min(selected + 1, results.length - 1);
        render();
        event.preventDefault();
      } else if (event.key === "ArrowUp") {
        selected = Math.max(selected - 1, 0);
        render();
        event.preventDefault();
      } else if (event.key === "Enter" && selected >= 0) {
        // Enter takes the suggestion instead of sending the form.
        choose(results[selected]);
        event.preventDefault();
      } else if (event.key === "Escape") {
        close();
        event.preventDefault();
      }
    });

    input.addEventListener("blur", function () { window.setTimeout(close, 150); });
  }

  /* ---- Signature editor (EML-034) ---------------------------------------- */
  //
  // <button data-insert-placeholder="{vorname}"> puts the placeholder into the
  // textarea [data-signature-source] at the cursor. While typing, the button
  // [data-signature-preview] is pressed after a short pause: it sends the
  // draft into the preview frame (formtarget), so the preview follows.

  function setUpSignatureForm(form) {
    var source = form.querySelector("[data-signature-source]");
    var preview = form.querySelector("[data-signature-preview]");
    var timer = null;
    if (!source) { return; }

    function refresh() {
      window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        if (preview && form.requestSubmit) { form.requestSubmit(preview); }
      }, 500);
    }

    form.addEventListener("click", function (event) {
      var button = event.target.closest("[data-insert-placeholder]");
      if (!button) { return; }
      var token = button.dataset.insertPlaceholder;
      var start = source.selectionStart === null ? source.value.length : source.selectionStart;
      var end = source.selectionEnd === null ? start : source.selectionEnd;
      source.focus();
      source.setRangeText(token, start, end, "end");
      refresh();
    });

    source.addEventListener("input", refresh);
  }

  /* ---- Conversation (EML-036) ---------------------------------------------- */
  // <ol data-scroll-end> starts scrolled to its end: the newest message, as in a messenger.

  function scrollToEnd(element) {
    element.scrollTop = element.scrollHeight;
  }

  /* ---- Crew and customer with one click (EML-043) ------------------------------ */
  // <div data-quick-recipients="id_to"> holds buttons <button data-add-recipients='["Anna <a@x.example>"]'>.
  // A click adds those addresses to the field that are not in it yet, and says in the
  // status line [data-recipients-status] what was added.

  function addressEntries(value) {
    var entries = [];
    var current = "";
    var quoted = false;
    for (var index = 0; index < value.length; index++) {
      var character = value.charAt(index);
      if (character === "\"") { quoted = !quoted; }
      if (!quoted && (character === "," || character === ";")) {
        entries.push(current);
        current = "";
      } else {
        current += character;
      }
    }
    entries.push(current);
    return entries.map(function (entry) { return entry.trim(); }).filter(Boolean);
  }

  function addressKey(entry) {
    var inBrackets = /<([^>]+)>/.exec(entry);
    return (inBrackets ? inBrackets[1] : entry).trim().toLowerCase();
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-add-recipients]");
    var box = button && button.closest("[data-quick-recipients]");
    var field = box && document.getElementById(box.dataset.quickRecipients);
    if (!field) { return; }
    var known = {};
    addressEntries(field.value).forEach(function (entry) { known[addressKey(entry)] = true; });
    var added = [];
    JSON.parse(button.dataset.addRecipients || "[]").forEach(function (entry) {
      var key = addressKey(entry);
      if (!known[key]) { known[key] = true; added.push(entry); }
    });
    if (added.length) {
      var before = field.value.replace(/[\s,;]+$/, "");
      field.value = (before ? before + ", " : "") + added.join(", ");
    }
    var status = box.querySelector("[data-recipients-status]");
    if (status) {
      status.textContent = added.length ? box.dataset.textAdded + " " + added.join(", ") : box.dataset.textNone;
    }
  });

  /* ---- Start-up -------------------------------------------------------------- */

  function initialise(root) {
    root.querySelectorAll("input[data-address-suggest]").forEach(function (input) {
      if (!input.dataset.ready) { input.dataset.ready = "1"; setUpAddressField(input); }
    });
    root.querySelectorAll("form[data-signature-form]").forEach(function (form) {
      if (!form.dataset.ready) { form.dataset.ready = "1"; setUpSignatureForm(form); }
    });
    root.querySelectorAll("[data-scroll-end]").forEach(function (element) {
      if (!element.dataset.ready) { element.dataset.ready = "1"; scrollToEnd(element); }
    });
  }

  document.body.addEventListener("htmx:afterSettle", function () { initialise(document); });
  initialise(document);
})();

/*
 * Planning overviews (VFG-021, VFG-022).
 *
 * Week grid: opens scrolled to the working hours (06:00, or earlier when
 * something starts earlier) and, where the days do not all fit, to today;
 * the line of the current time moves on every minute; "+n" opens the
 * all-day strip in full.
 *
 * Timelines in hour columns: the page holds the chosen span with one span
 * before and one after it. It opens scrolled to the chosen span; scrolled to
 * either end it loads the neighbouring span in the background and exchanges
 * the timeline so that the view stays where it is – the range moves on
 * while scrolling. Without this script the "earlier" and "later" buttons do
 * the same with a page load.
 *
 * Everything is wired through data- attributes; the content security policy
 * forbids inline scripts.
 */
(function () {
  "use strict";

  /* ---- Week grid (VFG-021) ------------------------------------------------ */

  var loadedAt = Date.now();

  function initWeek(grid) {
    var scroller = grid.querySelector(".wk-scroll");
    var firstHour = grid.querySelector(".wk-hour");
    if (!scroller || !firstHour) { return; }
    var hourHeight = firstHour.getBoundingClientRect().height;
    var startHour = parseInt(grid.dataset.scrollHour || "6", 10);
    scroller.scrollTop = Math.max(0, startHour * hourHeight);
    // Where the days do not all fit, bring today into view, right of the hours.
    var today = grid.querySelector(".wk-col.today");
    var corner = grid.querySelector(".wk-corner");
    if (today && corner) {
      var box = scroller.getBoundingClientRect();
      var day = today.getBoundingClientRect();
      var gutter = corner.getBoundingClientRect().width;
      if (day.right > box.right || day.left < box.left + gutter) {
        scroller.scrollLeft += day.left - box.left - gutter;
      }
    }
    grid.querySelectorAll("[data-now]").forEach(function (line) {
      line.dataset.startAt = line.style.getPropertyValue("--at") || "0";
    });
  }

  // The server placed the line when the page was made, in its own time zone; move it by the time passed since.
  function moveNow() {
    var passed = (Date.now() - loadedAt) / 3600000;
    document.querySelectorAll("[data-now]").forEach(function (line) {
      var at = parseFloat(line.dataset.startAt || "0") + passed;
      if (at >= 24) { line.hidden = true; return; }
      line.style.setProperty("--at", at.toFixed(3));
    });
  }

  document.addEventListener("click", function (event) {
    var toggle = event.target.closest("[data-all-day-toggle]");
    if (!toggle) { return; }
    var grid = toggle.closest("[data-week-grid]");
    if (!grid) { return; }
    var open = !grid.classList.contains("is-expanded");
    grid.classList.toggle("is-expanded", open);
    grid.querySelectorAll(".wk-more").forEach(function (button) {
      button.setAttribute("aria-expanded", open ? "true" : "false");
    });
    // The button pressed disappears; the focus goes to the one that takes its place.
    var next = grid.querySelector(open ? ".wk-less" : ".wk-more");
    if (next) { next.focus(); }
  });

  /* ---- Timelines in hour columns (VFG-022) ----------------------------- */

  var loading = false;

  function columnWidth(panel) {
    var grid = panel.querySelector(".tl-grid");
    var label = grid ? grid.querySelector(".tl-label") : null;
    var columns = parseInt(panel.dataset.columns || "0", 10);
    if (!grid || !label || !columns) { return 0; }
    return (grid.scrollWidth - label.offsetWidth) / columns;
  }

  function watch(panel) {
    panel.addEventListener("scroll", function () {
      if (loading) { return; }
      if (panel.scrollWidth <= panel.clientWidth + 2) { return; }
      if (panel.scrollLeft <= 1) {
        shift(panel, "earlier");
      } else if (panel.scrollLeft + panel.clientWidth >= panel.scrollWidth - 1) {
        shift(panel, "later");
      }
    }, { passive: true });
  }

  function initZoom(panel) {
    panel.scrollLeft = parseInt(panel.dataset.focus || "0", 10) * columnWidth(panel);
    watch(panel);
  }

  function shift(panel, direction) {
    var url = direction === "later" ? panel.dataset.laterUrl : panel.dataset.earlierUrl;
    var region = panel.closest("[data-tl-swap]");
    if (!url || !region) { return; }
    loading = true;
    panel.setAttribute("aria-busy", "true");
    var span = columnWidth(panel) * parseInt(panel.dataset.shift || "0", 10);
    var hadFocus = panel.contains(document.activeElement);
    window.fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "fetch" } })
      .then(function (response) {
        if (!response.ok) { throw new Error(String(response.status)); }
        return response.text();
      })
      .then(function (html) {
        var page = new DOMParser().parseFromString(html, "text/html");
        var fresh = page.querySelector("[data-tl-swap]");
        var freshPanel = fresh ? fresh.querySelector("[data-tl-zoom]") : null;
        if (!freshPanel) { throw new Error("no timeline in the answer"); }
        var before = panel.scrollLeft;
        // VFG-037 (kits in the utilization): a kit unfolded stays unfolded in the moved range.
        region.querySelectorAll("input[data-keep-state]").forEach(function (box) {
          var twin = fresh.querySelector('input[data-keep-state="' + box.dataset.keepState + '"]');
          if (twin) { twin.checked = box.checked; }
        });
        region.replaceWith(fresh);
        // The new range is the old one moved by one span: keep in view what was in view.
        freshPanel.scrollLeft = before + (direction === "later" ? -span : span);
        watch(freshPanel);
        window.history.replaceState(null, "", url);
        var range = fresh.querySelector("[data-tl-range]");
        var announce = document.querySelector("[data-tl-announce]");
        if (range && announce) { announce.textContent = range.textContent; }
        if (hadFocus) { freshPanel.focus({ preventScroll: true }); }
      })
      .catch(function () {
        window.location.assign(url);
      })
      .finally(function () {
        loading = false;
      });
  }

  /* ---- Start ------------------------------------------------------------ */

  document.querySelectorAll("[data-week-grid]").forEach(initWeek);
  document.querySelectorAll("[data-tl-zoom]").forEach(initZoom);
  if (document.querySelector("[data-now]")) {
    window.setInterval(moveNow, 60000);
  }
})();

/*
 * Personnel: the availability calendar (PER-021) and the calendar links (PER-023).
 *
 * Choosing days: the first tap on a day of [data-avail-calendar] sets the
 * first and the last day of the form [data-avail-form] next to it, the
 * second tap the other end (Shift extends from the first day). The chosen
 * days are framed. The form works without this as well: the two date fields
 * can be typed in.
 */
(function () {
  "use strict";

  function setUp(calendar) {
    var container = calendar.closest(".panel-body") || calendar.parentElement;
    var form = container ? container.querySelector("[data-avail-form]") : null;
    if (!form) { return; }
    var first = form.querySelector('input[name="start_day"]');
    var last = form.querySelector('input[name="end_day"]');
    var days = Array.prototype.slice.call(calendar.querySelectorAll("[data-avail-day]"));
    var picking = false;

    function show() {
      var from = first.value;
      var until = last.value || from;
      days.forEach(function (button) {
        var day = button.dataset.availDay;
        var chosen = Boolean(from) && day >= from && day <= until;
        button.classList.toggle("in-range", chosen);
        button.setAttribute("aria-pressed", chosen ? "true" : "false");
      });
    }

    calendar.addEventListener("click", function (event) {
      var button = event.target.closest("[data-avail-day]");
      if (!button) { return; }
      var day = button.dataset.availDay;
      if ((picking || event.shiftKey) && first.value) {
        // ISO dates compare as text.
        if (day < first.value) {
          last.value = last.value && last.value > first.value ? last.value : first.value;
          first.value = day;
        } else {
          last.value = day;
        }
        picking = false;
      } else {
        first.value = day;
        last.value = day;
        picking = true;
      }
      show();
    });

    first.addEventListener("change", function () {
      if (last.value && last.value < first.value) { last.value = first.value; }
      show();
    });
    last.addEventListener("change", show);
    show();
  }

  document.querySelectorAll("[data-avail-calendar]").forEach(setUp);

  /* A read-only field with a link: one tap selects all of it for copying (PER-023). */
  document.addEventListener("focusin", function (event) {
    if (event.target.matches && event.target.matches("[data-select-on-focus]")) {
      event.target.select();
    }
  });
})();

(function () {
  "use strict";

  /* ---- MVR plot: choosing another product (PRJ-077) ---------------------- */
  //
  // Each fixture type offers its suggestions as radio buttons, then "another
  // product" with a search field. Typing into the search field, or picking a
  // product from it, chooses "another product" in the same row.

  function chooseOther(event) {
    var target = event.target;
    if (!target || !target.closest) { return; }
    if (!target.matches("[data-typeahead-input], [data-typeahead-value]")) { return; }
    var row = target.closest("[data-mvr-row]");
    var other = row && row.querySelector("[data-mvr-other]");
    if (other && !other.checked) { other.checked = true; }
  }

  document.addEventListener("input", chooseOther);
  document.addEventListener("change", chooseOther);
})();

/*
 * Nested groups on the planning page (PRJ-037).
 *
 *  - The subgroups of a group can be folded away; the page remembers which
 *    ones for the browser tab, also across the refreshes of the planning.
 *  - A group is moved by dragging its handle: before or after another group,
 *    into another group, or out to the top level. Each list of groups
 *    (<div data-group-tree data-parent="…">) is a SortableJS list; together
 *    they form a nested list.
 *  - NFA-025: the handle is a button; the arrow keys up and down move the
 *    group among its siblings, right puts it into the group above it, left
 *    takes it out of its parent group.
 *
 * Every move is sent to the server (data-move-url of the handle: parent and
 * position), which checks the rules – not inside itself, at most three
 * levels – and answers with the refreshed planning. Wired through data-
 * attributes; no inline scripts (the content security policy forbids them).
 */
(function () {
  "use strict";

  var STORAGE_KEY = "rentalars.foldedGroups";
  var MAX_DEPTH = 3;
  var csrfToken = document.body.dataset.csrf || "";

  /* ---- Folding the subgroups ------------------------------------------ */

  function folded() {
    try {
      var list = JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) || "[]");
      return Array.isArray(list) ? list : [];
    } catch (error) { return []; }
  }

  function remember(list) {
    try { window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(list)); } catch (error) { /* no storage */ }
  }

  // The toggles stand in the group sections, which a patch replaces; the
  // lists of subgroups stay. So the state is put on both again after every swap.
  function applyFolding() {
    var list = folded();
    document.querySelectorAll("[data-group-toggle]").forEach(function (toggle) {
      var open = list.indexOf(toggle.dataset.groupToggle) < 0;
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      var box = document.getElementById(toggle.getAttribute("aria-controls"));
      if (box) { box.hidden = !open; }
    });
  }

  document.addEventListener("click", function (event) {
    var toggle = event.target.closest("[data-group-toggle]");
    if (!toggle) { return; }
    var id = toggle.dataset.groupToggle;
    var list = folded();
    var index = list.indexOf(id);
    if (toggle.getAttribute("aria-expanded") === "true") {
      if (index < 0) { list.push(id); }
    } else if (index >= 0) {
      list.splice(index, 1);
    }
    remember(list);
    applyFolding();
  });

  /* ---- Moving a group ------------------------------------------------- */

  function nodesIn(container) {
    return Array.prototype.filter.call(container.children, function (child) {
      return child.matches("[data-group-node]");
    });
  }

  function depthOf(container) {
    var owner = container.closest("[data-group-node]");
    return owner ? Number(owner.dataset.depth) + 1 : 0;
  }

  // How many levels a group takes with its subgroups: 1 without any.
  function heightOf(node) {
    var deepest = Number(node.dataset.depth);
    node.querySelectorAll("[data-group-node]").forEach(function (inner) {
      deepest = Math.max(deepest, Number(inner.dataset.depth));
    });
    return deepest - Number(node.dataset.depth) + 1;
  }

  function handleOf(node) {
    return node.querySelector(":scope > section [data-group-handle]");
  }

  // byKeyboard: the focus goes back to the handle and the page follows it; after a drag it stays put.
  function send(node, parent, position, byKeyboard) {
    var handle = handleOf(node);
    if (!handle || typeof htmx === "undefined") { return; }
    var groupId = node.dataset.groupNode;
    htmx.ajax("POST", handle.dataset.moveUrl, {
      source: handle,
      target: "#planning",
      swap: "outerHTML",
      headers: { "X-CSRFToken": csrfToken },
      values: { parent: parent || "", position: position ? String(position) : "" }
    }).then(function () {
      var moved = document.querySelector('[data-group-node="' + groupId + '"]');
      var again = moved ? handleOf(moved) : null;
      if (again) { again.focus({ preventScroll: !byKeyboard }); }
    });
  }

  // NFA-025: the arrow keys on the handle.
  document.addEventListener("keydown", function (event) {
    var handle = event.target.closest ? event.target.closest("[data-group-handle]") : null;
    if (!handle || ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].indexOf(event.key) < 0) { return; }
    if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) { return; }
    event.preventDefault();
    var node = handle.closest("[data-group-node]");
    var container = node.parentElement;
    var siblings = nodesIn(container);
    var index = siblings.indexOf(node);
    var parent = container.dataset.parent || "";
    if (event.key === "ArrowUp" && index > 0) {
      send(node, parent, index, true);
    } else if (event.key === "ArrowDown" && index < siblings.length - 1) {
      send(node, parent, index + 2, true);
    } else if (event.key === "ArrowRight" && index > 0) {
      // Into the group above, as its last subgroup; the server says so if that is too deep.
      send(node, siblings[index - 1].dataset.groupNode, null, true);
    } else if (event.key === "ArrowLeft" && parent) {
      // Out of the parent group, right behind it.
      var owner = container.closest("[data-group-node]");
      var outer = owner.parentElement;
      send(node, outer.dataset.parent || "", nodesIn(outer).indexOf(owner) + 2, true);
    }
  });

  function setUpTree(container) {
    var planning = container.closest("#planning");
    if (!planning || typeof Sortable === "undefined" || !planning.querySelector("[data-group-handle]")) { return; }
    Sortable.create(container, {
      group: "groups",
      handle: ".group-drag",
      draggable: "[data-group-node]",
      animation: 120,
      fallbackOnBody: true,
      swapThreshold: 0.65,
      emptyInsertThreshold: 12,
      onStart: function () { planning.classList.add("is-moving-group"); },
      // PRJ-037: never deeper than three levels – the drop is not offered there at all.
      onMove: function (event) {
        return depthOf(event.to) + heightOf(event.dragged) <= MAX_DEPTH;
      },
      onEnd: function (event) {
        planning.classList.remove("is-moving-group");
        if (event.from === event.to && event.oldIndex === event.newIndex) { return; }
        send(event.item, event.to.dataset.parent || "", nodesIn(event.to).indexOf(event.item) + 1, false);
      }
    });
  }

  function initialise() {
    document.querySelectorAll("[data-group-tree]").forEach(function (container) {
      if (!container.dataset.groupReady) { container.dataset.groupReady = "1"; setUpTree(container); }
    });
    applyFolding();
  }

  document.body.addEventListener("htmx:afterSettle", initialise);
  initialise();
})();

(function () {
  "use strict";

  /* ---- Validity of an offer: a date and a number of days (DOK-013) -------- */
  //
  // <div data-validity data-validity-from="2027-03-01"> holds a date field
  // (data-validity-date) and a number field (data-validity-days). Changing
  // one sets the other at once, counted from data-validity-from – the date
  // the offer gets. The server accepts either and checks that both agree.

  var DAY = 86400000;

  function parseDay(text) {
    var parts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text || "");
    return parts ? Date.UTC(+parts[1], +parts[2] - 1, +parts[3]) : null;
  }

  function follow(event) {
    var field = event.target;
    var box = field && field.closest ? field.closest("[data-validity]") : null;
    if (!box) { return; }
    var from = parseDay(box.dataset.validityFrom);
    var date = box.querySelector("[data-validity-date]");
    var days = box.querySelector("[data-validity-days]");
    if (from === null || !date || !days) { return; }
    if (field === days) {
      var text = days.value.trim();
      if (/^\d+$/.test(text)) { date.value = new Date(from + parseInt(text, 10) * DAY).toISOString().slice(0, 10); }
    } else if (field === date) {
      var until = parseDay(date.value);
      if (until !== null) { days.value = String(Math.round((until - from) / DAY)); }
    }
  }

  document.addEventListener("input", follow);
  document.addEventListener("change", follow);
})();

/*
 * Choosing several lines of the planning (PRJ-082).
 *
 * Every line has a box (data-select-line) that belongs to the form of the bar
 * "chosen lines" (#line-selection, data-selection-bar); the head of each
 * section has a box for all its lines (data-select-all). The bar shows while
 * a line is chosen and says how many. After the planning, or a part of it, was
 * swapped in, the count is taken again: the boxes of new parts are empty.
 * Everything is a plain checkbox or button, so it works with the keyboard.
 */
(function () {
  "use strict";

  function update() {
    // The boxes "all" are kept in step on every page that has them, also where there is no bar (the approval of times).
    document.querySelectorAll("[data-select-all]").forEach(function (all) {
      var boxes = all.closest("table").querySelectorAll("[data-select-line]");
      var ticked = Array.prototype.filter.call(boxes, function (box) { return box.checked; }).length;
      all.checked = boxes.length > 0 && ticked === boxes.length;
      all.indeterminate = ticked > 0 && ticked < boxes.length;
    });
    var bar = document.querySelector("[data-selection-bar]");
    if (!bar) { return; }
    var chosen = document.querySelectorAll("[data-select-line]:checked").length;
    bar.hidden = chosen === 0;
    var count = bar.querySelector("[data-selection-count]");
    if (count) { count.textContent = String(chosen); }
    var one = bar.querySelector("[data-selection-one]");
    var many = bar.querySelector("[data-selection-many]");
    if (one && many) { one.hidden = chosen !== 1; many.hidden = chosen === 1; }
  }

  document.addEventListener("change", function (event) {
    var all = event.target.closest ? event.target.closest("[data-select-all]") : null;
    if (all) {
      all.closest("table").querySelectorAll("[data-select-line]").forEach(function (box) { box.checked = all.checked; });
      update();
    } else if (event.target.matches && event.target.matches("[data-select-line]")) {
      update();
    }
  });

  document.addEventListener("click", function (event) {
    if (!event.target.closest || !event.target.closest("[data-selection-clear]")) { return; }
    document.querySelectorAll("[data-select-line]:checked").forEach(function (box) { box.checked = false; });
    update();
  });

  document.body.addEventListener("htmx:afterSettle", update);
  update();
})();

/*
 * PRJ-094: a new phase from the crew planning.
 *
 * <select data-new-phase-url="/projects/…/phases/new/dialog/" data-new-phase-label="Neue Phase …"> is the list
 * of phases of a crew form, for whoever may edit the project. This script adds the entry "Neue Phase …" at its
 * end. Choosing it opens the form for a new phase in a dialog of its own – it may stand over the dialog of a
 * crew line –, and the crew form keeps what was typed. The answer "phaseCreated" names the saved phase: it goes
 * into every such list of the page and is chosen in the one the dialog came from, which then takes over its
 * period as with any phase. Escape or "Abbrechen" close the dialog; the focus goes back to the list.
 *
 * Keyboard: some browsers change the value of a closed list with every arrow key. Reaching the entry that way
 * only selects it; Enter or Space opens the dialog, and leaving the list puts the former phase back.
 * Without this script there is no such entry; the list of a project without phases then stays hidden.
 */
(function () {
  "use strict";

  var NEW = "new";
  var NAVIGATION_KEYS = ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End", "PageUp", "PageDown"];
  var opener = null;

  function isPhaseList(element) {
    return Boolean(element && element.matches && element.matches("select[data-new-phase-url]"));
  }

  function newChosen(select) {
    var option = select.options[select.selectedIndex];
    return Boolean(option && option.hasAttribute("data-new-phase"));
  }

  function showField(select) {
    var holder = select.closest("[data-new-phase-field]");
    if (holder) { holder.hidden = false; }
  }

  function prepare(select) {
    if (select.dataset.newPhaseReady || !window.htmx) { return; }
    select.dataset.newPhaseReady = "1";
    var entry = document.createElement("option");
    entry.value = NEW;
    entry.textContent = select.dataset.newPhaseLabel || "…";
    entry.setAttribute("data-new-phase", "");
    select.appendChild(entry);
    select.dataset.chosen = select.value;
    showField(select);
  }

  function prepareAll() {
    document.querySelectorAll("select[data-new-phase-url]").forEach(prepare);
  }

  // The list shows its former phase again (the entry is never sent).
  function restore(select) {
    if (newChosen(select)) { select.value = select.dataset.chosen || ""; }
    delete select.dataset.keyed;
  }

  function focusIn(box) {
    var target = box.querySelector(".has-error select, .has-error input, [autofocus]");
    if (target) { target.focus(); }
  }

  function dialogBox() {
    var box = document.getElementById("phase-dialog");
    if (box) { return box; }
    box = document.createElement("dialog");
    box.id = "phase-dialog";
    box.className = "dialog";
    box.setAttribute("aria-labelledby", "phase-dialog-title");
    document.body.appendChild(box);
    // Its buttons close this dialog only, not the dialog of a crew line underneath it.
    box.addEventListener("click", function (event) {
      if (event.target.closest("[data-close-dialog]")) {
        event.stopPropagation();
        box.close();
      }
    });
    box.addEventListener("htmx:afterSwap", function () {
      if (!box.firstElementChild) { return; }
      if (!box.open) { box.showModal(); }
      focusIn(box);
    });
    box.addEventListener("close", function () {
      box.innerHTML = "";
      if (opener && document.body.contains(opener)) { opener.focus(); }
      opener = null;
    });
    return box;
  }

  function open(select) {
    restore(select);
    opener = select;
    var form = select.closest("form");
    var url = select.dataset.newPhaseUrl;
    // The period typed in the crew form is the first guess for the phase.
    var query = ["start", "end"].map(function (name) {
      var field = form ? form.querySelector('[name="' + name + '"]') : null;
      return field && field.value ? name + "=" + encodeURIComponent(field.value) : "";
    }).filter(Boolean).join("&");
    if (query) { url += (url.indexOf("?") === -1 ? "?" : "&") + query; }
    window.htmx.ajax("GET", url, { target: dialogBox(), swap: "innerHTML" });
  }

  function addPhase(select, phase) {
    if (select.querySelector('option[value="' + phase.id + '"]')) { return; }
    var option = document.createElement("option");
    option.value = String(phase.id);
    option.textContent = phase.label;
    option.dataset.start = phase.start;
    option.dataset.end = phase.end;
    // In the order of time, as the server lists them; the entry "Neue Phase …" stays last.
    var before = Array.prototype.find.call(select.options, function (other) {
      return other.hasAttribute("data-new-phase") || (other.dataset.start && other.dataset.start > phase.start);
    });
    select.insertBefore(option, before || null);
    showField(select);
  }

  document.addEventListener("change", function (event) {
    var select = event.target;
    if (!isPhaseList(select)) { return; }
    if (!newChosen(select)) {
      select.dataset.chosen = select.value;
      return;
    }
    if (!select.dataset.keyed) { open(select); }
  });

  document.addEventListener("keydown", function (event) {
    var select = event.target;
    if (!isPhaseList(select)) { return; }
    if ((event.key === "Enter" || event.key === " ") && newChosen(select)) {
      event.preventDefault();
      open(select);
    } else if (event.key === "Enter" || event.key === " " || event.altKey || event.key === "F4") {
      delete select.dataset.keyed;  // the list opens: what is picked there counts as chosen
    } else if (NAVIGATION_KEYS.indexOf(event.key) !== -1 || (event.key.length === 1 && !event.ctrlKey && !event.metaKey)) {
      select.dataset.keyed = "1";
    }
  }, true);

  document.addEventListener("pointerdown", function (event) {
    if (isPhaseList(event.target)) { delete event.target.dataset.keyed; }
  }, true);

  document.addEventListener("focusout", function (event) {
    if (isPhaseList(event.target) && event.target !== opener) { restore(event.target); }
  });

  document.body.addEventListener("phaseCreated", function (event) {
    var phase = event.detail && event.detail.value ? event.detail.value : event.detail;
    if (!phase || !phase.id) { return; }
    var source = opener;
    var address = source ? source.dataset.newPhaseUrl : "";
    document.querySelectorAll("select[data-new-phase-url]").forEach(function (select) {
      if (!address || select.dataset.newPhaseUrl === address) { addPhase(select, phase); }
    });
    if (source && document.body.contains(source)) {
      source.value = String(phase.id);
      // As if chosen by hand: the crew form takes over the period of the phase.
      source.dispatchEvent(new Event("change", { bubbles: true }));
    }
    var box = document.getElementById("phase-dialog");
    // PRJ-100: a phase beyond the rental period keeps the dialog open for the question whether to extend it.
    if (box && box.open && !phase.keepDialog) { box.close(); }
  });

  document.body.addEventListener("htmx:afterSettle", prepareAll);
  prepareAll();
})();

/* ==== UIX-030: the filters above a list fold away ==========================
 * {% filterpanel %} (core/templatetags/rentalars.py) puts the filters of a
 * list behind a button. UIX-038: they start folded on every screen
 * width; a filter with an
 * error is never folded. UIX-038: folded on every page load – an open
 * state remembered earlier per list in this browser is no longer
 * restored, and its stored entries are removed. The
 * button counts the active filters ("Filter (2 aktiv)"), and while the panel is
 * folded a line beside it says which they are. app.css sets the first state
 * before this script runs, so nothing jumps; without scripts every field shows.
 */
(function () {
  "use strict";

  function labelOf(field) {
    var label = field.labels && field.labels.length ? field.labels[0].textContent : field.getAttribute("aria-label") || field.name;
    return label.replace(/\s+/g, " ").trim();
  }

  function dayText(value) {
    var parts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    // UIX-029: 16/10/2026 in English.
    var separator = /^en/i.test(document.documentElement.lang || "") ? "/" : ".";
    return parts ? parts[3] + separator + parts[2] + separator + parts[1] : value;
  }

  // The filters the page was loaded with count – the server filtered by them –, not what was typed since.
  // A field without filter shows its first option or nothing; data-filter-default names another value.
  function activeFilters(panel) {
    var found = [];
    panel.querySelectorAll("input, select").forEach(function (field) {
      if (field.disabled || !field.name || ["hidden", "submit", "button", "reset"].indexOf(field.type) >= 0) { return; }
      var fallback = field.dataset.filterDefault;
      if (field.tagName === "SELECT") {
        var chosen = Array.prototype.filter.call(field.options, function (option) { return option.defaultSelected; });
        if (!field.multiple) {
          var option = chosen[chosen.length - 1] || field.options[0];
          if (option && (fallback !== undefined ? option.value !== fallback : option.index > 0)) {
            found.push(labelOf(field) + ": " + option.text.trim());
          }
        } else {
          chosen = chosen.filter(function (each) { return each.value !== ""; });
          if (chosen.length) { found.push(labelOf(field) + ": " + chosen.map(function (each) { return each.text.trim(); }).join(", ")); }
        }
      } else if (field.type === "checkbox" || field.type === "radio") {
        if (field.defaultChecked && field.value !== (fallback || "")) { found.push(labelOf(field)); }
      } else if (field.defaultValue !== "" && field.defaultValue !== fallback) {
        found.push(labelOf(field) + ": " + (field.type === "date" ? dayText(field.defaultValue) : field.defaultValue));
      }
    });
    return found;
  }

  function describe(toggle, panel) {
    var found = activeFilters(panel);
    var count = toggle.querySelector("[data-filter-count]");
    if (count) {
      // UIX-038: "(2 aktiv)" – the text comes from the page, translated (data-filter-active).
      var active = (toggle.dataset.filterActive || "#").replace("#", String(found.length));
      count.textContent = found.length ? " (" + active + ")" : "";
    }
    toggle.classList.toggle("has-active", found.length > 0);
    var summary = document.getElementById(toggle.getAttribute("aria-describedby"));
    if (!summary) { return; }
    summary.textContent = "";
    found.forEach(function (text) {
      var chip = document.createElement("span");
      chip.className = "filter-chip";
      chip.textContent = text;
      summary.appendChild(chip);
    });
    summary.hidden = found.length === 0;
  }

  function setOpen(toggle, open) {
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function openAtFirst(toggle, panel) {
    if (panel.querySelector(".errorlist, .has-error")) { return true; }  // a mistake is never folded away
    return false;  // UIX-038: folded on every page load, at every width
  }

  function setUp(toggle) {
    var panel = document.getElementById(toggle.getAttribute("aria-controls"));
    if (!panel || toggle.dataset.filterReady) { return; }
    toggle.dataset.filterReady = "1";
    describe(toggle, panel);
    setOpen(toggle, openAtFirst(toggle, panel));
  }

  function setUpAll(root) {
    (root && root.querySelectorAll ? root : document).querySelectorAll("[data-filter-toggle]").forEach(setUp);
  }

  document.addEventListener("click", function (event) {
    var toggle = event.target.closest("[data-filter-toggle]");
    if (!toggle) { return; }
    setOpen(toggle, toggle.getAttribute("aria-expanded") !== "true");
  });


  document.body.addEventListener("htmx:afterSettle", function (event) { setUpAll(event.target); });
  setUpAll(document);
})();

/* ==== UIX-036: one picker for every date and time field; PRJ-099: periods hatched ====
 * Every <input type="date">, "datetime-local" and "time" gets a button at its right end, in the place of the
 * browser's own calendar symbol. It opens a dialog with the calendar of "Zeitraum im Kalender wählen" and, for
 * a time, a round clock face as in the Android app: first tap the hour – the outer ring holds 1 to 12, the
 * inner ring 13 to 23 and 00 –, then the minute: the face shows steps of five, dragging gives every minute,
 * and hour and minute can be typed. A date alone is taken with the tap on the day.
 * The field keeps its type and its value ("2027-03-10T08:00"), so typing into it, the server, the checks of
 * the forms and the API stay as they are. Only the browser's own picker is no longer offered: the button takes
 * the place of its symbol, Alt+↓ opens this dialog instead, and on a touch screen – where the browser would
 * show its picker over the page – a tap on the field does too.
 * Keyboard: in the calendar the arrows move by day and week, Page↑/↓ by month, Home/End to the start and end
 * of the week, Enter or Space pick the day. The clock face is a slider: the arrows change the hour or the
 * minute by one, Page↑/↓ by more, Enter goes on from the hour to the minute and then takes the time; digits go
 * into the fields of hour and minute. Escape closes the dialog; the focus returns to where it came from.
 * PRJ-099: an element [data-calendar-marks] around the fields lists periods to hatch in these calendars – the
 * rental period and the event period (projects/templatetags/period_marks.py) – with a small legend; a period
 * named by the fields being chosen is left out. "Zeitraum im Kalender wählen" (UIX-025, above) uses the same
 * marks and keys through window.Rentalars.calendar.
 * Without this script the fields are the browser's own, as before.
 */
(function () {
  "use strict";

  var texts = document.body.dataset;
  var TYPES = ["date", "datetime-local", "time"];
  var SVG = "http://www.w3.org/2000/svg";
  var locale = document.documentElement.lang || "de";
  var monthFormat = new Intl.DateTimeFormat(locale, { month: "long", year: "numeric" });
  var weekdayFormat = new Intl.DateTimeFormat(locale, { weekday: "short" });
  var dayFormat = new Intl.DateTimeFormat(locale, { weekday: "short", day: "numeric", month: "numeric", year: "numeric" });
  var markFormat = new Intl.DateTimeFormat(locale, { weekday: "short", day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit" });
  var TOUCH = window.matchMedia("(pointer: coarse)");
  var NARROW = window.matchMedia("(max-width: 639px)");
  var counter = 0;

  function pad(number) { return (number < 10 ? "0" : "") + number; }
  function isoDay(date) { return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate()); }
  function midnight(date) { return new Date(date.getFullYear(), date.getMonth(), date.getDate()); }

  // "2027-03-10", "2027-03-10T08:00" or "08:00" → its parts; null for anything else.
  function partsOf(value) {
    var match = /^(?:(\d{4})-(\d{2})-(\d{2}))?T?(?:(\d{2}):(\d{2}))?/.exec(value || "");
    if (!match || (!match[1] && !match[4])) { return null; }
    return {
      day: match[1] ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3])) : null,
      hour: match[4] ? Number(match[4]) : null,
      minute: match[5] ? Number(match[5]) : null
    };
  }
  function momentOf(value) {
    var parts = partsOf(value);
    if (!parts || !parts.day) { return null; }
    return new Date(parts.day.getFullYear(), parts.day.getMonth(), parts.day.getDate(), parts.hour || 0, parts.minute || 0);
  }

  // The label of a field as read out: without the asterisk of a required field or other hidden parts.
  function labelOf(input) {
    var text = input.getAttribute("aria-label") || "";
    if (!text && input.labels && input.labels.length) {
      var copy = input.labels[0].cloneNode(true);
      copy.querySelectorAll('[aria-hidden="true"], input, button, select, textarea').forEach(function (part) { part.remove(); });
      text = copy.textContent;
    }
    return text.replace(/\s+/g, " ").trim();
  }

  function spriteUrl() {
    var use = document.querySelector("svg.icon use");
    var href = use ? use.getAttribute("href") || use.getAttribute("xlink:href") || "" : "";
    return href ? href.split("#")[0] : "/static/img/icons.svg";
  }
  function icon(name) {
    var svg = document.createElementNS(SVG, "svg");
    svg.setAttribute("class", "icon");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    var use = document.createElementNS(SVG, "use");
    use.setAttribute("href", spriteUrl() + "#" + name);
    svg.appendChild(use);
    return svg;
  }
  function button(className, text) {
    var element = document.createElement("button");
    element.type = "button";
    element.className = className;
    if (text) { element.textContent = text; }
    return element;
  }

  /* ---- PRJ-099: periods hatched in the calendars ---- */

  // The periods to mark for a field: from [data-calendar-marks] around it, without the period it belongs to.
  function calendarMarks(input, ownNames) {
    var holder = input.closest("[data-calendar-marks]");
    if (!holder) { return []; }
    var list;
    try { list = JSON.parse(holder.dataset.calendarMarks); } catch (error) { return []; }
    var scope = input.form || holder;
    var marks = [];
    (Array.isArray(list) ? list : []).forEach(function (mark) {
      var start = mark.start, end = mark.end;
      if (Array.isArray(mark.fields)) {
        if (mark.fields.some(function (name) { return ownNames.indexOf(name) !== -1; })) { return; }
        var first = scope.querySelector('[name="' + mark.fields[0] + '"]');
        var second = scope.querySelector('[name="' + mark.fields[1] + '"]');
        start = first ? first.value : "";
        end = second ? second.value : "";
      }
      var from = momentOf(start), until = momentOf(end);
      if (!from || !until || until < from) { return; }
      var firstDay = midnight(from), lastDay = midnight(until);
      // A period until midnight ends with the day before.
      if (lastDay > firstDay && until.getHours() === 0 && until.getMinutes() === 0) { lastDay.setDate(lastDay.getDate() - 1); }
      marks.push({ kind: mark.kind === "event" ? "event" : "rental", label: String(mark.label || ""), from: from, until: until, first: firstDay, last: lastDay });
    });
    return marks;
  }

  function markDay(element, day, marks) {
    var names = [];
    marks.forEach(function (mark) {
      if (day >= mark.first && day <= mark.last) {
        element.classList.add("mark-" + mark.kind);
        names.push(mark.label);
      }
    });
    if (names.length) { element.setAttribute("aria-label", element.getAttribute("aria-label") + " – " + names.join(", ")); }
  }

  function markLegend(marks) {
    if (!marks.length) { return null; }
    var list = document.createElement("ul");
    list.className = "mark-legend";
    marks.forEach(function (mark) {
      var item = document.createElement("li");
      var swatch = document.createElement("span");
      swatch.className = "mark-swatch mark-" + mark.kind;
      swatch.setAttribute("aria-hidden", "true");
      item.appendChild(swatch);
      item.appendChild(document.createTextNode(mark.label + ": " + markFormat.format(mark.from) + " – " + markFormat.format(mark.until)));
      list.appendChild(item);
    });
    return list;
  }

  /* ---- Keys in every calendar of these dialogs ---- */

  function moveDay(from, key) {
    var parts = from.dataset.day.split("-");
    var day = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    var target = new Date(day);
    var steps = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
    if (steps[key]) {
      target.setDate(day.getDate() + steps[key]);
    } else if (key === "Home") {
      target.setDate(day.getDate() - (day.getDay() + 6) % 7);
    } else if (key === "End") {
      target.setDate(day.getDate() + 6 - (day.getDay() + 6) % 7);
    } else if (key === "PageUp" || key === "PageDown") {
      target = new Date(day.getFullYear(), day.getMonth() + (key === "PageUp" ? -1 : 1), 1);
      var length = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
      target.setDate(Math.min(day.getDate(), length));
    } else {
      return false;
    }
    var root = from.closest("dialog") || document;
    var iso = isoDay(target);
    // Another month: the dialog turns its page – once more for the second month of a two-month view.
    for (var tries = 0; tries < 3; tries++) {
      var found = root.querySelector('table.range-month button[data-day="' + iso + '"]');
      if (found) {
        var calendar = found.closest(".dt-calendar");
        if (calendar) {
          calendar.querySelectorAll("button[data-day]").forEach(function (each) { each.tabIndex = each === found ? 0 : -1; });
        }
        found.focus();
        return true;
      }
      var turns = root.querySelectorAll(".range-nav > button");
      if (turns.length < 2) { return true; }
      turns[target < day ? 0 : turns.length - 1].click();
    }
    return true;
  }

  document.addEventListener("keydown", function (event) {
    if (event.altKey || event.ctrlKey || event.metaKey || !event.target.closest) { return; }
    var day = event.target.closest("table.range-month button[data-day]");
    if (day && moveDay(day, event.key)) { event.preventDefault(); }
  });

  /* ---- The fields ---- */

  function partnerOf(input) {
    var form = input.form;
    if (!form || !input.name) { return null; }
    var name = /start$/.test(input.name) ? input.name.replace(/start$/, "end") : /end$/.test(input.name) ? input.name.replace(/end$/, "start") : "";
    var other = name ? form.querySelector('input[name="' + name + '"]') : null;
    return other && other.type === input.type ? other : null;
  }

  function enhance(input) {
    if (input.dataset.pickerReady || TYPES.indexOf(input.type) === -1 || !input.parentNode) { return; }
    input.dataset.pickerReady = "1";
    var wrap = document.createElement("span");
    wrap.className = "dt-wrap";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);
    input.classList.add("dt-input");
    var opener = button("dt-btn");
    var what = input.type === "time" ? texts.textPickTime || "Choose the time"
      : input.type === "date" ? texts.textPickDate || "Choose the date" : texts.textPickDateTime || "Choose date and time";
    var label = labelOf(input);
    opener.setAttribute("aria-label", label ? what + ": " + label : what);
    opener.setAttribute("aria-haspopup", "dialog");
    opener.appendChild(icon(input.type === "time" ? "clock" : "calendar"));
    wrap.appendChild(opener);
    opener.addEventListener("click", function () { openPicker(input, opener); });
    input.addEventListener("keydown", function (event) {
      if ((event.altKey && event.key === "ArrowDown") || event.key === "F4") {
        event.preventDefault();
        openPicker(input, input);
      }
    });
    // Browsers that show their own picker on a click or tap do not get to; on a touch screen this one opens.
    input.addEventListener("click", function (event) {
      event.preventDefault();
      if (TOUCH.matches) { openPicker(input, input); }
    });
  }

  function enhanceAll(root) {
    (root && root.querySelectorAll ? root : document).querySelectorAll('input[type="date"], input[type="datetime-local"], input[type="time"]').forEach(enhance);
  }

  /* ---- The dialog ---- */

  function openPicker(input, opener) {
    if (input.disabled || input.readOnly || document.querySelector("dialog.dt-picker[open]")) { return; }
    var kind = input.type;
    var withDate = kind !== "time", withTime = kind !== "date";
    var now = new Date();
    var value = partsOf(input.value);
    var partner = partnerOf(input);
    var partnerParts = partner ? partsOf(partner.value) : null;
    var marks = withDate ? calendarMarks(input, [input.name, partner ? partner.name : ""]) : [];
    var minimum = input.min || "", maximum = input.max || "";

    var chosen = value && value.day ? value.day : null;
    var fallbackDay = partnerParts && partnerParts.day ? partnerParts.day : marks.length ? marks[0].first : midnight(now);
    var shown = new Date((chosen || fallbackDay).getFullYear(), (chosen || fallbackDay).getMonth(), 1);
    var hour, minute;
    if (value && value.hour !== null) {
      hour = value.hour; minute = value.minute;
    } else if (partnerParts && partnerParts.hour !== null) {
      hour = partnerParts.hour; minute = partnerParts.minute;
    } else if (kind === "time") {
      hour = now.getHours(); minute = Math.floor(now.getMinutes() / 5) * 5;
    } else {
      hour = 12; minute = 0;
    }
    var mode = "hour";

    var box = document.createElement("dialog");
    box.className = "dialog dt-picker dt-" + kind;
    var titleId = "dt-picker-title-" + (++counter);
    box.setAttribute("aria-labelledby", titleId);
    var head = document.createElement("div");
    head.className = "dialog-head";
    var title = document.createElement("h2");
    title.id = titleId;
    title.textContent = labelOf(input) || (withDate ? texts.textDate || "Date" : texts.textTime || "Time");
    head.appendChild(title);
    var body = document.createElement("div");
    body.className = "dialog-body";

    // On a phone date and time take turns; these two buttons switch and show what is chosen.
    var showDate = null, showTime = null;
    if (withDate && withTime) {
      var switcher = document.createElement("div");
      switcher.className = "dt-switch";
      showDate = button("dt-show-date");
      showTime = button("dt-show-time");
      switcher.appendChild(showDate);
      switcher.appendChild(showTime);
      body.appendChild(switcher);
    }
    var panes = document.createElement("div");
    panes.className = "dt-panes";
    body.appendChild(panes);

    // The calendar.
    var calendar = null, monthLabel = null, previous = null, next = null;
    if (withDate) {
      var datePane = document.createElement("section");
      datePane.className = "dt-pane dt-date-pane";
      datePane.setAttribute("aria-label", texts.textDate || "Date");
      var nav = document.createElement("div");
      nav.className = "range-nav";
      previous = button("icon-btn", "‹");
      previous.setAttribute("aria-label", texts.textEarlier || "Earlier");
      next = button("icon-btn", "›");
      next.setAttribute("aria-label", texts.textLater || "Later");
      monthLabel = document.createElement("span");
      monthLabel.className = "dt-month";
      monthLabel.setAttribute("aria-live", "polite");
      nav.appendChild(previous); nav.appendChild(monthLabel); nav.appendChild(next);
      calendar = document.createElement("div");
      calendar.className = "dt-calendar";
      datePane.appendChild(nav);
      datePane.appendChild(calendar);
      var legend = markLegend(marks);
      if (legend) { datePane.appendChild(legend); }
      panes.appendChild(datePane);
    }

    // The clock face.
    var clock = null, hourField = null, minuteField = null, face = null, numbers = null, hand = null, knob = null, dot = null, hint = null;
    if (withTime) {
      var timePane = document.createElement("section");
      timePane.className = "dt-pane dt-time-pane";
      timePane.setAttribute("aria-label", texts.textTime || "Time");
      var entry = document.createElement("div");
      entry.className = "dt-entry";
      hourField = document.createElement("input");
      minuteField = document.createElement("input");
      [[hourField, texts.textHour || "Hour"], [minuteField, texts.textMinute || "Minute"]].forEach(function (pair) {
        pair[0].type = "text";
        pair[0].inputMode = "numeric";
        pair[0].maxLength = 2;
        pair[0].autocomplete = "off";
        pair[0].setAttribute("aria-label", pair[1]);
      });
      var colon = document.createElement("span");
      colon.textContent = ":";
      colon.setAttribute("aria-hidden", "true");
      entry.appendChild(hourField); entry.appendChild(colon); entry.appendChild(minuteField);
      clock = document.createElement("div");
      clock.className = "dt-clock";
      clock.tabIndex = 0;
      clock.setAttribute("role", "slider");
      face = document.createElementNS(SVG, "svg");
      face.setAttribute("viewBox", "0 0 200 200");
      face.setAttribute("aria-hidden", "true");
      face.setAttribute("focusable", "false");
      var dial = document.createElementNS(SVG, "circle");
      dial.setAttribute("class", "dial");
      dial.setAttribute("cx", "100"); dial.setAttribute("cy", "100"); dial.setAttribute("r", "99");
      hand = document.createElementNS(SVG, "line");
      hand.setAttribute("class", "hand");
      hand.setAttribute("x1", "100"); hand.setAttribute("y1", "100");
      knob = document.createElementNS(SVG, "circle");
      knob.setAttribute("class", "knob");
      var centre = document.createElementNS(SVG, "circle");
      centre.setAttribute("class", "centre");
      centre.setAttribute("cx", "100"); centre.setAttribute("cy", "100"); centre.setAttribute("r", "3");
      numbers = document.createElementNS(SVG, "g");
      dot = document.createElementNS(SVG, "circle");
      dot.setAttribute("class", "dot");
      dot.setAttribute("r", "2.5");
      [dial, hand, knob, centre, numbers, dot].forEach(function (part) { face.appendChild(part); });
      clock.appendChild(face);
      hint = document.createElement("p");
      hint.className = "dt-hint muted small";
      hint.textContent = texts.textClockHint || "Tap the hour first, then the minute.";
      timePane.appendChild(entry);
      timePane.appendChild(clock);
      timePane.appendChild(hint);
      panes.appendChild(timePane);
    }

    // The buttons below.
    var foot = document.createElement("div");
    foot.className = "dialog-foot";
    var today = button("btn secondary", kind === "time" ? texts.textNow || "Now" : texts.textToday || "Today");
    foot.appendChild(today);
    var clear = null;
    if (!input.required) {
      clear = button("btn secondary", texts.textClear || "Clear");
      foot.appendChild(clear);
    }
    var spacer = document.createElement("span");
    spacer.className = "spacer";
    foot.appendChild(spacer);
    var cancel = button("btn secondary", texts.textCancel || "Cancel");
    foot.appendChild(cancel);
    var apply = null;
    if (withTime) {
      apply = button("btn", texts.textApply || "Apply");
      foot.appendChild(apply);
    }
    box.appendChild(head); box.appendChild(body); box.appendChild(foot);
    document.body.appendChild(box);

    /* -- the calendar -- */

    function dayOff(day) {
      var iso = isoDay(day);
      return (minimum && iso < minimum.slice(0, 10)) || (maximum && iso > maximum.slice(0, 10));
    }

    function renderCalendar(focusIso) {
      if (!calendar) { return; }
      calendar.textContent = "";
      monthLabel.textContent = monthFormat.format(shown);
      var table = document.createElement("table");
      table.className = "range-month";
      var caption = document.createElement("caption");
      caption.className = "visually-hidden";
      caption.textContent = monthFormat.format(shown);
      table.appendChild(caption);
      var headRow = document.createElement("tr");
      for (var weekday = 0; weekday < 7; weekday++) {
        var th = document.createElement("th");
        th.scope = "col";
        th.textContent = weekdayFormat.format(new Date(2024, 0, 1 + weekday));  // 1 Jan 2024 was a Monday
        headRow.appendChild(th);
      }
      var thead = document.createElement("thead");
      thead.appendChild(headRow);
      table.appendChild(thead);
      var tbody = document.createElement("tbody");
      var day = new Date(shown);
      day.setDate(1 - ((shown.getDay() + 6) % 7));
      var todayIso = isoDay(new Date());
      var chosenIso = chosen ? isoDay(chosen) : "";
      var otherDay = partnerParts && partnerParts.day ? partnerParts.day : null;
      var low = otherDay && chosen ? (otherDay < chosen ? otherDay : chosen) : null;
      var high = otherDay && chosen ? (otherDay < chosen ? chosen : otherDay) : null;
      var target = null;
      for (var week = 0; week < 6; week++) {
        var row = document.createElement("tr");
        for (var column = 0; column < 7; column++) {
          var cell = document.createElement("td");
          if (day.getMonth() === shown.getMonth()) {
            var pick = button("");
            var iso = isoDay(day);
            pick.textContent = day.getDate();
            pick.dataset.day = iso;
            pick.tabIndex = -1;
            pick.setAttribute("aria-label", dayFormat.format(day));
            if (iso === chosenIso) { pick.classList.add("edge"); pick.setAttribute("aria-pressed", "true"); }
            if (otherDay && iso === isoDay(otherDay) && iso !== chosenIso) { pick.classList.add("partner"); }
            if (low && day > low && day < high) { pick.classList.add("in-range"); }
            if (iso === todayIso) { pick.classList.add("today"); }
            if (dayOff(day)) { pick.setAttribute("aria-disabled", "true"); }
            markDay(pick, day, marks);
            cell.appendChild(pick);
            if (iso === focusIso || (!target && iso === chosenIso)) { target = pick; }
          }
          row.appendChild(cell);
          day.setDate(day.getDate() + 1);
        }
        tbody.appendChild(row);
      }
      table.appendChild(tbody);
      calendar.appendChild(table);
      target = target || calendar.querySelector("button.today") || calendar.querySelector("button[data-day]");
      target.tabIndex = 0;
      return target;
    }

    function turn(months) {
      shown = new Date(shown.getFullYear(), shown.getMonth() + months, 1);
      renderCalendar();
    }

    /* -- the clock -- */

    function point(radius, degrees) {
      var angle = degrees * Math.PI / 180;
      return [100 + radius * Math.sin(angle), 100 - radius * Math.cos(angle)];
    }

    function renderClock() {
      if (!clock) { return; }
      numbers.textContent = "";
      var labels = [];
      if (mode === "hour") {
        for (var index = 0; index < 12; index++) {
          labels.push({ text: String(index === 0 ? 12 : index), value: index === 0 ? 12 : index, radius: 80, degrees: index * 30 });
          labels.push({ text: pad(index === 0 ? 0 : index + 12), value: index === 0 ? 0 : index + 12, radius: 53, degrees: index * 30, inner: true });
        }
      } else {
        for (var five = 0; five < 60; five += 5) {
          labels.push({ text: pad(five), value: five, radius: 80, degrees: five * 6 });
        }
      }
      var current = mode === "hour" ? hour : minute;
      var radius = mode === "hour" && (hour === 0 || hour > 12) ? 53 : 80;
      var degrees = mode === "hour" ? (hour % 12) * 30 : minute * 6;
      var end = point(radius, degrees);
      hand.setAttribute("x2", end[0]); hand.setAttribute("y2", end[1]);
      knob.setAttribute("cx", end[0]); knob.setAttribute("cy", end[1]);
      knob.setAttribute("r", radius === 80 ? "15" : "13");
      dot.setAttribute("cx", end[0]); dot.setAttribute("cy", end[1]);
      dot.style.display = mode === "minute" && minute % 5 ? "" : "none";
      labels.forEach(function (label) {
        var at = point(label.radius, label.degrees);
        var text = document.createElementNS(SVG, "text");
        text.setAttribute("x", at[0]); text.setAttribute("y", at[1]);
        text.setAttribute("class", (label.inner ? "inner" : "") + (label.value === current ? " on" : ""));
        text.textContent = label.text;
        numbers.appendChild(text);
      });
      clock.setAttribute("aria-label", mode === "hour" ? texts.textHour || "Hour" : texts.textMinute || "Minute");
      clock.setAttribute("aria-valuemin", "0");
      clock.setAttribute("aria-valuemax", mode === "hour" ? "23" : "59");
      clock.setAttribute("aria-valuenow", String(current));
      clock.setAttribute("aria-valuetext", pad(hour) + ":" + pad(minute));
      hourField.classList.toggle("active", mode === "hour");
      minuteField.classList.toggle("active", mode === "minute");
    }

    function showFields() {
      if (hourField && document.activeElement !== hourField) { hourField.value = pad(hour); }
      if (minuteField && document.activeElement !== minuteField) { minuteField.value = pad(minute); }
    }

    function describe() {
      if (showDate) {
        showDate.textContent = "";
        showDate.appendChild(icon("calendar"));
        showDate.appendChild(document.createTextNode(chosen ? dayFormat.format(chosen) : texts.textDate || "Date"));
        showTime.textContent = "";
        showTime.appendChild(icon("clock"));
        showTime.appendChild(document.createTextNode(pad(hour) + ":" + pad(minute)));
      }
      if (apply) { apply.disabled = withDate && !chosen; }
    }

    function update() {
      renderClock();
      showFields();
      describe();
    }

    function setMode(next) {
      mode = next;
      update();
    }

    function showPane(time) {
      if (!showDate) { return; }
      box.classList.toggle("show-time", time);
      showDate.setAttribute("aria-pressed", time ? "false" : "true");
      showTime.setAttribute("aria-pressed", time ? "true" : "false");
    }

    /* -- taking the value -- */

    function valueNow() {
      var text = withDate ? isoDay(chosen) : "";
      if (kind === "datetime-local") { text += "T"; }
      if (withTime) { text += pad(hour) + ":" + pad(minute); }
      if (minimum && text < minimum) { text = minimum; }
      if (maximum && text > maximum) { text = maximum; }
      return text;
    }

    function write(text) {
      input.value = text;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function take() {
      if (withDate && !chosen) { return; }
      write(valueNow());
      box.close();
    }

    function chooseDay(pick) {
      if (pick.getAttribute("aria-disabled") === "true") { return; }
      var parts = pick.dataset.day.split("-");
      chosen = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
      if (!withTime) { take(); return; }
      var again = renderCalendar(pick.dataset.day);
      describe();
      if (showDate && NARROW.matches) {
        // On a phone the time comes next, on the clock face.
        showPane(true);
        setMode("hour");
        clock.focus();
      } else if (again) {
        again.focus();
      }
    }

    if (calendar) {
      calendar.addEventListener("click", function (event) {
        var pick = event.target.closest("button[data-day]");
        if (pick) { chooseDay(pick); }
      });
      previous.addEventListener("click", function () { turn(-1); });
      next.addEventListener("click", function () { turn(1); });
    }

    if (showDate) {
      showDate.addEventListener("click", function () {
        showPane(false);
        var day = calendar.querySelector('button[tabindex="0"]');
        if (day) { day.focus(); }
      });
      showTime.addEventListener("click", function () {
        showPane(true);
        clock.focus();
      });
    }

    if (clock) {
      var dragging = false, moved = false, startX = 0, startY = 0;

      var pickAt = function (event, final) {
        var frame = face.getBoundingClientRect();
        var x = (event.clientX - frame.left) / frame.width * 200 - 100;
        var y = (event.clientY - frame.top) / frame.height * 200 - 100;
        var degrees = Math.atan2(x, -y) * 180 / Math.PI;
        if (degrees < 0) { degrees += 360; }
        if (mode === "hour") {
          var index = Math.round(degrees / 30) % 12;
          var inner = Math.sqrt(x * x + y * y) < 66;
          hour = inner ? (index === 0 ? 0 : index + 12) : (index === 0 ? 12 : index);
        } else {
          minute = Math.round(degrees / 6) % 60;
          // A tap takes the nearest five minutes; dragging gives every minute.
          if (final && !moved) { minute = (Math.round(minute / 5) * 5) % 60; }
        }
        update();
      };

      clock.addEventListener("pointerdown", function (event) {
        if (event.button !== 0) { return; }
        event.preventDefault();
        clock.focus({ preventScroll: true });
        dragging = true; moved = false;
        startX = event.clientX; startY = event.clientY;
        if (clock.setPointerCapture) { clock.setPointerCapture(event.pointerId); }
        pickAt(event, false);
      });
      clock.addEventListener("pointermove", function (event) {
        if (!dragging) { return; }
        if (Math.abs(event.clientX - startX) + Math.abs(event.clientY - startY) > 6) { moved = true; }
        pickAt(event, false);
      });
      clock.addEventListener("pointerup", function (event) {
        if (!dragging) { return; }
        dragging = false;
        pickAt(event, true);
        if (mode === "hour") { setMode("minute"); }
      });
      clock.addEventListener("pointercancel", function () { dragging = false; });

      clock.addEventListener("keydown", function (event) {
        var key = event.key;
        var top = mode === "hour" ? 24 : 60;
        var current = mode === "hour" ? hour : minute;
        var steps = { ArrowUp: 1, ArrowRight: 1, ArrowDown: -1, ArrowLeft: -1, PageUp: mode === "hour" ? 3 : 5, PageDown: mode === "hour" ? -3 : -5 };
        var next = null;
        if (steps[key]) {
          next = (current + steps[key] + top) % top;
        } else if (key === "Home") {
          next = 0;
        } else if (key === "End") {
          next = top - 1;
        } else if (key === "Enter") {
          event.preventDefault();
          if (mode === "hour") { setMode("minute"); } else { take(); }
          return;
        } else if (/^[0-9]$/.test(key)) {
          // Digits are typed into the field of the hour or the minute.
          event.preventDefault();
          var field = mode === "hour" ? hourField : minuteField;
          field.focus();
          field.value = key;
          typed(field);
          return;
        } else {
          return;
        }
        event.preventDefault();
        if (mode === "hour") { hour = next; } else { minute = next; }
        update();
      });

      var typed = function (field) {
        var digits = field.value.replace(/\D/g, "").slice(0, 2);
        if (digits !== field.value) { field.value = digits; }
        var number = digits === "" ? NaN : Number(digits);
        if (field === hourField && number <= 23) { hour = number; }
        if (field === minuteField && number <= 59) { minute = number; }
        update();
        if (field === hourField && digits.length === 2) { minuteField.focus(); }
      };

      [hourField, minuteField].forEach(function (field) {
        field.addEventListener("focus", function () {
          setMode(field === hourField ? "hour" : "minute");
          field.select();
        });
        field.addEventListener("input", function () { typed(field); });
        field.addEventListener("blur", function () { field.value = pad(field === hourField ? hour : minute); });
        field.addEventListener("keydown", function (event) {
          if (event.key === "ArrowUp" || event.key === "ArrowDown") {
            event.preventDefault();
            var change = event.key === "ArrowUp" ? 1 : -1;
            if (field === hourField) { hour = (hour + change + 24) % 24; } else { minute = (minute + change + 60) % 60; }
            field.value = pad(field === hourField ? hour : minute);
            update();
          } else if (event.key === "Enter") {
            event.preventDefault();
            if (field === hourField) { minuteField.focus(); } else { take(); }
          }
        });
      });
    }

    today.addEventListener("click", function () {
      var moment = new Date();
      if (withDate) {
        chosen = midnight(moment);
        shown = new Date(moment.getFullYear(), moment.getMonth(), 1);
        if (!withTime) { take(); return; }
        renderCalendar(isoDay(chosen));
      } else {
        hour = moment.getHours();
        minute = Math.floor(moment.getMinutes() / 5) * 5;
      }
      update();
    });
    if (clear) {
      clear.addEventListener("click", function () {
        write("");
        box.close();
      });
    }
    cancel.addEventListener("click", function () { box.close(); });
    if (apply) { apply.addEventListener("click", take); }
    box.addEventListener("close", function () {
      box.remove();
      if (opener && document.body.contains(opener)) { opener.focus(); }
    });

    var first = renderCalendar();
    update();
    showPane(false);
    box.showModal();
    if (first) {
      first.focus();
    } else if (TOUCH.matches) {
      clock.focus();
    } else {
      hourField.focus();
    }
  }

  window.Rentalars = window.Rentalars || {};
  window.Rentalars.calendar = { marks: calendarMarks, markDay: markDay, legend: markLegend };
  window.Rentalars.enhancePickers = enhanceAll;

  // PRJ-100: the rental period was extended from the dialog over the crew planning – the page offers to show it.
  document.body.addEventListener("rentalPeriodChanged", function () {
    var note = document.getElementById("changed-note");
    if (note) { note.classList.remove("hidden"); }
  });

  document.body.addEventListener("htmx:afterSettle", function (event) { enhanceAll(event.target); });
  enhanceAll(document);
})();

/*
 * Material (MAT-050, PRD-046).
 *
 *  - MAT-050: the form "Neue Exemplare" asks for one serial number per item.
 *    <div data-serial-numbers data-count-field="id_count" data-item-label="Exemplar">
 *    holds a text field with one serial number per line. The script hides it
 *    and shows a field per item instead – as many as "Number of items" says –
 *    and writes them back into the text field, one per line. Enter jumps to
 *    the next field (a scanner ends every code with Enter); several lines
 *    pasted into one field fill the following ones. Without the script the
 *    text field itself takes the serial numbers.
 *  - PRD-046: <select data-reload-fields="kind category"> reloads a new
 *    product's form with the values of the named fields of the form, so that
 *    the server can prefill the rest: first the kind, then the category.
 */
(function () {
  "use strict";

  var MAX_ITEMS = 500;

  function setUpSerialNumbers(root) {
    var text = root.querySelector("textarea");
    if (!text) { return; }
    var countField = root.dataset.countField ? document.getElementById(root.dataset.countField) : null;
    var itemLabel = root.dataset.itemLabel || "";
    var label = root.querySelector("label[for='" + text.id + "']");
    var help = root.querySelector(".help");
    if (help && root.dataset.fieldsHelp && countField) { help.textContent = root.dataset.fieldsHelp; }
    var values = text.value.split(/\r?\n/);
    var shown = 0;

    var group = document.createElement("fieldset");
    group.className = "serial-fields";
    var legend = document.createElement("legend");
    legend.textContent = label ? label.textContent : "";
    group.appendChild(legend);
    var list = document.createElement("ol");
    group.appendChild(list);
    if (help && help.id) { group.setAttribute("aria-describedby", help.id); }

    text.hidden = true;
    text.setAttribute("tabindex", "-1");
    if (label) { label.hidden = true; }
    root.insertBefore(group, text);

    function write() {
      var lines = values.slice(0, shown);
      while (lines.length && !lines[lines.length - 1].trim()) { lines.pop(); }
      text.value = lines.join("\n");
    }

    function wanted() {
      if (!countField) { return 1; }
      var number = parseInt(countField.value, 10);
      if (isNaN(number) || number < 1) { return shown || 1; }
      return Math.min(number, MAX_ITEMS);
    }

    function render() {
      var count = wanted();
      while (shown < count) {
        shown += 1;
        var item = document.createElement("li");
        var input = document.createElement("input");
        var caption = document.createElement("label");
        input.type = "text";
        input.id = text.id + "_" + shown;
        input.maxLength = 120;
        input.autocomplete = "off";
        input.dataset.index = String(shown - 1);
        input.value = values[shown - 1] || "";
        caption.htmlFor = input.id;
        caption.textContent = countField ? itemLabel + " " + shown : legend.textContent;
        item.appendChild(caption);
        item.appendChild(input);
        list.appendChild(item);
      }
      while (shown > count) {
        list.removeChild(list.lastElementChild);
        shown -= 1;
      }
      write();
    }

    list.addEventListener("input", function (event) {
      var index = Number(event.target.dataset.index);
      while (values.length <= index) { values.push(""); }
      values[index] = event.target.value;
      write();
    });

    list.addEventListener("keydown", function (event) {
      if (event.key !== "Enter") { return; }
      event.preventDefault();
      var next = list.querySelector("input[data-index='" + (Number(event.target.dataset.index) + 1) + "']");
      if (next) { next.focus(); }
    });

    list.addEventListener("paste", function (event) {
      var pasted = (event.clipboardData || window.clipboardData).getData("text");
      if (!pasted || pasted.indexOf("\n") === -1) { return; }
      event.preventDefault();
      var lines = pasted.replace(/\r/g, "").split("\n");
      while (lines.length && !lines[lines.length - 1].trim()) { lines.pop(); }
      var start = Number(event.target.dataset.index);
      lines.forEach(function (line, offset) {
        while (values.length <= start + offset) { values.push(""); }
        values[start + offset] = line.trim();
      });
      if (countField && start + lines.length > wanted()) {
        countField.value = String(Math.min(start + lines.length, MAX_ITEMS));
      }
      render();
      list.querySelectorAll("input").forEach(function (input) { input.value = values[Number(input.dataset.index)] || ""; });
      write();
    });

    if (countField) {
      countField.addEventListener("input", render);
      countField.addEventListener("change", render);
    }
    render();
  }

  // PRD-046: reload the form of a new product with the chosen kind and category.
  document.addEventListener("change", function (event) {
    var names = event.target.dataset ? event.target.dataset.reloadFields : null;
    if (!names || !event.target.form) { return; }
    var form = event.target.form;
    var query = [];
    names.split(/\s+/).forEach(function (name) {
      var field = form.elements[name];
      if (field && field.value) { query.push(encodeURIComponent(name) + "=" + encodeURIComponent(field.value)); }
    });
    if (query.length) { window.location.search = "?" + query.join("&"); }
  });

  function initialise(root) {
    root.querySelectorAll("[data-serial-numbers]").forEach(function (element) {
      if (!element.dataset.ready) { element.dataset.ready = "1"; setUpSerialNumbers(element); }
    });
  }

  document.body.addEventListener("htmx:afterSettle", function () { initialise(document); });
  initialise(document);
})();

/* ==== PRJ-101: "create" from a type-ahead in a dialog ======================
 * The last suggestion of a type-ahead field can create what was typed
 * (PRJ-070); its form opens in the dialog of the page. A type-ahead that is
 * itself inside a dialog – the supplier of a subrental, in the dialog of the
 * line – would lose the form being filled in that way. There the form opens
 * in a dialog of its own, over the first one. Saved ("objectCreated" with
 * "closeDialog"), only this dialog closes: the new record lands in the
 * field, and the form underneath keeps everything typed. Escape and
 * "Abbrechen" close only this dialog; the focus returns to the field.
 */
(function () {
  "use strict";

  var opener = null;

  function createDialog() {
    var box = document.getElementById("create-dialog");
    if (box) { return box; }
    box = document.createElement("dialog");
    box.id = "create-dialog";
    box.className = "dialog";
    document.body.appendChild(box);
    // Its buttons close this dialog only, not the dialog underneath.
    box.addEventListener("click", function (event) {
      if (event.target.closest("[data-close-dialog]")) {
        event.stopPropagation();
        box.close();
      }
    });
    // The answer of a saved form closes this dialog only – after "objectCreated" has reached the page.
    box.addEventListener("closeDialog", function (event) {
      event.stopPropagation();
      window.setTimeout(function () { if (box.open) { box.close(); } }, 0);
    });
    box.addEventListener("htmx:afterSwap", function () {
      if (!box.firstElementChild) { return; }
      var heading = box.querySelector("h2[id]");
      if (heading) { box.setAttribute("aria-labelledby", heading.id); }
      if (!box.open) { box.showModal(); }
      var field = box.querySelector(".has-error input, .has-error select, input:not([type=hidden])");
      if (field) { field.focus(); }
    });
    box.addEventListener("close", function () {
      box.innerHTML = "";
      var field = opener;
      opener = null;
      if (!field || !document.body.contains(field)) { return; }
      // After the browser has put the focus back itself: the field takes typing again, the caret at its end.
      window.setTimeout(function () {
        field.focus();
        if (field.setSelectionRange) { field.setSelectionRange(field.value.length, field.value.length); }
      }, 0);
    });
    return box;
  }

  document.addEventListener("typeaheadCreate", function (event) {
    var root = event.target;
    if (!root.closest || !root.closest("dialog") || !window.htmx) { return; }
    event.preventDefault();
    opener = event.detail.input || null;
    window.htmx.ajax("GET", event.detail.url, { target: createDialog(), swap: "innerHTML" });
  });
})();

/* ==== UIX-010: the chat in the project; ADM-013: the form of an automation ====================
 *
 * Chat: every page of a project watches "chat:<pk>" (core/changes.py). Its stamp reads
 * "<content>~<unread>". The unread count goes into the tab "Chat"; on the chat itself a changed content
 * fetches the messages in place – no page load, the field keeps what is typed, a message being changed
 * stays open. "@" and the beginning of a name offer the people who read along (a list box: arrows,
 * Enter or Tab, Escape); the names under "… lesen mit" put a mention into the field as well.
 * Ctrl+Enter sends.
 *
 * Automation: <form data-automation-form> shows only the parts whose data-show-when holds
 * ("trigger:inquiry", "action:notify;recipient:user") and offers only the actions and recipients
 * that fit the chosen trigger (data-actions-of, data-recipients-of). Without the script every part
 * shows, and the server says what does not fit.
 */
(function () {
  "use strict";

  /* ---- Chat in the project (UIX-010) ---------------------------------------- */

  function contentPart(stamp) {
    var at = (stamp || "").indexOf("~");
    return at < 0 ? (stamp || "") : stamp.slice(0, at);
  }

  function unreadPart(stamp) {
    var at = (stamp || "").indexOf("~");
    return at < 0 ? 0 : (parseInt(stamp.slice(at + 1), 10) || 0);
  }

  var chat = document.querySelector("[data-chat]");
  var refreshing = false;

  function chatHolder() { return document.getElementById("chat-messages"); }

  function nearEnd(element) {
    return !element || element.scrollHeight - element.scrollTop - element.clientHeight < 60;
  }

  function refreshChat() {
    var holder = chatHolder();
    if (!chat || !holder || refreshing) { return; }
    // A message being changed stays as it is until it is saved.
    if (holder.querySelector("details.chat-edit[open]")) { return; }
    var log = holder.querySelector(".chat-log");
    var stick = nearEnd(log);
    var keepTop = log ? log.scrollTop : 0;
    refreshing = true;
    fetch(chat.dataset.chatUrl, { credentials: "same-origin", headers: { "HX-Request": "true" } })
      .then(function (response) { return response.ok ? response.text() : null; })
      .then(function (html) {
        refreshing = false;
        if (html === null) { return; }
        var known = {};
        holder.querySelectorAll(".bubble[id]").forEach(function (bubble) { known[bubble.id] = true; });
        holder.innerHTML = html;
        if (window.htmx) { window.htmx.process(holder); }
        // UIX-010: the newest message of somebody else that was not there before is read out.
        var arrived = Array.prototype.filter.call(holder.querySelectorAll(".bubble.is-in[id]"), function (bubble) {
          return !known[bubble.id];
        });
        var announce = document.querySelector("[data-chat-announce]");
        if (announce && arrived.length) {
          var last = arrived[arrived.length - 1];
          var author = last.querySelector(".bubble-head strong");
          var text = last.querySelector(".bubble-text");
          announce.textContent = (announce.dataset.textNew || "New message from") + " " +
            (author ? author.textContent.trim() : "") + ": " + (text ? text.textContent.trim() : "");
        }
        var fresh = holder.querySelector(".chat-log");
        if (fresh) {
          fresh.dataset.ready = "1";
          fresh.scrollTop = stick ? fresh.scrollHeight : keepTop;
        }
      })
      .catch(function () { refreshing = false; });
  }

  function showUnread(badge, count) {
    badge.textContent = "";
    if (count) {
      badge.appendChild(document.createTextNode(String(count)));
      var label = document.createElement("span");
      label.className = "visually-hidden";
      label.textContent = " " + (badge.dataset.label || "");
      badge.appendChild(label);
    }
    badge.classList.toggle("hidden", !count);
  }

  document.addEventListener("rentalars:stamps", function (event) {
    var stamps = event.detail || {};
    Object.keys(stamps).forEach(function (key) {
      if (key.indexOf("chat:") !== 0 || !stamps[key]) { return; }
      var pk = key.slice(5);
      var onChat = chat && chat.dataset.chat === pk;
      document.querySelectorAll('[data-chat-unread="' + pk + '"]').forEach(function (badge) {
        showUnread(badge, onChat ? 0 : unreadPart(stamps[key]));
      });
      if (onChat) {
        var shown = chatHolder() && chatHolder().querySelector("[data-stamp]");
        if (!shown || shown.dataset.stamp !== contentPart(stamps[key])) { refreshChat(); }
      }
    });
  });

  if (chat) {
    var form = chat.querySelector("[data-chat-form]");
    var input = chat.querySelector("[data-chat-input]");
    var box = document.getElementById("chat-suggestions");
    var names = Array.prototype.map.call(chat.querySelectorAll("[data-chat-mention]"), function (button) {
      return button.dataset.chatMention;
    });
    var active = -1;

    // The message is in: the field is empty again (HX-Trigger "chatSent" of chat.views).
    document.body.addEventListener("chatSent", function () {
      if (!form || !input) { return; }
      form.reset();
      input.value = "";
      showFileError("");
      input.focus();
    });

    // UIX-049: too many or too large files are said before the upload, and a long upload shows
    // how far it got. The server checks again (chat.media); without this script it alone does.
    var fileError = chat.querySelector("[data-chat-file-error]");
    var progress = chat.querySelector("[data-chat-progress]");

    function showFileError(text) {
      if (!fileError) { return; }
      fileError.textContent = text || "";
      fileError.classList.toggle("hidden", !text);
    }

    function checkFiles() {
      var files = [];
      form.querySelectorAll("[data-chat-files]").forEach(function (field) {
        Array.prototype.forEach.call(field.files || [], function (file) { files.push(file); });
      });
      var megabyte = 1024 * 1024;
      var total = 0;
      var tooLarge = files.some(function (file) {
        total += file.size;
        var limit = (file.type || "").indexOf("video/") === 0 ? form.dataset.maxVideoMb : form.dataset.maxPhotoMb;
        return file.size > Number(limit) * megabyte;
      });
      if (files.length > Number(form.dataset.maxFiles)) { showFileError(form.dataset.textTooMany); return false; }
      if (tooLarge || total > Number(form.dataset.maxMessageMb) * megabyte) {
        showFileError(form.dataset.textTooLarge);
        return false;
      }
      showFileError("");
      return true;
    }

    if (form) {
      form.addEventListener("change", function (event) {
        if (event.target.matches("[data-chat-files]")) { checkFiles(); }
      });
      form.addEventListener("htmx:beforeRequest", function (event) {
        if (event.target === form && !checkFiles()) { event.preventDefault(); }
      });
      form.addEventListener("submit", function (event) {
        if (!window.htmx && !checkFiles()) { event.preventDefault(); }
      });
      form.addEventListener("htmx:xhr:progress", function (event) {
        var detail = event.detail || {};
        if (!progress || !detail.lengthComputable || detail.total < 512 * 1024) { return; }
        progress.classList.remove("hidden");
        progress.value = Math.round(detail.loaded * 100 / detail.total);
      });
      form.addEventListener("htmx:afterRequest", function () {
        if (progress) { progress.classList.add("hidden"); progress.value = 0; }
      });
    }

    function closeSuggestions() {
      if (!box) { return; }
      box.classList.add("hidden");
      box.innerHTML = "";
      input.removeAttribute("aria-activedescendant");
      active = -1;
    }

    // "@" at the start of a word, and what follows it up to the caret.
    function mentionBeforeCaret() {
      var before = input.value.slice(0, input.selectionStart);
      var at = before.lastIndexOf("@");
      if (at < 0 || (at > 0 && !/[\s(]/.test(before.charAt(at - 1)))) { return null; }
      var typed = before.slice(at + 1);
      if (typed.length > 40 || /[\n@]/.test(typed)) { return null; }
      return { start: at, typed: typed };
    }

    function choose(name) {
      var found = mentionBeforeCaret();
      var caret = input.selectionStart;
      var start = found ? found.start : caret;
      var text = "@" + name + " ";
      if (!found && start > 0 && !/\s/.test(input.value.charAt(start - 1))) { text = " " + text; }
      input.value = input.value.slice(0, start) + text + input.value.slice(caret);
      var end = start + text.length;
      input.focus();
      input.setSelectionRange(end, end);
      closeSuggestions();
    }

    function markActive() {
      Array.prototype.forEach.call(box.children, function (option, index) {
        option.setAttribute("aria-selected", index === active ? "true" : "false");
      });
      if (active >= 0) {
        input.setAttribute("aria-activedescendant", box.children[active].id);
      } else {
        input.removeAttribute("aria-activedescendant");
      }
    }

    function suggest() {
      var found = mentionBeforeCaret();
      if (!found || !box) { closeSuggestions(); return; }
      var typed = found.typed.toLowerCase();
      var matches = names.filter(function (name) {
        var lower = name.toLowerCase();
        return lower.indexOf(typed) === 0 || lower.split(/\s+/).some(function (word) { return word.indexOf(typed) === 0; });
      }).slice(0, 8);
      if (!matches.length) { closeSuggestions(); return; }
      box.innerHTML = "";
      matches.forEach(function (name, index) {
        var option = document.createElement("li");
        option.id = "chat-suggestion-" + index;
        option.setAttribute("role", "option");
        option.textContent = name;
        option.addEventListener("mousedown", function (event) { event.preventDefault(); choose(name); });
        box.appendChild(option);
      });
      active = 0;
      markActive();
      box.classList.remove("hidden");
    }

    if (input) {
      input.addEventListener("input", suggest);
      input.addEventListener("blur", function () { window.setTimeout(closeSuggestions, 100); });
      input.addEventListener("keydown", function (event) {
        var open = box && !box.classList.contains("hidden") && box.children.length;
        if (open && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
          event.preventDefault();
          active = (active + (event.key === "ArrowDown" ? 1 : -1) + box.children.length) % box.children.length;
          markActive();
          return;
        }
        if (open && (event.key === "Enter" || event.key === "Tab") && active >= 0 && !event.ctrlKey && !event.metaKey) {
          event.preventDefault();
          choose(box.children[active].textContent);
          return;
        }
        if (open && event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          closeSuggestions();
          return;
        }
        if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && form) {
          event.preventDefault();
          form.requestSubmit();
        }
      });
    }

    chat.addEventListener("click", function (event) {
      var button = event.target.closest("[data-chat-mention]");
      if (!button || !input) { return; }
      closeSuggestions();
      input.focus();
      input.setSelectionRange(input.value.length, input.value.length);
      choose(button.dataset.chatMention);
    });
  }

  /* ---- The form of an automation (ADM-013) ----------------------------------- */

  var automation = document.querySelector("[data-automation-form]");
  if (automation) {
    var actionsOf = {};
    var recipientsOf = {};
    try {
      actionsOf = JSON.parse(automation.dataset.actionsOf || "{}");
      recipientsOf = JSON.parse(automation.dataset.recipientsOf || "{}");
    } catch (error) { /* without the lists every choice stays */ }

    var valueOf = function (name) {
      var field = automation.elements[name];
      return field ? field.value : "";
    };

    var limit = function (select, allowed) {
      if (!select || !allowed) { return; }
      Array.prototype.forEach.call(select.options, function (option) {
        var fits = !option.value || allowed.indexOf(option.value) >= 0;
        option.hidden = !fits;
        option.disabled = !fits;
      });
      if (select.value && allowed.indexOf(select.value) < 0) { select.value = allowed[0]; }
    };

    var update = function () {
      var trigger = valueOf("trigger");
      limit(automation.elements.action, actionsOf[trigger]);
      limit(automation.elements.recipient, recipientsOf[trigger]);
      automation.querySelectorAll("[data-show-when]").forEach(function (part) {
        var shows = part.dataset.showWhen.split(";").every(function (condition) {
          var bits = condition.split(":");
          return (bits[1] || "").split(",").indexOf(valueOf(bits[0])) >= 0;
        });
        part.classList.toggle("hidden", !shows);
      });
    };

    automation.addEventListener("change", update);
    update();
  }
})();

/* ==== UIX-034, PRJ-097: maps at addresses ==================================
 * "Karte anzeigen" fetches the map of an address as a part of the page
 * (templates/core/_map.html). Its element [data-map] names the places, the
 * tile server and where Leaflet lies on this server; Leaflet
 * (static/vendor/leaflet, BSD-2-Clause) is loaded only now, the first time a
 * map is shown. The browser loads the map pictures from the tile server of
 * the configuration file – the content security policy of a page with a map
 * allows exactly that one.
 *
 * Correcting a position: opening "Position korrigieren" of a place makes its
 * marker draggable, and a click into the map puts it there; both fill the
 * fields for latitude and longitude, which can also be typed – the way with
 * the keyboard. The wheel of the mouse zooms only while the map has the
 * focus, so that scrolling the page does not zoom it by accident.
 */
(function () {
  "use strict";

  var loading = null;

  function loadLeaflet(urls) {
    if (window.L) { return Promise.resolve(window.L); }
    if (loading) { return loading; }
    loading = new Promise(function (resolve, reject) {
      var style = document.createElement("link");
      style.rel = "stylesheet";
      style.href = urls.css;
      document.head.appendChild(style);
      var script = document.createElement("script");
      script.src = urls.js;
      script.onload = function () { resolve(window.L); };
      script.onerror = function () { loading = null; reject(new Error("Leaflet could not be loaded")); };
      document.head.appendChild(script);
    });
    return loading;
  }

  function escapeHtml(text) {
    var box = document.createElement("span");
    box.textContent = text;
    return box.innerHTML.replace(/"/g, "&quot;");
  }

  function pin(L, number) {
    return L.divIcon({
      className: "map-pin",
      html: "<span><b>" + Number(number) + "</b></span>",
      iconSize: [32, 40],
      iconAnchor: [16, 38],
      popupAnchor: [0, -34]
    });
  }

  function popupContent(place) {
    var box = document.createElement("div");
    var title = document.createElement("strong");
    title.textContent = place.number + ". " + place.label;
    box.appendChild(title);
    if (place.address && place.address !== place.label) {
      var line = document.createElement("div");
      line.textContent = place.address;
      box.appendChild(line);
    }
    return box;
  }

  function addMarker(L, map, place, latlng) {
    var label = place.number + ". " + place.label;
    var marker = L.marker(latlng, { icon: pin(L, place.number), title: label, keyboard: true, riseOnHover: true });
    marker.bindPopup(popupContent(place));
    marker.addTo(map);
    var element = marker.getElement();
    if (element) { element.setAttribute("aria-label", label); }
    return marker;
  }

  function draw(L, element, data) {
    var frame = element.closest(".map-frame");
    var map = L.map(element, { zoomControl: false, scrollWheelZoom: false });
    element.mapInstance = map;
    L.control.zoom({ zoomInTitle: data.texts.zoomIn, zoomOutTitle: data.texts.zoomOut }).addTo(map);
    map.attributionControl.setPrefix('<a href="https://leafletjs.com" target="_blank" rel="noopener noreferrer">Leaflet</a>');
    L.tileLayer(data.tiles, {
      maxZoom: data.maxZoom,
      // UIX-034: the pages send "Referrer-Policy: same-origin", so the tile requests would carry no
      // Referer, which the tile usage policy of OpenStreetMap requires (else "Access blocked 403"). The tiles
      // carry the origin of the installation – only the origin, never the path of the page.
      referrerPolicy: data.referrerPolicy || "strict-origin-when-cross-origin",
      attribution: '<a href="' + escapeHtml(data.attributionUrl) + '" target="_blank" rel="noopener noreferrer">' +
        escapeHtml(data.attribution) + "</a>"
    }).addTo(map);
    map.on("focus", function () { map.scrollWheelZoom.enable(); });
    map.on("blur", function () { map.scrollWheelZoom.disable(); });

    var markers = {};
    var byKey = {};
    var bounds = [];
    data.places.forEach(function (place) {
      byKey[place.key] = place;
      if (place.lat === null || place.lon === null) { return; }
      markers[place.key] = addMarker(L, map, place, [place.lat, place.lon]);
      bounds.push([place.lat, place.lon]);
    });
    if (bounds.length > 1) {
      map.fitBounds(bounds, { padding: [36, 36], maxZoom: 16 });
    } else if (bounds.length === 1) {
      map.setView(bounds[0], 15);
    } else {
      map.setView(data.centre, data.zoom);
    }
    if (!frame) { return; }

    frame.querySelectorAll("details.map-correct").forEach(function (details) {
      var item = details.closest("[data-key]");
      var place = item ? byKey[item.dataset.key] : null;
      var latitude = details.querySelector("[data-map-latitude]");
      var longitude = details.querySelector("[data-map-longitude]");
      if (!place || !latitude || !longitude) { return; }
      var active = false;

      function fill(latlng) {
        latitude.value = latlng.lat.toFixed(6);
        longitude.value = latlng.lng.toFixed(6);
      }
      function marker() {
        if (!markers[place.key]) {
          var centre = map.getCenter();
          markers[place.key] = addMarker(L, map, place, centre);
          fill(centre);
        }
        return markers[place.key];
      }
      function dragged(event) { fill(event.target.getLatLng()); }
      function clicked(event) { marker().setLatLng(event.latlng); fill(event.latlng); }
      function start() {
        if (active) { return; }
        active = true;
        frame.querySelectorAll("details.map-correct[open]").forEach(function (other) {
          if (other !== details) { other.open = false; }
        });
        var own = marker();
        own.dragging.enable();
        own.on("dragend", dragged);
        map.on("click", clicked);
        element.classList.add("picking");
      }
      function stop() {
        if (!active) { return; }
        active = false;
        var own = markers[place.key];
        if (own && own.dragging) { own.dragging.disable(); own.off("dragend", dragged); }
        map.off("click", clicked);
        element.classList.remove("picking");
      }
      details.addEventListener("toggle", function () { if (details.open) { start(); } else { stop(); } });
      [latitude, longitude].forEach(function (input) {
        input.addEventListener("change", function () {
          var lat = parseFloat(latitude.value.replace(",", "."));
          var lng = parseFloat(longitude.value.replace(",", "."));
          if (isFinite(lat) && isFinite(lng) && Math.abs(lat) <= 90 && Math.abs(lng) <= 180) {
            marker().setLatLng([lat, lng]);
            map.panTo([lat, lng]);
          }
        });
      });
      if (details.open) { start(); }
    });
  }

  function setUp(element) {
    var data;
    try { data = JSON.parse(element.dataset.map); } catch (error) { return; }
    loadLeaflet(data.leaflet).then(function (L) { draw(L, element, data); }, function () {
      element.classList.add("hidden");
    });
  }

  function initialise(root) {
    root.querySelectorAll("[data-map]").forEach(function (element) {
      if (!element.dataset.mapReady) { element.dataset.mapReady = "1"; setUp(element); }
    });
  }

  // A map that is replaced (a position was saved) gives its resources back first.
  document.body.addEventListener("htmx:beforeSwap", function (event) {
    var target = event.detail.target;
    if (!target || !target.querySelectorAll) { return; }
    target.querySelectorAll("[data-map]").forEach(function (element) {
      if (element.mapInstance) { element.mapInstance.remove(); element.mapInstance = null; }
    });
  });
  // The button that fetched the map is gone: the focus goes to the map, not back to the top of the page.
  document.body.addEventListener("htmx:afterSwap", function (event) {
    var box = event.detail.target;
    if (!box || !box.classList || !box.classList.contains("map-box")) { return; }
    var frame = box.querySelector(".map-frame");
    if (frame && (!document.activeElement || document.activeElement === document.body || !document.body.contains(document.activeElement))) {
      frame.focus({ preventScroll: true });
    }
  });
  document.body.addEventListener("htmx:afterSettle", function () { initialise(document); });
  initialise(document);
})();

/* ==== PRJ-089: show files as project files ===================================================
 * The upload form of the project files carries the endings of show files in data-show-endings: choosing a
 * file whose name ends like a show file picks the document type for show files (an <option data-showfile>)
 * while no type is chosen, and fills in the console where the ending tells it. The fields of a show file
 * ([data-showfile-fields]: console, version, current show) are shown only while such a type is chosen;
 * without script they stay visible, and the server does the same picking.
 */
(function () {
  "use strict";

  function chosenIsShow(select) {
    var option = select && select.options[select.selectedIndex];
    return Boolean(option && option.hasAttribute("data-showfile"));
  }

  function showFields(form) {
    var select = form.querySelector('select[name="document_type"]');
    if (!select) { return; }
    var show = chosenIsShow(select);
    form.querySelectorAll("[data-showfile-fields]").forEach(function (box) {
      box.classList.toggle("hidden", !show);
    });
  }

  function ending(name, endings) {
    var lower = (name || "").toLowerCase();
    var found = "";
    Object.keys(endings).forEach(function (candidate) {
      // The longest ending wins: "x.show.gz" is ".show.gz", not ".gz".
      if (lower.length > candidate.length && lower.slice(-candidate.length) === candidate && candidate.length > found.length) {
        found = candidate;
      }
    });
    return found;
  }

  function fileChosen(input) {
    var endings;
    try { endings = JSON.parse(input.dataset.showEndings || "{}"); } catch (error) { return; }
    var file = input.files && input.files[0];
    var found = file ? ending(file.name, endings) : "";
    var form = input.closest("form");
    if (!found || !form) { return; }
    var select = form.querySelector('select[name="document_type"]');
    var showOption = select && select.querySelector("option[data-showfile]");
    if (select && showOption && !select.value) {
      select.value = showOption.value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
    var system = form.querySelector('input[name="show_system"]');
    if (system && !system.value && endings[found] && chosenIsShow(select)) {
      system.value = endings[found];
    }
    showFields(form);
  }

  function initialise(root) {
    root.querySelectorAll("[data-showfile-fields]").forEach(function (box) {
      var form = box.closest("form");
      if (form) { showFields(form); }
    });
  }

  document.addEventListener("change", function (event) {
    var target = event.target;
    if (target.matches && target.matches("input[type=file][data-show-endings]")) {
      fileChosen(target);
    } else if (target.matches && target.matches('select[name="document_type"]')) {
      var form = target.closest("form");
      if (form) { showFields(form); }
    }
  });
  document.body.addEventListener("htmx:afterSettle", function () { initialise(document); });
  initialise(document);
})();

/*
 * ZEI-019: pages that list expenses without refreshing themselves (the deployment view) carry
 * data-reload-after-expenses. When an expense was recorded in the dialog, they are loaded again once the
 * dialog closes – as data-reload-after-times does for times.
 */
(function () {
  "use strict";
  var dialog = document.getElementById("dialog");
  var expensesChanged = false;
  document.body.addEventListener("expensesChanged", function () { expensesChanged = true; });
  if (dialog) {
    dialog.addEventListener("close", function () {
      if (expensesChanged && document.querySelector("[data-reload-after-expenses]")) {
        window.location.reload();
      }
      expensesChanged = false;
    });
  }
})();

/* ==== VFG-026: moving appointments by dragging them in a timeline ===================================
 * In hour columns – the view "Tage" of Planung → Zeitstrahl and the timeline on the tab "Zeitplanung" – a bar with
 * [data-tl-move] (the rental period, the event or a phase of a project the user may change) can be dragged: by its
 * middle to move it, by one of its ends (.tl-grip) to change the start or the end. The times snap to 15 minutes; a
 * dashed frame shows where the bar would go, with its new times. Dropping opens the dialog of the server with what
 * follows (schedule/move_views.py); nothing changes before "Verschieben" there.
 * Keyboard: on a chosen bar, ← and → move it by 15 minutes, with Shift its end; the new times are announced
 * ([data-tl-announce]). Enter opens the dialog, Escape takes the move back.
 * A bar of the timeline on "Zeitplanung" ([data-tl-dialog]) opens the dialog with a click as well – its times can
 * be typed there; a bar of Planung → Zeitstrahl still opens its project. A finger does not drag: it scrolls.
 * After a move the page is loaded again when the dialog closes, and the focus goes back to the bar.
 */
(function () {
  "use strict";

  var STEP = 15;
  var THRESHOLD = 4;
  var FOCUS_KEY = "rentalars.timeline-moved";
  var dialog = document.getElementById("dialog");
  var locale = document.documentElement.lang || "de";
  // The minutes count the wall clock as if it were UTC: no time zone of the browser comes in between.
  var weekdayFormat = new Intl.DateTimeFormat(locale, { weekday: "short", timeZone: "UTC" });
  var drag = null;
  var opened = null;
  var moved = null;
  var suppressClick = false;

  function minutesOf(text) {
    var match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(text || "");
    if (!match) { return null; }
    return Date.UTC(+match[1], +match[2] - 1, +match[3], +match[4], +match[5]) / 60000;
  }
  function pad(number) { return (number < 10 ? "0" : "") + number; }
  function textOf(minutes) {
    var date = new Date(minutes * 60000);
    return date.getUTCFullYear() + "-" + pad(date.getUTCMonth() + 1) + "-" + pad(date.getUTCDate()) +
      "T" + pad(date.getUTCHours()) + ":" + pad(date.getUTCMinutes());
  }
  // "Do 22.10. 14:15 – 20:15", over midnight with both days – as the dialog of the server writes it.
  function dayText(date) {
    // UIX-029: "Thu 22/10" in English.
    if (/^en/i.test(locale)) { return weekdayFormat.format(date) + " " + pad(date.getUTCDate()) + "/" + pad(date.getUTCMonth() + 1); }
    return weekdayFormat.format(date).replace(/\.$/, "") + " " + pad(date.getUTCDate()) + "." + pad(date.getUTCMonth() + 1) + ".";
  }
  function timeText(date) { return pad(date.getUTCHours()) + ":" + pad(date.getUTCMinutes()); }
  function periodText(start, end) {
    var from = new Date(start * 60000), until = new Date(end * 60000);
    var text = dayText(from) + " " + timeText(from) + " – ";
    if (from.toISOString().slice(0, 10) !== until.toISOString().slice(0, 10)) { text += dayText(until) + " "; }
    return text + timeText(until);
  }
  function snap(minutes) { return Math.round(minutes / STEP) * STEP; }

  // Where the columns of the bar's row begin, and how many minutes one pixel of it is.
  function begin(bar, mode) {
    var panel = bar.closest("[data-tl-zoom]");
    var row = bar.closest(".tl-row");
    var start = minutesOf(bar.dataset.tlStart), end = minutesOf(bar.dataset.tlEnd);
    if (!panel || !row || start === null || end === null) { return null; }
    var first = minutesOf((panel.dataset.first || "") + "T00:00");
    var total = parseInt(panel.dataset.columns || "0", 10) * parseInt(panel.dataset.hours || "0", 10) * 60;
    var width = row.getBoundingClientRect().width;
    if (first === null || !total || !width) { return null; }
    return { bar: bar, mode: mode, row: row, first: first, perPixel: total / width,
      start: start, end: end, newStart: start, newEnd: end, ghost: null };
  }

  function changed(state) { return state.newStart !== state.start || state.newEnd !== state.end; }

  function place(state, start, end) {
    state.newStart = start;
    state.newEnd = end;
    if (!state.ghost) {
      state.ghost = document.createElement("div");
      state.ghost.className = "tl-ghost";
      state.ghost.setAttribute("aria-hidden", "true");
      state.row.appendChild(state.ghost);
      state.bar.classList.add("is-moving");
    }
    var ghost = state.ghost;
    ghost.style.left = ((start - state.first) / state.perPixel) + "px";
    ghost.style.width = Math.max(2, (end - start) / state.perPixel) + "px";
    ghost.style.top = state.bar.offsetTop + "px";
    ghost.style.height = state.bar.offsetHeight + "px";
    // The new times above the frame, outside the timeline that would cut them off.
    if (!state.tip) {
      state.tip = document.createElement("div");
      state.tip.className = "tl-drag-tip";
      state.tip.setAttribute("aria-hidden", "true");
      document.body.appendChild(state.tip);
    }
    state.tip.textContent = (state.bar.dataset.tlName || "") + ": " + periodText(start, end);
    var box = ghost.getBoundingClientRect();
    var panel = state.row.closest("[data-tl-zoom]").getBoundingClientRect();
    var left = Math.min(Math.max(box.left, panel.left), panel.right - state.tip.offsetWidth);
    state.tip.style.left = Math.max(4, left) + "px";
    state.tip.style.top = Math.max(4, box.top - state.tip.offsetHeight - 6) + "px";
  }

  function reset(state) {
    if (!state) { return; }
    if (state.ghost) { state.ghost.remove(); state.ghost = null; }
    if (state.tip) { state.tip.remove(); state.tip = null; }
    state.bar.classList.remove("is-moving");
  }

  function announce(text) {
    var region = document.querySelector("[data-tl-announce]");
    if (region) { region.textContent = text; }
  }

  function openDialog(state) {
    var url = state.bar.dataset.tlMove;
    if (changed(state)) {
      url += "&start=" + encodeURIComponent(textOf(state.newStart)) + "&end=" + encodeURIComponent(textOf(state.newEnd));
    }
    url += "&next=" + encodeURIComponent(window.location.pathname + window.location.search);
    if (!window.htmx || !dialog) { window.location.assign(url); return; }
    opened = state;
    moved = null;
    window.htmx.ajax("GET", url, { target: "#dialog" });
  }

  /* ---- Dragging with the mouse or a pen ---- */

  document.addEventListener("pointerdown", function (event) {
    if (event.button !== 0 || event.pointerType === "touch" || drag || opened) { return; }
    var bar = event.target.closest ? event.target.closest("[data-tl-move]") : null;
    if (!bar) { return; }
    var grip = event.target.closest(".tl-grip");
    var mode = grip ? (grip.classList.contains("is-start") ? "start" : "end") : "move";
    var state = begin(bar, mode);
    if (!state) { return; }
    state.x = event.clientX;
    state.pointer = event.pointerId;
    state.dragging = false;
    drag = state;
  });

  document.addEventListener("pointermove", function (event) {
    if (!drag || drag.keyboard || event.pointerId !== drag.pointer) { return; }
    var shift = event.clientX - drag.x;
    if (!drag.dragging) {
      if (Math.abs(shift) < THRESHOLD) { return; }
      drag.dragging = true;
      document.documentElement.classList.add("tl-is-dragging");
      try { drag.bar.setPointerCapture(event.pointerId); } catch (error) { /* the pointer is gone already */ }
    }
    event.preventDefault();
    var minutes = shift * drag.perPixel;
    if (drag.mode === "move") {
      var start = snap(drag.start + minutes);
      place(drag, start, start + drag.end - drag.start);
    } else if (drag.mode === "start") {
      place(drag, Math.min(snap(drag.start + minutes), drag.end - STEP), drag.end);
    } else {
      place(drag, drag.start, Math.max(snap(drag.end + minutes), drag.start + STEP));
    }
  });

  function drop(event) {
    if (!drag || drag.keyboard || event.pointerId !== drag.pointer) { return; }
    var state = drag;
    drag = null;
    document.documentElement.classList.remove("tl-is-dragging");
    if (!state.dragging) { return; }
    // The click that follows the drop must neither open the project nor the dialog once more.
    suppressClick = true;
    window.setTimeout(function () { suppressClick = false; }, 400);
    if (event.type === "pointercancel" || !changed(state)) { reset(state); return; }
    openDialog(state);
  }
  document.addEventListener("pointerup", drop);
  document.addEventListener("pointercancel", drop);

  // A link is not to be dragged by the browser itself.
  document.addEventListener("dragstart", function (event) {
    if (event.target.closest && event.target.closest("[data-tl-move]")) { event.preventDefault(); }
  });

  document.addEventListener("click", function (event) {
    var bar = event.target.closest ? event.target.closest("[data-tl-move]") : null;
    if (!bar) { return; }
    if (suppressClick) {
      suppressClick = false;
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    if (bar.hasAttribute("data-tl-dialog") && !event.ctrlKey && !event.metaKey && !event.shiftKey && !opened) {
      // On "Zeitplanung" a click opens the dialog with the present times, to be changed there.
      event.preventDefault();
      var state = drag && drag.keyboard && drag.bar === bar ? drag : begin(bar, "move");
      drag = null;
      if (state) { openDialog(state); }
    }
  }, true);

  /* ---- The keyboard ---- */

  document.addEventListener("keydown", function (event) {
    var bar = event.target.closest ? event.target.closest("[data-tl-move]") : null;
    if (!bar || event.altKey || event.ctrlKey || event.metaKey) { return; }
    var mine = drag && drag.keyboard && drag.bar === bar;
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      if (!mine) {
        reset(drag);
        drag = begin(bar, "move");
        if (!drag) { return; }
        drag.keyboard = true;
      }
      var step = event.key === "ArrowLeft" ? -STEP : STEP;
      if (event.shiftKey) {
        place(drag, drag.newStart, Math.max(snap(drag.newEnd + step), drag.newStart + STEP));
      } else {
        var start = snap(drag.newStart + step);
        place(drag, start, start + drag.newEnd - drag.newStart);
      }
      var hint = document.getElementById("tl-move-hint");
      announce((bar.dataset.tlName || "") + ": " + periodText(drag.newStart, drag.newEnd) + ". " +
        (hint ? hint.dataset.textPending || "" : ""));
    } else if (event.key === "Enter" && mine) {
      event.preventDefault();
      var state = drag;
      drag = null;
      if (changed(state) || bar.hasAttribute("data-tl-dialog")) { openDialog(state); } else { reset(state); }
    } else if (event.key === "Escape" && mine) {
      event.preventDefault();
      reset(drag);
      drag = null;
      announce("");
    }
  });

  // A move begun with the keyboard ends when the focus leaves the bar – but not for the dialog it opened.
  document.addEventListener("focusout", function (event) {
    if (drag && drag.keyboard && event.target === drag.bar) {
      reset(drag);
      drag = null;
    }
  });

  /* ---- After the dialog ---- */

  document.body.addEventListener("timelineMoved", function (event) {
    var detail = event.detail && event.detail.value ? event.detail.value : event.detail;
    moved = detail && detail.key ? detail.key : "moved";
  });

  function forget() {
    if (!opened) { return; }
    reset(opened);
    opened = null;
  }

  // The dialog could not be loaded (an error, no connection): the bar goes back to its place.
  document.body.addEventListener("htmx:responseError", forget);
  document.body.addEventListener("htmx:sendError", forget);

  if (dialog) {
    dialog.addEventListener("close", function () {
      if (!opened) { return; }
      var state = opened;
      opened = null;
      if (moved) {
        try { window.sessionStorage.setItem(FOCUS_KEY, state.bar.dataset.tlKey || ""); } catch (error) { /* no storage */ }
        window.location.reload();
        return;
      }
      reset(state);
      if (document.contains(state.bar)) { state.bar.focus({ preventScroll: true }); }
    });
  }

  // After the page was loaded again: the focus back on the bar that was moved.
  var key = "";
  try {
    key = window.sessionStorage.getItem(FOCUS_KEY) || "";
    window.sessionStorage.removeItem(FOCUS_KEY);
  } catch (error) { key = ""; }
  if (key) {
    var bar = document.querySelector('[data-tl-key="' + (window.CSS && CSS.escape ? CSS.escape(key) : key) + '"]');
    if (bar) {
      bar.focus({ preventScroll: true });
      bar.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  }
})();

/* ==== PER-039: marking a time range in the week of the availability calendar ==========================
 * Where the availability can be entered ([data-avail-select] on the week of Mein Bereich → Verfügbarkeit and of a
 * person's page), a time range is marked in the day columns: dragged with the mouse or a pen, or – on a phone, where
 * a finger scrolls – by tapping its start and then its end (a mouse can do that too). Over several days the range is
 * the same hours on each day, as the form below enters it ("with times the colour applies on each of the days").
 * The marked range is shown in the columns; the form [data-avail-form] gets the first and last day and the times
 * (00:00–24:00 means whole days), its line [data-avail-selection] says in words what was marked, and the buttons of
 * the colours come into view. The form stays the way for the keyboard: its date and time fields can be typed in.
 * Steps: 15 minutes with a mouse or pen, 30 minutes with a finger. A deployment in a column stays a link.
 */
(function () {
  "use strict";

  var THRESHOLD = 4;

  function pad(number) { return (number < 10 ? "0" : "") + number; }
  function clock(minutes) { return Math.floor(minutes / 60) + ":" + pad(minutes % 60); }
  function field(minutes) { return pad(Math.floor(minutes / 60) % 24) + ":" + pad(minutes % 60); }
  function fill(template, values) {
    return (template || "").replace(/\{(\w+)\}/g, function (all, name) {
      return Object.prototype.hasOwnProperty.call(values, name) ? values[name] : all;
    });
  }

  function setUp(grid) {
    var container = grid.closest(".panel-body") || grid.parentElement;
    var form = container ? container.querySelector("[data-avail-form]") : null;
    if (!form) { return; }
    var columns = Array.prototype.slice.call(grid.querySelectorAll(".wk-col[data-day]"));
    if (!columns.length) { return; }
    var inputs = {
      first: form.querySelector('input[name="start_day"]'),
      last: form.querySelector('input[name="end_day"]'),
      withTimes: form.querySelector('input[name="with_times"]'),
      start: form.querySelector('input[name="start_time"]'),
      end: form.querySelector('input[name="end_time"]')
    };
    if (!inputs.first || !inputs.last) { return; }
    var said = form.querySelector("[data-avail-selection]");
    var buttons = form.querySelector(".avail-buttons");
    var press = null;     // the pointer that is down: where, and whether it drags
    var anchor = null;    // the start tapped first, waiting for the end
    var marked = false;   // the form holds a range marked here
    var filling = false;

    function columnAt(x) {
      for (var index = 0; index < columns.length; index += 1) {
        var box = columns[index].getBoundingClientRect();
        if (x < box.right || index === columns.length - 1) { return index; }
      }
      return columns.length - 1;
    }

    // The cell of `step` minutes under the pointer: its index from midnight.
    function cellAt(column, y, step) {
      var box = columns[column].getBoundingClientRect();
      var minutes = (y - box.top) / box.height * 1440;
      return Math.max(0, Math.min(1440 / step - 1, Math.floor(minutes / step)));
    }

    function range(from, to) {
      var step = from.step;
      return {
        firstDay: Math.min(from.column, to.column),
        lastDay: Math.max(from.column, to.column),
        start: Math.min(from.cell, to.cell) * step,
        end: (Math.max(from.cell, to.cell) + 1) * step
      };
    }

    function clear() {
      grid.querySelectorAll(".wk-select").forEach(function (box) { box.remove(); });
    }

    function show(chosen) {
      clear();
      for (var index = chosen.firstDay; index <= chosen.lastDay; index += 1) {
        var box = document.createElement("div");
        box.className = "wk-select";
        box.setAttribute("aria-hidden", "true");
        box.style.setProperty("--start", (chosen.start / 60).toFixed(3));
        box.style.setProperty("--length", ((chosen.end - chosen.start) / 60).toFixed(3));
        if (index === chosen.firstDay) {
          var label = document.createElement("span");
          label.className = "wk-select-label";
          label.textContent = clock(chosen.start) + "–" + clock(chosen.end);
          box.appendChild(label);
        }
        columns[index].appendChild(box);
      }
    }

    function dayName(index) { return columns[index].getAttribute("aria-label") || columns[index].dataset.day; }
    function clockText(minutes) { return fill(grid.dataset.textClock || "{time}", { time: clock(minutes) }); }

    function set(input, value) {
      if (!input || input.value === value) { return; }
      input.value = value;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }

    // The marked range into the form, and in words.
    function take(chosen) {
      var whole = chosen.start === 0 && chosen.end === 1440;
      filling = true;
      set(inputs.first, columns[chosen.firstDay].dataset.day);
      set(inputs.last, columns[chosen.lastDay].dataset.day);
      if (inputs.withTimes && inputs.withTimes.checked === whole) {
        inputs.withTimes.checked = !whole;
        inputs.withTimes.dispatchEvent(new Event("change", { bubbles: true }));
      }
      if (!whole) {
        set(inputs.start, field(chosen.start));
        set(inputs.end, field(chosen.end));
      }
      filling = false;
      marked = true;
      var values = {
        first: dayName(chosen.firstDay), last: dayName(chosen.lastDay),
        start: clock(chosen.start), end: clockText(chosen.end)
      };
      var one = chosen.firstDay === chosen.lastDay;
      var key = whole ? (one ? "textWholeDay" : "textWholeDays") : (one ? "textDay" : "textDays");
      if (said) { said.textContent = fill(grid.dataset[key], values) + " " + (grid.dataset.textThen || ""); }
      if (buttons && buttons.scrollIntoView) { buttons.scrollIntoView({ block: "nearest", behavior: "smooth" }); }
    }

    grid.addEventListener("pointerdown", function (event) {
      if (event.button !== 0 || event.target.closest("a, button")) { return; }
      var column = columns.indexOf(event.target.closest(".wk-col"));
      if (column < 0) { return; }
      var step = event.pointerType === "touch" ? 30 : 15;
      press = { id: event.pointerId, x: event.clientX, y: event.clientY, touch: event.pointerType === "touch",
        dragging: false, from: { column: column, cell: cellAt(column, event.clientY, step), step: step } };
    });

    grid.addEventListener("pointermove", function (event) {
      if (!press || press.touch || event.pointerId !== press.id) { return; }
      if (!press.dragging) {
        if (Math.abs(event.clientX - press.x) + Math.abs(event.clientY - press.y) < THRESHOLD) { return; }
        press.dragging = true;
        anchor = null;
        grid.classList.add("is-marking");
        try { grid.setPointerCapture(event.pointerId); } catch (error) { /* the pointer is gone already */ }
      }
      event.preventDefault();
      var column = columnAt(event.clientX);
      show(range(press.from, { column: column, cell: cellAt(column, event.clientY, press.from.step) }));
    });

    grid.addEventListener("pointerup", function (event) {
      if (!press || event.pointerId !== press.id) { return; }
      var done = press;
      press = null;
      grid.classList.remove("is-marking");
      if (done.dragging) {
        var column = columnAt(event.clientX);
        take(range(done.from, { column: column, cell: cellAt(column, event.clientY, done.from.step) }));
        return;
      }
      // A finger that moved scrolled the week; it marks nothing.
      if (Math.abs(event.clientX - done.x) + Math.abs(event.clientY - done.y) >= 10) { return; }
      if (!anchor || anchor.step !== done.from.step) {
        anchor = done.from;
        var first = range(anchor, anchor);
        show(first);
        if (said) {
          said.textContent = fill(grid.dataset.textAnchor, { first: dayName(anchor.column), start: clockText(first.start) });
        }
        return;
      }
      var chosen = range(anchor, done.from);
      anchor = null;
      show(chosen);
      take(chosen);
    });

    grid.addEventListener("pointercancel", function () {
      press = null;
      grid.classList.remove("is-marking");
    });

    // Typed in the form or days chosen at their heads: the marked range no longer holds.
    form.addEventListener("change", function (event) {
      if (filling || !marked || !event.target.matches("input")) { return; }
      if (event.target.name === "note" || event.target.name === "with_times") { return; }
      marked = false;
      anchor = null;
      clear();
      if (said) { said.textContent = ""; }
    });
    grid.addEventListener("click", function (event) {
      if (!event.target.closest("[data-avail-day]") || !marked) { return; }
      marked = false;
      anchor = null;
      clear();
      if (said) { said.textContent = ""; }
      // A day head means whole days again.
      if (inputs.withTimes && inputs.withTimes.checked) {
        inputs.withTimes.checked = false;
        inputs.withTimes.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
  }

  document.querySelectorAll("[data-avail-select]").forEach(setUp);
})();

/* ==== ZEI-026: "In Zwischenablage kopieren" at approved times ==================================== */
// <button data-copy-block="…"> copies its text – tabs and line breaks included – and says "Kopiert" to screen
// readers through the nearest [data-copy-status]. Without navigator.clipboard (a page over plain http) a hidden
// text area and execCommand("copy") do it.
(function () {
  "use strict";

  function fallbackCopy(text) {
    var area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.top = "-1000px";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    var done = false;
    try { done = document.execCommand("copy"); } catch (error) { done = false; }
    document.body.removeChild(area);
    return done;
  }

  function copied(button, done) {
    var region = button.closest("[data-copy-scope], #my-times, main") || document;
    var status = region.querySelector("[data-copy-status]") || document.querySelector("[data-copy-status]");
    var text = done ? (button.dataset.copiedText || "Copied") : (button.dataset.failedText || "Copying failed");
    if (status) {
      status.textContent = "";
      window.setTimeout(function () { status.textContent = text; }, 50);
    }
    if (done) {
      button.classList.add("copied");
      window.setTimeout(function () { button.classList.remove("copied"); }, 900);
    }
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-copy-block]");
    if (!button) { return; }
    var text = button.dataset.copyBlock;
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(
        function () { copied(button, true); },
        function () { copied(button, fallbackCopy(text)); }
      );
    } else {
      copied(button, fallbackCopy(text));
    }
  });
})();

/* ==== PER-040: lists of rows that grow and change their order – Einstellungen → Zuschläge ============ */
// <div data-formset="rules" data-up-label="…" data-down-label="…" data-moved-label="… {place}"> holds
// <div data-formset-rows> with one [data-formset-row] each, a <template data-formset-empty> with the empty row of
// Django's formset (its names hold "__prefix__") and <button data-formset-add="rules" hidden>. The management form
// (<input name="rules-TOTAL_FORMS">) counts the rows. Without the script the page offers one empty row and the
// order as numbers; with it, "add" appends a row and two buttons move a row up or down (the numbers follow).
(function () {
  "use strict";

  function setUp(box) {
    var prefix = box.dataset.formset;
    var form = box.closest("form");
    var total = form && form.querySelector('[name="' + prefix + '-TOTAL_FORMS"]');
    var rows = box.querySelector("[data-formset-rows]");
    var template = box.querySelector("template[data-formset-empty]");
    var add = box.querySelector("[data-formset-add]");
    if (!rows) { return; }
    var live = document.createElement("p");
    live.className = "visually-hidden";
    live.setAttribute("aria-live", "polite");
    box.appendChild(live);

    function allRows() { return Array.prototype.slice.call(rows.querySelectorAll("[data-formset-row]")); }

    function renumber() {
      allRows().forEach(function (row, index) {
        var input = row.querySelector("[data-surcharge-order]");
        if (input) { input.value = String(index + 1); }
      });
    }

    function move(row, step, button) {
      var other = step < 0 ? row.previousElementSibling : row.nextElementSibling;
      if (!other) { return; }
      rows.insertBefore(row, step < 0 ? other : other.nextElementSibling);
      renumber();
      button.focus();
      var place = allRows().indexOf(row) + 1;
      live.textContent = (box.dataset.movedLabel || "{place}").replace("{place}", String(place));
    }

    function button(label, text, onClick) {
      var element = document.createElement("button");
      element.type = "button";
      element.className = "btn secondary small";
      element.setAttribute("aria-label", label);
      element.title = label;
      element.textContent = text;
      element.addEventListener("click", onClick);
      return element;
    }

    function setUpOrder(row) {
      var input = row.querySelector("[data-surcharge-order]");
      if (!input || input.dataset.ready) { return; }
      input.dataset.ready = "1";
      var field = input.closest(".field");
      var group = document.createElement("div");
      group.className = "rule-order";
      group.setAttribute("role", "group");
      group.setAttribute("aria-label", box.dataset.orderLabel || "");
      var up = button(box.dataset.upLabel || "↑", "↑", function () { move(row, -1, up); });
      var down = button(box.dataset.downLabel || "↓", "↓", function () { move(row, 1, down); });
      input.type = "hidden";
      group.appendChild(input);
      group.appendChild(up);
      group.appendChild(down);
      if (field) { field.replaceWith(group); } else { input.parentNode.appendChild(group); }
    }

    allRows().forEach(setUpOrder);
    if (add && total && template) {
      add.hidden = false;
      add.addEventListener("click", function () {
        var index = parseInt(total.value, 10) || 0;
        var holder = document.createElement("div");
        holder.innerHTML = template.innerHTML.replace(/__prefix__/g, String(index));
        var row = holder.querySelector("[data-formset-row]");
        if (!row) { return; }
        rows.appendChild(row);
        total.value = String(index + 1);
        var order = row.querySelector("[data-surcharge-order]");
        if (order) { order.value = String(allRows().length); }
        setUpOrder(row);
        var kind = row.querySelector('select[name$="-kind"]');
        if (kind) { kind.dispatchEvent(new Event("change", { bubbles: true })); }
        var first = row.querySelector("input:not([type=hidden]), select");
        if (first) { first.focus(); }
      });
    }
  }

  document.querySelectorAll("[data-formset]").forEach(setUp);
})();

/* ==== PRJ-112: the status of a service case =========================
 * "Waiting", "Waiting to close" and "Backlog" open the follow-up dialog; the
 * status is saved only with it. Closing the dialog without saving puts the
 * list of statuses on the page back to the status the case has.
 *
 * Choosing one of them opens the dialog right away: with
 * the mouse or a phone's picker on "change". The arrow keys change a closed
 * list step by step, so a change by keyboard waits for Enter or for the list
 * to lose the focus – no dialog on every step. "Status setzen" stays for the
 * other statuses and without the page script.
 */
(function () {
  "use strict";
  var dialog = document.getElementById("dialog");
  if (!dialog) { return; }
  dialog.addEventListener("close", function () {
    document.querySelectorAll(".case-status-form").forEach(function (form) { form.reset(); });
  });

  var STEP_KEYS = ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End", "PageUp", "PageDown"];
  document.querySelectorAll(".case-status-form[data-follow-up-statuses]").forEach(function (form) {
    var select = form.querySelector("select");
    if (!select) { return; }
    var needed = form.dataset.followUpStatuses.split(",");
    var byKeyboard = false;
    var wantsDialog = function () {
      return needed.indexOf(select.value) >= 0 && select.value !== form.dataset.saved;
    };
    var openDialog = function () {
      byKeyboard = false;
      if (!wantsDialog() || dialog.open) { return; }
      if (form.requestSubmit) { form.requestSubmit(); } else { form.dispatchEvent(new Event("submit", { cancelable: true })); }
    };
    select.addEventListener("keydown", function (event) {
      if (event.key === "Enter" && wantsDialog()) {
        event.preventDefault();
        openDialog();
      } else if (STEP_KEYS.indexOf(event.key) >= 0 || event.key.length === 1) {
        byKeyboard = true;  // typing a letter jumps to an entry as well
      }
    });
    select.addEventListener("change", function () { if (!byKeyboard) { openDialog(); } });
    select.addEventListener("blur", function () { if (byKeyboard) { openDialog(); } });
  });
})();

/* ==== ADM-017: take the reply draft by AI over into the text of the mail ====
 * The draft goes above what the text holds already – when answering, the quoted mail stays below it.
 * The button names the text field in aria-controls; the draft is the read-only field it names.
 */
(function () {
  "use strict";
  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-ai-take-draft]");
    if (!button) { return; }
    var source = document.getElementById(button.getAttribute("data-ai-take-draft"));
    var target = document.getElementById(button.getAttribute("aria-controls"));
    if (!source || !target) { return; }
    var draft = source.value.trim();
    var current = target.value.replace(/^\s+/, "");
    // KND-004: the draft starts with the greeting the text starts with already (the form puts it there, the model is told
    // to use it): the greeting of the text goes, so that the mail greets once.
    var greeting = draft.split("\n", 1)[0].trim();
    if (greeting && current.split("\n", 1)[0].trim() === greeting) { current = current.replace(/^[^\n]*\n?\s*/, ""); }
    target.value = current ? draft + "\n\n" + current : draft;
    target.dispatchEvent(new Event("input", { bubbles: true }));
    target.focus();
    if (target.setSelectionRange) { target.setSelectionRange(0, 0); }
    target.scrollTop = 0;
    var status = document.querySelector("[data-ai-draft-status]");
    if (status) { status.textContent = button.getAttribute("data-text-taken") || ""; }
  });
})();

/* ==== UIX-045: on the phone the menu slides in from the right, as in the companion app ===============
 * Only while the window is as narrow as the top bar with the menu button (up to 900 px, the breakpoint of the style
 * sheet); above it nothing here listens to touches and the side navigation stays as it is. body.nav-open stays the
 * one switch – the menu button, the magnifier and "/" set it as before; this block adds what goes with it:
 *  - the page behind becomes inert, so focus stays in the menu (Tab wraps round); on closing the focus goes back to
 *    the button that opened it;
 *  - Escape, the close button and a tap beside the menu close it; so does the browser's Back: while the menu is
 *    open there is a history entry for it, and a link in the menu replaces that entry, so that Back from the next
 *    page leads back here and not to the same page with the menu;
 *  - swiping from right to left anywhere on the page opens it – not where the touch starts on something that scrolls
 *    sideways or handles its own gestures (a timeline, a wide table, a map, a slider, a drag handle). The menu follows
 *    the finger (body.nav-dragging) and on release opens or closes by the speed of the swipe, else by whether it is
 *    more than half out; the rest of the way takes the part of the 220 ms that is left. Swiping it back closes it.
 *  - crossing the breakpoint while it is open closes it at once.
 */
(function () {
  "use strict";
  var body = document.body;
  var root = document.documentElement;
  var drawer = document.getElementById("sidebar");
  var scrim = document.querySelector(".nav-scrim");
  if (!drawer || !scrim || !window.matchMedia) { return; }
  var phone = window.matchMedia("(max-width: 900px)");
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  var DURATION = 220;  // ms for the whole way, as in the app
  var FLING = 0.4;  // px per ms: a swipe at least this fast decides by its direction alone
  var SLOP = 10;  // px a finger moves before it counts as a swipe
  var OWN_GESTURES = "input[type=range], [contenteditable], dialog[open], [data-tl-move], [data-avail-select], .drag, .group-drag, .leaflet-container, [data-no-swipe]";
  var opener = null;
  var poppedClose = false;
  var leaving = false;
  var noClickUntil = 0;
  var gesture = null;
  var wasOpen = body.classList.contains("nav-open");

  function isOpen() { return body.classList.contains("nav-open"); }
  function menuButton() { return document.querySelector("[data-toggle-nav]"); }
  function close() { body.classList.remove("nav-open"); }
  function hasEntry() { return Boolean(window.history.state && window.history.state.rentalarsNav); }
  function outside() { return Array.prototype.slice.call(document.querySelectorAll(".skip-link, .topbar, .main, #changed-note")); }
  function focusables() {
    return Array.prototype.filter.call(
      drawer.querySelectorAll("a[href], button:not([disabled]), input:not([disabled]):not([type=hidden]), select, textarea"),
      function (element) { return element.offsetParent !== null && !element.closest(".hidden"); }
    );
  }

  // Coming back to the entry of an open menu (a reload while it was open): the menu is closed now.
  if (hasEntry()) { window.history.replaceState(null, ""); }

  function opened() {
    outside().forEach(function (element) { element.inert = true; });
    var button = menuButton();
    if (button) { button.setAttribute("aria-expanded", "true"); }
    if (!opener) { opener = button; }
    if (!hasEntry()) {
      try { window.history.pushState({ rentalarsNav: true }, ""); } catch (error) { /* history not available */ }
    }
    if (!drawer.contains(document.activeElement)) {
      var first = drawer.querySelector(".nav-close") || focusables()[0];
      if (first) { first.focus({ preventScroll: true }); }
    }
  }

  function closed() {
    outside().forEach(function (element) { element.inert = false; });
    var button = menuButton();
    if (button) { button.setAttribute("aria-expanded", "false"); }
    if (!poppedClose && !leaving && hasEntry()) { window.history.back(); }
    poppedClose = false;
    var back = opener;
    opener = null;
    var active = document.activeElement;
    if (!leaving && phone.matches && back && (!active || active === body || drawer.contains(active))) {
      back.focus({ preventScroll: true });
    }
  }

  new MutationObserver(function () {
    var now = isOpen();
    if (now === wasOpen) { return; }
    wasOpen = now;
    if (now) { opened(); } else { closed(); }
  }).observe(body, { attributes: true, attributeFilter: ["class"] });

  window.addEventListener("popstate", function (event) {
    if (isOpen() && !(event.state && event.state.rentalarsNav)) {
      poppedClose = true;
      close();
    }
  });

  document.addEventListener("click", function (event) {
    if (Date.now() < noClickUntil) {  // the end of a swipe is no tap
      noClickUntil = 0;
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    var trigger = event.target.closest("[data-toggle-nav], [data-open-search]");
    if (trigger && !isOpen()) { opener = trigger; }
    if (event.target.closest("[data-close-nav]")) {
      event.preventDefault();
      close();
      return;
    }
    if (!isOpen()) { return; }
    var link = event.target.closest("a[href]");
    if (!link || !drawer.contains(link)) { return; }
    if (link.hasAttribute("hx-get")) { close(); return; }  // "Zeit erfassen" opens its dialog over the page
    var plain = event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey;
    if (plain && hasEntry() && !link.target && !link.hasAttribute("download") && link.origin === window.location.origin) {
      event.preventDefault();
      leaving = true;
      window.location.replace(link.href);
    }
  }, true);

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!isOpen() || !drawer.contains(form)) { return; }
    leaving = true;
    if ((form.method || "get").toLowerCase() === "get" && hasEntry()) {
      event.preventDefault();
      var query = new URLSearchParams(new FormData(form)).toString();
      window.location.replace(form.action.split("?")[0] + (query ? "?" + query : ""));
    }
  }, true);

  document.addEventListener("keydown", function (event) {
    if (!isOpen()) { return; }
    if (event.key === "Escape") {
      event.preventDefault();
      close();
    } else if (event.key === "Tab") {
      var items = focusables();
      if (!items.length) { return; }
      var first = items[0];
      var last = items[items.length - 1];
      var inside = drawer.contains(document.activeElement);
      if (event.shiftKey && (!inside || document.activeElement === first)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (!inside || document.activeElement === last)) {
        event.preventDefault();
        first.focus();
      }
    }
  });

  // --- Swiping ---------------------------------------------------------------------------------------------

  function handlesItsOwnGestures(element) {
    if (element.closest(OWN_GESTURES)) { return true; }
    for (var node = element; node && node !== body && node !== root; node = node.parentElement) {
      var style = window.getComputedStyle(node);
      if ((style.overflowX === "auto" || style.overflowX === "scroll") && node.scrollWidth > node.clientWidth + 1) { return true; }
      if (style.touchAction && style.touchAction !== "auto" && style.touchAction !== "manipulation") { return true; }
    }
    return false;
  }

  function show(offset, full) {
    drawer.style.transform = "translateX(" + offset + "px)";
    scrim.style.opacity = String(Math.max(0, Math.min(1, 1 - offset / full)));
  }

  function speedOf(samples) {
    var last = samples[samples.length - 1];
    for (var index = 0; index < samples.length - 1; index += 1) {
      var time = last[1] - samples[index][1];
      if (time > 0 && time <= 100) { return (last[0] - samples[index][0]) / time; }
    }
    return 0;
  }

  function settle(open, offset, full) {
    var left = open ? offset / full : 1 - offset / full;
    root.style.setProperty("--nav-duration", (reduced.matches ? 0 : Math.round(DURATION * left)) + "ms");
    body.classList.remove("nav-dragging");
    drawer.style.transform = "";
    scrim.style.opacity = "";
    if (open && !isOpen()) {
      opener = menuButton();
      body.classList.add("nav-open");
    } else if (!open && isOpen()) {
      close();
    }
    window.setTimeout(function () { root.style.removeProperty("--nav-duration"); }, DURATION + 50);
  }

  function onStart(event) {
    gesture = null;
    if (event.touches.length !== 1 || !(event.target instanceof Element)) { return; }
    var open = isOpen();
    var target = event.target;
    if (open ? !drawer.contains(target) && target !== scrim : handlesItsOwnGestures(target)) { return; }
    if (!open && document.querySelector("dialog[open]")) { return; }
    var touch = event.touches[0];
    var full = drawer.getBoundingClientRect().width || 300;
    gesture = {
      open: open, x: touch.clientX, y: touch.clientY, dragging: false, full: full, offset: open ? 0 : full,
      samples: [[touch.clientX, event.timeStamp]],
    };
  }

  function onMove(event) {
    if (!gesture) { return; }
    if (event.touches.length !== 1) { gesture = null; return; }
    var touch = event.touches[0];
    var dx = touch.clientX - gesture.x;
    var dy = touch.clientY - gesture.y;
    if (!gesture.dragging) {
      if (Math.abs(dx) < SLOP && Math.abs(dy) < SLOP) { return; }
      // Up and down scrolls; only a sideways swipe towards the menu's goal moves it.
      if (Math.abs(dy) >= Math.abs(dx) || (gesture.open ? dx < 0 : dx > 0)) { gesture = null; return; }
      gesture.dragging = true;
      body.classList.add("nav-dragging");
    }
    if (event.cancelable) { event.preventDefault(); }
    gesture.offset = Math.max(0, Math.min(gesture.full, (gesture.open ? 0 : gesture.full) + dx));
    show(gesture.offset, gesture.full);
    gesture.samples.push([touch.clientX, event.timeStamp]);
    if (gesture.samples.length > 6) { gesture.samples.shift(); }
  }

  function onEnd(event) {
    var done = gesture;
    gesture = null;
    if (!done || !done.dragging) { return; }
    noClickUntil = Date.now() + 400;
    // The release counts as a last sample where the finger was: a finger that rested before letting go did not fling.
    done.samples.push([done.samples[done.samples.length - 1][0], event.timeStamp]);
    var speed = speedOf(done.samples);
    var open = Math.abs(speed) >= FLING ? speed < 0 : done.offset < done.full / 2;
    settle(event.type === "touchcancel" ? done.open : open, done.offset, done.full);
  }

  var listening = false;
  function listen(on) {
    if (on === listening) { return; }
    listening = on;
    var change = on ? "addEventListener" : "removeEventListener";
    document[change]("touchstart", onStart, { passive: true });
    document[change]("touchmove", onMove, { passive: false });
    document[change]("touchend", onEnd);
    document[change]("touchcancel", onEnd);
  }

  function onBreakpoint() {
    listen(phone.matches);
    if (phone.matches) { return; }
    gesture = null;
    if (isOpen() || body.classList.contains("nav-dragging")) {
      root.style.setProperty("--nav-duration", "0ms");
      body.classList.remove("nav-dragging");
      drawer.style.transform = "";
      scrim.style.opacity = "";
      close();
      window.setTimeout(function () { root.style.removeProperty("--nav-duration"); }, 50);
    }
  }
  if (phone.addEventListener) { phone.addEventListener("change", onBreakpoint); } else { phone.addListener(onBreakpoint); }
  listen(phone.matches);
})();

/* ==== EML-050: "Kurzüberblick ohne KI" stays as the reader left it while the block "Zusammenfassung" reloads
 * The short overview is folded when the page loads (the same in a project and a service case). While a summary is
 * written the block asks every three seconds and is replaced each time; whoever unfolded the overview meanwhile
 * keeps it unfolded.
 */
(function () {
  "use strict";
  var wasOpen = null;
  document.addEventListener("htmx:beforeSwap", function (event) {
    var target = event.detail && event.detail.target;
    if (!target || target.id !== "ai-summary") { return; }
    var details = target.querySelector("details.ai-overview");
    wasOpen = details ? details.open : null;
  });
  document.addEventListener("htmx:afterSwap", function () {
    if (wasOpen === null) { return; }
    var details = document.querySelector("#ai-summary details.ai-overview");
    if (details) { details.open = wasOpen; }
    wasOpen = null;
  });
})();

/* ==== LOG-017: the planned kilometres of a vehicle on a trip, suggested by the route service ==========
 * Where the operator set a route service up, the dialog of a vehicle on a trip has a button
 * data-route-suggest="…/logistics/route/<trip>/" next to the field named by data-route-target ("planned_km"). A
 * click asks the server, which answers {"km": "123.4"} or {"error": "…"}. The kilometres go into the field of the
 * same form – with a decimal comma in German, as the server shows decimals – and stay changeable; what happened is
 * read out in [data-route-status]. The dialog is swapped in by htmx, so the click is caught on the document.
 */
(function () {
  "use strict";
  var texts = document.body.dataset;

  function localNumber(value) {
    var text = String(value);
    return /^en/i.test(document.documentElement.lang || "") ? text : text.replace(".", ",");
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-route-suggest]");
    if (!button) { return; }
    event.preventDefault();
    if (button.getAttribute("aria-busy") === "true") { return; }
    var form = button.closest("form") || document;
    var name = button.dataset.routeTarget || "planned_km";
    var input = form.querySelector('[name="' + name + '"]') || form.querySelector('[name$="-' + name + '"]');
    var status = form.querySelector("[data-route-status]");
    function tell(text) {
      if (!status) { return; }
      status.textContent = "";  // the same text twice is read out again
      window.setTimeout(function () { status.textContent = text; }, 50);
    }
    button.setAttribute("aria-busy", "true");
    tell(texts.textRouteBusy || "Asking the route service …");
    fetch(button.dataset.routeSuggest, { headers: { "Accept": "application/json" }, credentials: "same-origin" })
      .then(function (response) {
        if (response.status === 403) { return { error: texts.textForbidden || "You do not have the right to do this." }; }
        return response.json().catch(function () { return {}; });
      })
      .then(function (data) {
        if (data && data.km !== undefined && data.km !== null && data.km !== "") {
          var km = localNumber(data.km);
          if (input) {
            input.value = km;
            input.dispatchEvent(new Event("input", { bubbles: true }));
            input.dispatchEvent(new Event("change", { bubbles: true }));
          }
          tell((texts.textRouteDone || "{km} km by the route – a suggestion you can change.").replace("{km}", km));
        } else {
          tell(data && data.error ? data.error : (texts.textError || "The request failed."));
        }
      })
      .catch(function () { tell(texts.textError || "The request failed."); })
      .then(function () { button.removeAttribute("aria-busy"); });
  });
})();

/* ==== MAT-060: a new supplier with its master data, from "new supplier" of a supplier field ==========
 * The supplier field of the forms for items (material/_name_typeahead.html) takes a name. Its suggestion "neuer
 * Händler" carries create_url (material:supplier_create): choosing it opens the supplier's master data in the
 * dialog of the page – or over the dialog the field stands in (PRJ-101) –, as "Neue Phase …" does (PRJ-094). Saved,
 * the answer "supplierCreated" names the supplier: its name goes into the field the dialog came from, and the form
 * keeps everything typed. A type-ahead that takes the supplier's ID gets it through "objectCreated" (PRJ-070).
 * Escape or "Abbrechen" leave the typed name in the field. Without the script there are no suggestions: a new name
 * creates the supplier with the form, as before (MAT-050).
 */
(function () {
  "use strict";

  var opener = null;

  // The field the dialog is opened from: the type-ahead announces it before the dialog loads. Once a dialog
  // closes – saved or not – it is forgotten, so that no later answer lands in it.
  document.addEventListener("typeaheadCreate", function (event) {
    opener = event.detail && event.detail.input ? event.detail.input : null;
  }, true);
  document.addEventListener("close", function (event) {
    var box = event.target;
    if (!box || box.tagName !== "DIALOG") { return; }
    opener = null;
    if (box.dataset.supplierLabelled) {
      box.removeAttribute("aria-labelledby");
      delete box.dataset.supplierLabelled;
    }
  }, true);

  // The dialog of the page is named by the heading of the supplier form while it shows it.
  document.body.addEventListener("htmx:afterSwap", function (event) {
    var box = event.detail ? event.detail.target : null;
    if (!box || box.tagName !== "DIALOG" || box.hasAttribute("aria-labelledby")) { return; }
    if (box.querySelector("#supplier-dialog-title")) {
      box.setAttribute("aria-labelledby", "supplier-dialog-title");
      box.dataset.supplierLabelled = "1";
    }
  });

  document.body.addEventListener("supplierCreated", function (event) {
    var supplier = event.detail && event.detail.value ? event.detail.value : event.detail;
    var input = opener;
    opener = null;
    if (!supplier || !supplier.name || !input || !document.body.contains(input)) { return; }
    // Only a field that is itself the value – the name – takes it here.
    if (!input.name) { return; }
    input.value = supplier.name;
    var root = input.closest("[data-typeahead]");
    var hidden = root ? root.querySelector("[data-typeahead-value]") : null;
    if (hidden && !hidden.name) { hidden.value = supplier.name; }
    input.dispatchEvent(new Event("change", { bubbles: true }));
    window.setTimeout(function () {
      if (!document.querySelector("dialog[open]")) { input.focus(); }
    }, 0);
  });
})();

/* ==== MAT-061: the rows of "Kauf einpflegen" ============================================================
 * The rows are a formset (data-formset="pos", see PER-040 above: "add a row" appends one). Here: the button "more
 * rows" – which sends the form without this script – gives way to "add a row"; the box "remove the row" becomes a
 * button that hides the row and ticks the box; a new row gets its type-aheads and serial number fields; a suggested
 * model (data-purchase-model) goes into the model field of its row with one click.
 */
(function () {
  "use strict";

  var box = document.querySelector("[data-purchase-positions]");
  if (!box) { return; }
  var rows = box.querySelector("[data-formset-rows]");
  var add = box.querySelector("[data-formset-add]");
  var more = box.querySelector("[data-purchase-more]");
  var live = document.createElement("p");
  live.className = "visually-hidden";
  live.setAttribute("aria-live", "polite");
  box.appendChild(live);
  if (more && add) { more.hidden = true; more.classList.add("hidden"); }

  function setUpRemove(row) {
    var holder = row.querySelector("[data-purchase-remove]");
    var check = holder ? holder.querySelector("input[type=checkbox]") : null;
    if (!check || holder.dataset.ready) { return; }
    holder.dataset.ready = "1";
    holder.hidden = true;
    var button = document.createElement("button");
    button.type = "button";
    button.className = "btn secondary small";
    button.textContent = box.dataset.removeLabel || "×";
    button.addEventListener("click", function () {
      check.checked = true;
      check.dispatchEvent(new Event("change", { bubbles: true }));  // MAT-075: the sum below follows
      row.hidden = true;
      live.textContent = box.dataset.removedLabel || "";
      if (add && !add.hidden) { add.focus(); }
    });
    holder.parentNode.appendChild(button);
  }

  rows.querySelectorAll("[data-formset-row]").forEach(setUpRemove);
  if (add) {
    // Runs after the general script appended the row.
    add.addEventListener("click", function () {
      var row = rows.lastElementChild;
      if (!row) { return; }
      setUpRemove(row);
      row.dispatchEvent(new CustomEvent("htmx:afterSettle", { bubbles: true, detail: {} }));
    });
  }

  box.addEventListener("click", function (event) {
    var choice = event.target.closest ? event.target.closest("[data-purchase-model]") : null;
    if (!choice) { return; }
    var row = choice.closest("[data-formset-row]");
    var input = row ? row.querySelector('input[name$="-model_name"]') : null;
    if (!input) { return; }
    input.value = choice.dataset.purchaseModel;
    input.dispatchEvent(new Event("change", { bubbles: true }));
    input.focus();
  });

  /* MAT-075: the sum of the positions, net and gross, follows what is typed; the server renders the
   * same block on every step (purchase_forms.purchase_sums). A price as typed ("1.072,50", "1072,50"; English
   * "1,072.50") times its pieces, a set once, a row without price as 0. Typed gross, the net sum adds each price net,
   * rounded to cents (what is stored); typed net, the gross sum is the net sum with the tax rate, rounded once. */
  var sum = document.querySelector("[data-purchase-sum]");
  var form = box.closest("form");
  if (!sum || !form) { return; }
  var english = /^en/i.test(document.documentElement.lang || "");
  var firstGroup = /^[1-9]\d{0,2}$/;

  function grouped(text, mark) {
    var groups = text.split(mark);
    if (groups.length < 2 || !firstGroup.test(groups[0])) { return false; }
    return groups.slice(1).every(function (group) { return /^\d{3}$/.test(group); });
  }

  // The reading of purchases.parse_amount: "1.072" is 1072 in German and 1.072 in English.
  function plainNumber(text) {
    var dots = (text.match(/\./g) || []).length, commas = (text.match(/,/g) || []).length;
    if (!dots && !commas) { return text; }
    if (dots && commas) {
      var point = text.lastIndexOf(".") > text.lastIndexOf(",") ? "." : ",";
      var at = text.lastIndexOf(point);
      var whole = text.slice(0, at), fraction = text.slice(at + 1), group = point === "." ? "," : ".";
      if (whole.indexOf(point) !== -1 || !fraction || !grouped(whole, group)) { return null; }
      return whole.split(group).join("") + "." + fraction;
    }
    var mark = dots ? "." : ",";
    var parts = text.split(mark);
    if (parts.length > 2) {
      if (grouped(text, mark)) { return parts.join(""); }
      var last = parts[parts.length - 1];
      if (last.length >= 1 && last.length <= 2 && grouped(parts.slice(0, -1).join(mark), mark)) {
        return parts.slice(0, -1).join("") + "." + last;
      }
      return null;
    }
    if (!parts[1]) { return null; }
    if (parts[1].length === 3 && firstGroup.test(parts[0]) && mark === (english ? "," : ".")) { return parts[0] + parts[1]; }
    return (parts[0] || "0") + "." + parts[1];
  }

  // A typed price in cents; null for none the form takes (more than two decimals, negative, 100 million or more).
  function cents(value) {
    var text = String(value || "").replace(/€|euros?|eur/gi, "").replace(/[\s   '’]/g, "")
      .replace(/[.,]-{1,2}$/, "").replace(/^\+/, "");
    if (!/^(?:\d[\d.,]*|[.,]\d+)$/.test(text) || text.length > 30) { return null; }
    var plain = plainNumber(text);
    if (plain === null || !/^\d+(?:\.\d{1,2})?$/.test(plain)) { return null; }
    var amount = Math.round(Number(plain) * 100);
    return amount < 10000000000 ? amount : null;
  }

  function format(amount) {
    var units = String(Math.floor(Math.abs(amount) / 100)).replace(/\B(?=(\d{3})+(?!\d))/g, english ? "," : ".");
    var rest = String(Math.abs(amount) % 100);
    var number = units + (english ? "." : ",") + (rest.length < 2 ? "0" + rest : rest);
    var sign = amount < 0 ? "-" : "";
    return english ? sign + "€" + number : sign + number + " €";
  }

  function taxRate() {
    var select = form.querySelector('[name="price_tax_rate"]');
    var number = parseFloat(String(select ? select.value : (sum.dataset.rate || "")).replace(",", "."));
    return isNaN(number) ? null : number;
  }

  function isEmptyRow(row) {
    return ["model_name", "manufacturer_name", "product_text", "unit_price", "serial_numbers", "article_number", "source"]
      .every(function (name) {
        var field = row.querySelector('[name$="-' + name + '"]');
        return !field || !String(field.value || "").trim();
      });
  }

  function update() {
    var prices = form.querySelector('[name="prices"]');
    var grossEntered = !!prices && prices.value === "gross";
    var rate = taxRate();
    var most = parseInt(sum.dataset.maxPieces, 10) || 500;
    var net = 0, gross = 0, unpriced = 0;
    rows.querySelectorAll("[data-formset-row]").forEach(function (row) {
      var removed = row.querySelector('input[name$="-DELETE"]');
      if (row.hidden || (removed && removed.checked) || isEmptyRow(row)) { return; }
      var price = cents((row.querySelector('[name$="-unit_price"]') || {}).value);
      if (price === null) { unpriced += 1; return; }
      var set = row.querySelector('input[name$="-price_for_set"]');
      var count = String((row.querySelector('[name$="-count"]') || {}).value || "").trim();
      var pieces = /^-?\d+$/.test(count) ? Math.max(1, Math.min(most, parseInt(count, 10))) : 1;
      if (set && set.checked) { pieces = 1; }
      if (grossEntered && rate !== null) {
        gross += price * pieces;
        net += Math.round(price * 100 / (100 + rate) + 1e-9) * pieces;
      } else {
        net += price * pieces;
      }
    });
    if (!grossEntered) { gross = rate === null ? null : Math.round(net * (100 + rate) / 100 + 1e-9); }
    sum.querySelector("[data-sum-net]").textContent = format(net);
    var grossPart = sum.querySelector("[data-sum-gross-part]");
    if (grossPart) {
      grossPart.hidden = gross === null;
      if (gross !== null) { sum.querySelector("[data-sum-gross]").textContent = format(gross); }
    }
    var rateText = sum.querySelector("[data-sum-rate]");
    if (rateText && rate !== null) { rateText.textContent = english ? String(rate) : String(rate).replace(".", ","); }
    var note = sum.querySelector("[data-sum-unpriced]");
    if (note) {
      note.hidden = !unpriced;
      note.textContent = ((unpriced === 1 ? sum.dataset.unpricedOne : sum.dataset.unpricedMany) || "").replace("{count}", String(unpriced));
    }
    var difference = sum.querySelector("[data-sum-difference]");
    if (difference) {
      var grossCompared = difference.dataset.compared === "gross";
      var invoice = parseFloat(grossCompared ? sum.dataset.invoiceGross : sum.dataset.invoiceNet);
      var ours = grossCompared ? gross : net;
      if (ours === null || isNaN(invoice)) { return; }
      var off = ours - Math.round(invoice * 100);
      difference.textContent = off ? (off > 0 ? "+" : "") + format(off) : (sum.dataset.sameLabel || "0");
      difference.className = off ? "purchase-sum-off" : "purchase-sum-ok";
    }
  }

  var waiting = null;
  function later() {
    window.clearTimeout(waiting);
    waiting = window.setTimeout(update, 250);
  }
  form.addEventListener("input", later);
  form.addEventListener("change", later);
})();

/* ---- PRJ-005 (event end; PRJ-127): "Veranstaltung bis" after "Material zurück bis" – a warning, no error ---- */
(function () {
  "use strict";
  // The project form: [data-event-warning] shows while the event ends after the rental period (fields "end", "event_end").
  document.querySelectorAll("[data-event-warning]").forEach(function (note) {
    var form = note.closest("form");
    if (!form) { return; }
    var end = form.querySelector('[name="end"]'), eventEnd = form.querySelector('[name="event_end"]');
    if (!end || !eventEnd) { return; }
    function update() {
      // Both fields hold "2027-03-10T14:15" (or a date, "2027-03-10"): the text compares like the moments.
      note.hidden = !(end.value && eventEnd.value && eventEnd.value > end.value);
    }
    ["input", "change"].forEach(function (name) { form.addEventListener(name, update); });
    update();
  });
})();

/* ==== Subgroup scroll: swapping the whole planning keeps the place on the page ========================
 * Saving a group (and copying, deleting, switching it to optional …) answers with the whole planning block, which
 * replaces the old one. The browser keeps the part of the page in view where it is (scroll anchoring): it moves the
 * page down by the height of the new block that is inserted above the old one, and when the old one is gone the page
 * ends up at the bottom – with a long planning the user had to scroll up again. So the place is noted before the swap
 * and put back after it, together with the open and closed state of the <details> in the block.
 */
(function () {
  "use strict";
  var noted = null;

  document.addEventListener("htmx:beforeSwap", function (event) {
    var target = event.detail && event.detail.target;
    if (!target || target.id !== "planning" || !target.querySelectorAll) { noted = null; return; }
    noted = {
      x: window.scrollX,
      y: window.scrollY,
      // (R3-10) by a stable name (data-keep), not by position: a line that moved or came
      // in between must not give its state to another one.
      details: {}
    };
    target.querySelectorAll("details[data-keep]").forEach(function (element) {
      noted.details[element.dataset.keep] = element.open;
    });
  });

  function putBack() {
    if (!noted) { return; }
    var planning = document.getElementById("planning");
    if (planning) {
      planning.querySelectorAll("details[data-keep]").forEach(function (element) {
        if (Object.prototype.hasOwnProperty.call(noted.details, element.dataset.keep)) {
          element.open = noted.details[element.dataset.keep];
        }
      });
    }
    window.scrollTo(noted.x, noted.y);
  }

  document.addEventListener("htmx:afterSwap", function (event) {
    var target = event.detail && event.detail.target;
    if (noted && target && target.id === "planning") {
      putBack();
      // Content that arrives right after (the hints above the lines) must not move the place either.
      window.requestAnimationFrame(putBack);
      window.setTimeout(function () { putBack(); noted = null; }, 60);
    }
  });
})();

/* ==== The suggestions of the planning are announced only when their number changes ========
 * The panel is swapped after every change of the planning; a live region around it would read it out each time. The
 * panel carries its number and a sentence ([data-suggestion-count], [data-suggestion-text]); a status line outside
 * of it ([data-suggestion-status]) is written to when the number is not the one the panel showed before.
 */
(function () {
  "use strict";
  var shown = {};

  document.addEventListener("htmx:afterSwap", function (event) {
    var target = event.detail && event.detail.target;
    if (!target || !target.id || target.id.indexOf("suggestions") !== 0 || !target.querySelector) { return; }
    var marker = target.querySelector("[data-suggestion-count]");
    var status = document.querySelector("[data-suggestion-status]");
    if (!marker) { return; }
    var count = marker.dataset.suggestionCount;
    if (status && shown[target.id] !== undefined && shown[target.id] !== count) {
      status.textContent = "";
      window.setTimeout(function () { status.textContent = marker.dataset.suggestionText || ""; }, 100);
    }
    shown[target.id] = count;
  });
})();
