/* static/js/settings/settings_s5.js */

(function () {
  const form = document.getElementById("pwForm");
  if (!form) return;

  const curPw = document.getElementById("curPw");
  const newPw = document.getElementById("newPw");
  const newPw2 = document.getElementById("newPw2");
  const saveBtn = document.getElementById("saveBtn");
  const errBox = document.getElementById("pwError");

  function showError(msg) {
    if (!errBox) return;
    if (!msg) {
      errBox.textContent = "";
      errBox.classList.remove("is-show");
      return;
    }
    errBox.textContent = msg;
    errBox.classList.add("is-show");
  }

  function hasLetterAndNumber(pw) {
    return /[A-Za-z]/.test(pw) && /[0-9]/.test(pw);
  }

  function validate() {
    const a = (curPw.value || "").trim();
    const b = (newPw.value || "").trim();
    const c = (newPw2.value || "").trim();

    // 0) 모두 비면 초기 상태
    if (!a && !b && !c) {
      showError("");
      saveBtn.disabled = true;
      return false;
    }

    // 1) required
    if (!a || !b || !c) {
      showError("모든 항목을 입력해주세요.");
      saveBtn.disabled = true;
      return false;
    }

    // 2) 길이
    if (b.length < 8) {
      showError("새 비밀번호는 8자 이상으로 입력해주세요.");
      saveBtn.disabled = true;
      return false;
    }

    // 3) 확인 일치 (✅ 권장 룰보다 먼저)
    if (b !== c) {
      showError("새 비밀번호와 확인이 일치하지 않아요.");
      saveBtn.disabled = true;
      return false;
    }

    // 4) 현재 비밀번호와 동일 금지(권장/필수는 선택)
    if (a === b) {
      showError("새 비밀번호는 현재 비밀번호와 다르게 입력해주세요.");
      saveBtn.disabled = true;
      return false;
    }

    // 5) 권장 룰(영문+숫자) — 통과는 허용, 메시지만 유지
    if (!hasLetterAndNumber(b)) {
      showError("새 비밀번호는 영문과 숫자를 함께 포함하는 것을 권장해요.");
      saveBtn.disabled = false;
      return true;
    }

    showError("");
    saveBtn.disabled = false;
    return true;
  }

  ["input", "change", "keyup"].forEach((evt) => form.addEventListener(evt, validate));

  form.addEventListener("submit", (e) => {
    const ok = validate();
    if (!ok) e.preventDefault();
  });

  validate();
})();
