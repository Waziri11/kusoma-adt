(function () {
  "use strict";

  var MOBILE_QUERY = "(max-width: 767.98px)";
  var SHEET_SELECTOR = '[role="dialog"][data-slot="sheet-content"][data-side="bottom"]';
  var media = window.matchMedia(MOBILE_QUERY);
  var enhanced = new WeakSet();
  var scheduled = false;

  function resetSheet(sheet, animate) {
    sheet.style.transition = animate ? "transform 180ms ease-out, opacity 180ms ease-out" : "";
    sheet.style.transform = "translateY(0)";
    sheet.style.opacity = "1";
    sheet.removeAttribute("data-mobile-sheet-dragging");
    if (animate) {
      window.setTimeout(function () {
        if (!sheet.isConnected) return;
        sheet.style.transition = "";
        sheet.style.transform = "";
        sheet.style.opacity = "";
      }, 200);
    }
  }

  function requestNativeClose(sheet) {
    var event = new KeyboardEvent("keydown", {
      key: "Escape",
      code: "Escape",
      bubbles: true,
      cancelable: true
    });
    sheet.dispatchEvent(event);

    window.setTimeout(function () {
      if (!sheet.isConnected || !sheet.hasAttribute("data-open")) return;
      var id = sheet.id;
      var trigger = null;
      if (id) {
        var candidates = document.querySelectorAll('[aria-controls][aria-expanded="true"]');
        trigger = Array.prototype.find.call(candidates, function (candidate) {
          return candidate.getAttribute("aria-controls") === id;
        }) || null;
      }
      if (trigger) {
        trigger.click();
        return;
      }
      var overlay = document.querySelector('[data-slot="sheet-overlay"][data-open]');
      if (overlay) overlay.click();
    }, 120);
  }

  function dismissSheet(sheet) {
    var distance = Math.max(sheet.offsetHeight, window.innerHeight * 0.45);
    sheet.style.transition = "transform 180ms ease-in, opacity 180ms ease-in";
    sheet.style.transform = "translateY(" + distance + "px)";
    sheet.style.opacity = "0";
    window.setTimeout(function () {
      requestNativeClose(sheet);
    }, 150);
  }

  function enhanceSheet(sheet) {
    if (enhanced.has(sheet)) return;
    var handle = sheet.firstElementChild;
    if (!handle || handle.getAttribute("aria-hidden") !== "true") return;

    enhanced.add(sheet);
    sheet.setAttribute("data-mobile-sheet-draggable", "");
    handle.removeAttribute("aria-hidden");
    handle.setAttribute("role", "button");
    handle.setAttribute("tabindex", "0");
    handle.setAttribute("aria-label", "Vuta chini kufunga");
    handle.setAttribute("title", "Vuta chini kufunga");
    handle.setAttribute("data-mobile-sheet-drag-handle", "");

    var drag = null;

    function start(clientY, pointerId) {
      if (!media.matches) return;
      drag = {
        startY: clientY,
        lastY: clientY,
        startTime: performance.now(),
        pointerId: pointerId
      };
      sheet.setAttribute("data-mobile-sheet-dragging", "");
      sheet.style.transition = "none";
    }

    function move(clientY) {
      if (!drag) return;
      drag.lastY = clientY;
      var distance = Math.max(0, clientY - drag.startY);
      sheet.style.transform = "translateY(" + distance + "px)";
      sheet.style.opacity = String(Math.max(0.72, 1 - distance / Math.max(sheet.offsetHeight * 2, 1)));
    }

    function finish(clientY) {
      if (!drag) return;
      var endY = typeof clientY === "number" ? clientY : drag.lastY;
      var distance = Math.max(0, endY - drag.startY);
      var elapsed = Math.max(1, performance.now() - drag.startTime);
      var velocity = distance / elapsed;
      var threshold = Math.min(120, sheet.offsetHeight * 0.25);
      drag = null;
      sheet.removeAttribute("data-mobile-sheet-dragging");

      if (distance >= threshold || (distance >= 40 && velocity >= 0.55)) {
        dismissSheet(sheet);
      } else {
        resetSheet(sheet, true);
      }
    }

    handle.addEventListener("pointerdown", function (event) {
      if (!media.matches || (event.button !== undefined && event.button !== 0)) return;
      event.preventDefault();
      start(event.clientY, event.pointerId);
      if (typeof handle.setPointerCapture === "function") {
        try {
          handle.setPointerCapture(event.pointerId);
        } catch (_) {
          /* Older mobile browsers may not support pointer capture on a div. */
        }
      }
    });
    handle.addEventListener("pointermove", function (event) {
      if (!drag || drag.pointerId !== event.pointerId) return;
      event.preventDefault();
      move(event.clientY);
    });
    handle.addEventListener("pointerup", function (event) {
      if (!drag || drag.pointerId !== event.pointerId) return;
      event.preventDefault();
      finish(event.clientY);
    });
    handle.addEventListener("pointercancel", function () {
      if (!drag) return;
      drag = null;
      resetSheet(sheet, true);
    });
    handle.addEventListener("keydown", function (event) {
      if (!media.matches || (event.key !== "Enter" && event.key !== " ")) return;
      event.preventDefault();
      dismissSheet(sheet);
    });

    if (!window.PointerEvent) {
      handle.addEventListener("touchstart", function (event) {
        if (!media.matches || event.touches.length !== 1) return;
        event.preventDefault();
        start(event.touches[0].clientY, null);
      }, { passive: false });
      handle.addEventListener("touchmove", function (event) {
        if (!drag || event.touches.length !== 1) return;
        event.preventDefault();
        move(event.touches[0].clientY);
      }, { passive: false });
      handle.addEventListener("touchend", function (event) {
        if (!drag) return;
        event.preventDefault();
        var touch = event.changedTouches && event.changedTouches[0];
        finish(touch ? touch.clientY : drag.lastY);
      }, { passive: false });
      handle.addEventListener("touchcancel", function () {
        if (!drag) return;
        drag = null;
        resetSheet(sheet, true);
      }, { passive: false });
    }
  }

  function install() {
    scheduled = false;
    var sheets = document.querySelectorAll(SHEET_SELECTOR);
    Array.prototype.forEach.call(sheets, enhanceSheet);
    if (!media.matches) {
      Array.prototype.forEach.call(sheets, function (sheet) { resetSheet(sheet, false); });
    }
  }

  function scheduleInstall() {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(install);
  }

  var observer = new MutationObserver(scheduleInstall);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  if (typeof media.addEventListener === "function") media.addEventListener("change", scheduleInstall);
  else if (typeof media.addListener === "function") media.addListener(scheduleInstall);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scheduleInstall, { once: true });
  } else {
    scheduleInstall();
  }
})();
