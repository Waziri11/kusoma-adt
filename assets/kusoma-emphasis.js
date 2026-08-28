/* Preserve the source-book bold words through i18n and Easy Read rewrites. */
(function () {
  var targets = {
    pg085_n0018: ["bidhaa"],
    pg086_n0004: ["bidhaa"],
    pg086_n0005: ["bidhaa", "thamani"],
    pg086_n0007: ["Thamani"],
    pg086_n0009: ["kuving’arisha", "kuving'arisha"]
  };

  function escaped(value) {
    return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function applyTo(element, words) {
    if (!element || element.querySelector("[data-word-index]")) return;
    var current = element.textContent || "";
    var pattern = new RegExp("(" + words.map(escaped).join("|") + ")", "giu");
    if (!pattern.test(current)) return;
    pattern.lastIndex = 0;
    var parts = current.split(pattern);
    var fragment = document.createDocumentFragment();
    parts.forEach(function (part) {
      if (!part) return;
      pattern.lastIndex = 0;
      if (pattern.test(part)) {
        var strong = document.createElement("strong");
        strong.className = "font-bold";
        strong.textContent = part;
        fragment.appendChild(strong);
      } else {
        fragment.appendChild(document.createTextNode(part));
      }
    });
    if (element.innerHTML !== "" && element.querySelector("strong") && element.textContent === current) {
      return;
    }
    element.replaceChildren(fragment);
  }

  function applyAll() {
    Object.keys(targets).forEach(function (id) {
      applyTo(document.querySelector('[data-id="' + id + '"]'), targets[id]);
    });
  }

  function start() {
    var content = document.getElementById("content");
    if (!content) return;
    var scheduled = false;
    var observer = new MutationObserver(function () {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(function () {
        scheduled = false;
        observer.disconnect();
        applyAll();
        observer.observe(content, { childList: true, characterData: true, subtree: true });
      });
    });
    applyAll();
    observer.observe(content, { childList: true, characterData: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
