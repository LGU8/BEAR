/* static/js/settings/settings_s4.js */
(function () {
  const form = document.getElementById("s4Form");
  if (!form) return;

  const hidActivity = document.getElementById("hidActivity");
  const hidPurpose = document.getElementById("hidPurpose");
  const saveBtn = document.getElementById("saveBtn");

  const activityBtns = Array.from(document.querySelectorAll(".js-activity"));
  const purposeBtns = Array.from(document.querySelectorAll(".js-purpose"));

  // kcal preview
  const kcalTargetEl = document.getElementById("kcalTarget");
  const tdeeJsonScriptEl = document.getElementById("tdeeByLevelJson"); // json_script id

  const initial = {
    activity: (hidActivity?.value || "").trim(),
    purpose: (hidPurpose?.value || "").trim(),
  };
  const state = { ...initial };

  function setActive(btns, value) {
    btns.forEach((b) => {
      const on = String(b.dataset.value || "") === String(value || "");
      b.classList.toggle("is-active", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function syncHidden() {
    if (hidActivity) hidActivity.value = String(state.activity || "");
    if (hidPurpose) hidPurpose.value = String(state.purpose || "");
  }

  function isChanged() {
    return String(state.activity || "") !== String(initial.activity || "")
        || String(state.purpose || "") !== String(initial.purpose || "");
  }

  function isValid() {
    return !!String(state.activity || "") && !!String(state.purpose || "");
  }

  function updateSave() {
    if (!saveBtn) return;
    saveBtn.disabled = !(isValid() && isChanged());
  }

  // -------------------------
  // kcal preview helpers
  // -------------------------
  function safeJsonParse(s) {
    try {
      return JSON.parse(s);
    } catch (e) {
      return {};
    }
  }

  const tdeeByLevel = safeJsonParse((tdeeJsonScriptEl?.textContent || "{}").trim());

  function purposeOffset(purpose) {
    const p = String(purpose || "");
    if (p === "1") return -400; // diet
    if (p === "3") return 400;  // bulkup
    return 0;                  // maintain or invalid
  }

  function clampMinTarget(v) {
    if (!Number.isFinite(v) || v <= 0) return 0;
    return Math.max(1200, Math.round(v));
  }

  function updateKcalPreview() {
    if (!kcalTargetEl) return;

    const lv = String(state.activity || "");
    const pu = String(state.purpose || "");

    const tdee = parseInt(tdeeByLevel[lv] ?? "0", 10) || 0;
    const off = purposeOffset(pu);
    const target = tdee > 0 ? clampMinTarget(tdee + off) : 0;

    kcalTargetEl.textContent = String(target);
  }

  // -------------------------
  // events
  // -------------------------
  activityBtns.forEach((btn) => {
    btn.setAttribute("aria-pressed", "false");
    btn.addEventListener("click", () => {
      const v = String(btn.dataset.value || "");
      if (!v) return;

      state.activity = v;

      setActive(activityBtns, state.activity);
      syncHidden();
      updateKcalPreview();
      updateSave();
    });
  });

  purposeBtns.forEach((btn) => {
    btn.setAttribute("aria-pressed", "false");
    btn.addEventListener("click", () => {
      const v = String(btn.dataset.value || "");
      if (!v) return;

      state.purpose = v;

      setActive(purposeBtns, state.purpose);
      syncHidden();
      updateKcalPreview();
      updateSave();
    });
  });

  // init
  setActive(activityBtns, state.activity);
  setActive(purposeBtns, state.purpose);
  syncHidden();
  updateKcalPreview();
  updateSave();

  form.addEventListener("submit", (e) => {
    if (!isValid() || !isChanged()) {
      e.preventDefault();
      updateSave();
    }
  });
})();