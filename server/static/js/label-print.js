/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * MAT-056: the page of labels printed from the browser.
 *
 * The page has one label per printed page, each in its exact size (@page). Once the fonts and pictures are
 * there, the print dialog of the browser opens by itself (<body data-print-on-load>); "Drucken" opens it again.
 * The bar with the button and the hints is not printed.
 */
(function () {
  "use strict";

  function printNow() { window.print(); }

  document.addEventListener("click", function (event) {
    if (event.target.closest && event.target.closest("[data-print-now]")) { printNow(); }
  });

  if (document.body && document.body.hasAttribute("data-print-on-load")) {
    window.addEventListener("load", function () {
      var ready = document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
      ready.then(function () { window.setTimeout(printNow, 200); });
    });
  }
})();
