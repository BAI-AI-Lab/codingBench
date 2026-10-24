// Filters on the problem list, model tabs for code, copy buttons. Pages work without this script.
(function () {
  function pick(seg, btn) {
    seg.querySelectorAll("button").forEach(function (b) { b.setAttribute("aria-pressed", String(b === btn)); });
  }

  var filters = document.querySelectorAll("[data-filter]");
  function applyFilters() {
    var want = {};
    filters.forEach(function (seg) { want[seg.dataset.filter] = seg.querySelector('[aria-pressed="true"]').dataset.value; });
    document.querySelectorAll("#plist tbody tr").forEach(function (tr) {
      tr.hidden = Object.keys(want).some(function (k) { return want[k] !== "all" && tr.dataset[k] !== want[k]; });
    });
  }
  filters.forEach(function (seg) {
    seg.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (b) { pick(seg, b); applyFilters(); }
    });
  });
  document.querySelectorAll("#plist tbody tr[data-href]").forEach(function (tr) {
    tr.addEventListener("click", function (e) { if (!e.target.closest("a")) location.href = tr.dataset.href; });
  });

  document.querySelectorAll("[data-tabs]").forEach(function (seg) {
    var group = document.querySelectorAll('[data-panel-group="' + seg.dataset.tabs + '"]');
    seg.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      pick(seg, b);
      group.forEach(function (p) { p.hidden = p.dataset.panel !== b.dataset.value; });
    });
  });

  document.querySelectorAll(".copy").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var src = document.getElementById(btn.dataset.src);
      if (!src || !navigator.clipboard) return;
      var label = btn.dataset.label || (btn.dataset.label = btn.textContent);
      navigator.clipboard.writeText(src.innerText).then(function () {
        btn.textContent = "已复制";
        setTimeout(function () { btn.textContent = label; }, 1500);
      });
    });
  });
})();
