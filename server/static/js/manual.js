/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Manual chapters: an old address of the manual with an anchor – /manual/#7-projekte-planen, from before the
 * manual was split into pages – is forwarded to the page of its chapter, /manual/7/#7-projekte-planen. The browser
 * does not send the anchor to the server, so the table of contents asks for the list of anchors (it is cached) and
 * moves on – when the page opens with an anchor and when the anchor is changed on the open page. Without a script,
 * or for an anchor that is not known, the table of contents simply stays. */
(function () {
  var script = document.currentScript;
  if (!script) { return; }
  var known = null;
  function forward() {
    var hash = window.location.hash;
    if (hash.length < 2) { return; }
    var anchor;
    try { anchor = decodeURIComponent(hash.slice(1)); } catch (error) { return; }
    if (known === null) {
      known = fetch(script.dataset.anchors, { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(function (response) { return response.ok ? response.json() : {}; })
        .catch(function () { return {}; });
    }
    known.then(function (data) {
      var chapter = data && data.chapters && data.chapters[anchor];
      if (chapter) { window.location.replace(script.dataset.chapterBase + chapter + "/" + hash); }
    });
  }
  forward();
  window.addEventListener("hashchange", forward);
})();
