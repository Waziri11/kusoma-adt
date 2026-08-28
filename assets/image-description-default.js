/* Enable image narration once for existing and new readers of this book. */
(function () {
  var migrationKey = "kusomaImageDescriptionsV1";

  try {
    if (window.localStorage.getItem(migrationKey) !== "done") {
      window.localStorage.setItem("describeImagesMode", "true");
      window.localStorage.setItem(migrationKey, "done");
    }
  } catch (_) {
    var path = window.location.pathname.slice(0, window.location.pathname.lastIndexOf("/") + 1);
    document.cookie = "describeImagesMode=true; path=" + path;
  }
})();
