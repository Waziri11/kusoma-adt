// Keep every device on one coherent ADT bundle while preserving user settings.
(function () {
  "use strict";

  var root = document.documentElement;
  var script = document.currentScript;
  var declaredVersion = "";
  var bookRootUrl = null;
  var revealTimer;
  var revealed = false;

  try {
    var scriptUrl = new URL(script && script.src ? script.src : location.href);
    declaredVersion = scriptUrl.searchParams.get("v") || "";
    bookRootUrl = new URL("../", scriptUrl);
  } catch (_) {}

  function reveal() {
    if (revealed) return;
    revealed = true;
    clearTimeout(revealTimer);
    root.style.removeProperty("visibility");
    root.removeAttribute("data-adt-release-checking");
  }

  function newestVersion(first, second) {
    if (!first) return second || "";
    if (!second) return first;
    if (/^\d+$/.test(first) && /^\d+$/.test(second)) {
      return Number(first) >= Number(second) ? first : second;
    }
    return first === second ? first : second;
  }

  async function clearLegacyReleaseData(version) {
    var previous = null;
    try {
      previous = localStorage.getItem("adtBundleVersion");
    } catch (_) {}
    if (previous === version) return;

    var tasks = [];
    if ("caches" in window && bookRootUrl) {
      tasks.push(
        caches.keys().then(function (keys) {
          return Promise.all(keys.map(async function (key) {
            var cache = await caches.open(key);
            var requests = await cache.keys();
            var bookRequests = requests.filter(function (request) {
              try {
                var requestUrl = new URL(request.url);
                return requestUrl.origin === bookRootUrl.origin &&
                  requestUrl.pathname.startsWith(bookRootUrl.pathname);
              } catch (_) {
                return false;
              }
            });
            await Promise.all(bookRequests.map(function (request) {
              return cache.delete(request);
            }));
            if ((await cache.keys()).length === 0) await caches.delete(key);
          }));
        })
      );
    }
    if (
      bookRootUrl &&
      "serviceWorker" in navigator &&
      navigator.serviceWorker.getRegistrations
    ) {
      tasks.push(
        navigator.serviceWorker.getRegistrations().then(function (registrations) {
          var bookRegistrations = registrations.filter(function (registration) {
            try {
              var scopeUrl = new URL(registration.scope);
              return scopeUrl.origin === bookRootUrl.origin &&
                scopeUrl.pathname.startsWith(bookRootUrl.pathname);
            } catch (_) {
              return false;
            }
          });
          return Promise.all(bookRegistrations.map(function (registration) {
            return registration.unregister();
          }));
        })
      );
    }
    await Promise.allSettled(tasks);
    try {
      localStorage.setItem("adtBundleVersion", version);
    } catch (_) {}
  }

  function reloadFor(version) {
    var page = new URL(location.href);
    if (page.searchParams.get("release") === version) {
      root.setAttribute("data-adt-release", version);
      reveal();
      return;
    }
    page.searchParams.set("release", version);
    page.searchParams.set("adt-refresh", Date.now().toString(36));
    location.replace(page.toString());
  }

  root.style.setProperty("visibility", "hidden", "important");
  root.setAttribute("data-adt-release-checking", "true");
  revealTimer = setTimeout(reveal, 4000);

  var manifestUrl;
  try {
    manifestUrl = new URL("./release.json", script.src);
  } catch (_) {
    reveal();
    return;
  }
  manifestUrl.searchParams.set("cache-bust", Date.now().toString(36));

  fetch(manifestUrl.toString(), {
    cache: "no-store",
    credentials: "same-origin",
    headers: { "Cache-Control": "no-cache" }
  })
    .then(function (response) {
      if (!response.ok) throw new Error("release manifest unavailable");
      return response.json();
    })
    .then(async function (manifest) {
      var liveVersion = String(manifest.bundleVersion || "");
      var targetVersion = newestVersion(declaredVersion, liveVersion);
      if (!targetVersion) {
        reveal();
        return;
      }
      await clearLegacyReleaseData(targetVersion);
      reloadFor(targetVersion);
    })
    .catch(function () {
      // Keep the cached book usable offline; consistency is rechecked online.
      if (declaredVersion) root.setAttribute("data-adt-release", declaredVersion);
      reveal();
    });
})();
