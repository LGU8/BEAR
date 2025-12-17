/* =========================
   settings_s4.js
   - 활동량/목표 선택 토글
   - hidden input에 값 반영
   - 변경 시 저장 버튼 활성화
   - 둘 중 하나라도 미선택이면 저장 비활성
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
    btns.forEach((b) => b.classList.toggle("is-active", b.dataset.value === value));
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
    saveBtn.disabled = !(isChanged() && isValid());
  }

  activityBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      state.activity = String(btn.dataset.value || "");
      setActive(activityBtns, state.activity);
      syncHidden();
      updateSave();
    });
  });

  purposeBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      state.purpose = String(btn.dataset.value || "");
      setActive(purposeBtns, state.purpose);
      syncHidden();
      updateSave();
    });
  });

  // init
  setActive(activityBtns, state.activity);
  setActive(purposeBtns, state.purpose);
  updateSave();

  form.addEventListener("submit", (e) => {
    if (!isValid()) {
      e.preventDefault();
      updateSave();
    }
  });
})();