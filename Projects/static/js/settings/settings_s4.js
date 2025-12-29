/* =========================
   settings_s4.js (FINAL)
   - 활동량/목표 단일 선택
   - hidden input 반영
   - 변경 시 저장 버튼 활성화
   - 유효성: activity & purpose 모두 선택
   - a11y: aria-pressed
   ========================= */

(function () {
  const form = document.getElementById("s4Form");
  if (!form) return;

  const hidActivity = document.getElementById("hidActivity");
  const hidPurpose = document.getElementById("hidPurpose");
  const saveBtn = document.getElementById("saveBtn");

  const activityBtns = Array.from(document.querySelectorAll(".js-activity"));
  const purposeBtns = Array.from(document.querySelectorAll(".js-purpose"));

  const initial = {
    activity: (hidActivity?.value || "").trim(),
    purpose: (hidPurpose?.value || "").trim(),
  };

  const state = { ...initial };

  function setActive(btns, value) {
    btns.forEach((b) => {
      const on = (b.dataset.value || "") === value;
      b.classList.toggle("is-active", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function syncHidden() {
    hidActivity.value = state.activity;
    hidPurpose.value = state.purpose;
  }

  function isChanged() {
    return state.activity !== initial.activity || state.purpose !== initial.purpose;
  }

  function isValid() {
    return !!state.activity && !!state.purpose;
  }

  function updateSave() {
    saveBtn.disabled = !(isValid() && isChanged());
  }

  activityBtns.forEach((btn) => {
    btn.setAttribute("aria-pressed", "false");
    btn.addEventListener("click", () => {
      const v = String(btn.dataset.value || "");
      if (!v) return;

      // 단일 선택 유지 (재클릭으로 해제 X)
      state.activity = v;

      setActive(activityBtns, state.activity);
      syncHidden();
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
      updateSave();
    });
  });

  // init
  setActive(activityBtns, state.activity);
  setActive(purposeBtns, state.purpose);
  syncHidden();
  updateSave();

  form.addEventListener("submit", (e) => {
    if (!isValid() || !isChanged()) {
      e.preventDefault();
      updateSave();
    }
  });
})();
