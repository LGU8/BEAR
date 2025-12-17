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
    const hasLetter = /[A-Za-z]/.test(pw);
    const hasNumber = /[0-9]/.test(pw);
    return hasLetter && hasNumber;
  }

  function validate() {
    const a = (curPw.value || "").trim();
    const b = (newPw.value || "").trim();
    const c = (newPw2.value || "").trim();

    // 아무것도 입력 안 했으면 비활성
    if (!a && !b && !c) {
      showError("");
      saveBtn.disabled = true;
      return false;
    }

    // 기본 required 체크
    if (!a || !b || !c) {
      showError("모든 항목을 입력해주세요.");
      saveBtn.disabled = true;
      return false;
    }

    if (b.length < 8) {
      showError("새 비밀번호는 8자 이상으로 입력해주세요.");
      saveBtn.disabled = true;
      return false;
    }

    // 권장 룰(필수로 하고 싶으면 조건을 return false로 고정)
    if (!hasLetterAndNumber(b)) {
      showError("새 비밀번호는 영문과 숫자를 함께 포함하는 것을 권장해요.");
      // 권장은 버튼은 켜주되, 메시지는 유지
      saveBtn.disabled = false;
      return true;
    }

    if (b !== c) {
      showError("새 비밀번호와 확인이 일치하지 않아요.");
      saveBtn.disabled = true;
      return false;
    }

    showError("");
    saveBtn.disabled = false;
    return true;
  }

  ["input", "change", "keyup"].forEach((evt) => {
    form.addEventListener(evt, validate);
  });

  form.addEventListener("submit", (e) => {
    const ok = validate();
    if (!ok) e.preventDefault();
  });

  // 초기
  validate();
})();
