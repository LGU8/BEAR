(function () {
  const form = document.getElementById("pwForm");
  if (!form) return;

  const curPw = document.getElementById("curPw");
  const newPw = document.getElementById("newPw");
  const newPw2 = document.getElementById("newPw2");
  const saveBtn = document.getElementById("saveBtn");
  const errBox = document.getElementById("pwError");

  function show(msg) {
    if (!errBox) return;
    errBox.textContent = msg || "";
  }

  function hasLetterAndNumber(pw) {
    return /[A-Za-z]/.test(pw) && /[0-9]/.test(pw);
  }

  function validate() {
    const a = (curPw.value || "").trim();
    const b = (newPw.value || "").trim();
    const c = (newPw2.value || "").trim();

    // 초기
    if (!a && !b && !c) {
      show("");
      saveBtn.disabled = true;
      return false;
    }

    // required
    if (!a || !b || !c) {
      show("모든 항목을 입력해주세요.");
      saveBtn.disabled = true;
      return false;
    }

    // length
    if (b.length < 8) {
      show("새 비밀번호는 8자 이상으로 입력해주세요.");
      saveBtn.disabled = true;
      return false;
    }

    // match
    if (b !== c) {
      show("새 비밀번호와 재입력이 일치하지 않아요.");
      saveBtn.disabled = true;
      return false;
    }

    // not same as current
    if (a === b) {
      show("새 비밀번호는 현재 비밀번호와 다르게 입력해주세요.");
      saveBtn.disabled = true;
      return false;
    }

    // 권장 룰: 통과는 허용, 메시지만 출력 (원하면 여기서 disabled 유지로 바꿔도 됨)
    if (!hasLetterAndNumber(b)) {
      show("영문과 숫자를 함께 포함하는 것을 권장해요.");
      saveBtn.disabled = false;
      return true;
    }

    show("");
    saveBtn.disabled = false;
    return true;
  }

  ["input", "change", "keyup"].forEach((evt) => form.addEventListener(evt, validate));

  form.addEventListener("submit", (e) => {
    if (!validate()) e.preventDefault();
  });

  validate();
})();