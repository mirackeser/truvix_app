/**
 * Shared behaviour for the Truvix web pages.
 *
 * Vanilla, no build step: these are three documents that must keep working
 * years after anybody last thought about them, and a toolchain is a thing that
 * rots. Everything here degrades to plain HTML if the script never runs.
 */

(function () {
  "use strict";

  var config = window.TRUVIX_SITE || {};

  /**
   * Fill every `data-site` placeholder with its configured value.
   *
   * A value that has not been filled in is marked rather than left blank, so a
   * document published with an empty company name says so instead of quietly
   * reading as though the field did not exist.
   */
  function applyConfig() {
    var nodes = document.querySelectorAll("[data-site]");
    Array.prototype.forEach.call(nodes, function (node) {
      var key = node.getAttribute("data-site");
      var value = config[key];
      if (value) {
        node.textContent = value;
        return;
      }
      node.textContent = "[" + key + " — yapılandırılmadı]";
      node.classList.add("unset");
    });
  }

  /** Render the last-updated date in Turkish. */
  function applyDate() {
    var nodes = document.querySelectorAll("[data-updated]");
    if (!nodes.length || !config.lastUpdated) {
      return;
    }
    var parsed = new Date(config.lastUpdated + "T00:00:00Z");
    var text = isNaN(parsed.getTime())
      ? config.lastUpdated
      : parsed.toLocaleDateString("tr-TR", {
          day: "numeric",
          month: "long",
          year: "numeric",
          timeZone: "UTC",
        });
    Array.prototype.forEach.call(nodes, function (node) {
      node.textContent = text;
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    applyConfig();
    applyDate();
  });

  window.TruvixSite = { config: config };
})();
