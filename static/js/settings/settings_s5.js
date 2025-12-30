// static/js/settings/settings_s5.js
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

    // 사용자가 입력을 시작하면(빈 값에서 벗어나면) 서버 에러 문구는 클라이언트 검증으로 대체
    if (a || b || c) {
      // 서버 에러가 남아있더라도, 아래 검증 결과로 갱신되게 함
    }

    if (!a && !b && !c) {
      // 초기 상태: 서버에서 내려온 에러가 있더라도 일단 유지하고 싶으면 show("") 대신 그대로 두면 됨.
      // 여기서는 "완전 초기"면 버튼만 비활성화하고 텍스트는 유지.
      saveBtn.disabled = true;
      return false;
    }

    if (!a || !b || !c) {
      show("모든 항목을 입력해주세요.");
      saveBtn.disabled = true;
      return false;
    }

    if (b.length < 8) {
      show("새 비밀번호는 8자 이상으로 입력해주세요.");
      saveBtn.disabled = true;
      return false;
    }

    if (b !== c) {
      show("새 비밀번호와 재입력이 일치하지 않아요.");
      saveBtn.disabled = true;
      return false;
    }

    if (a === b) {
      show("새 비밀번호는 현재 비밀번호와 다르게 입력해주세요.");
      saveBtn.disabled = true;
      return false;
    }

    // 권장 룰: 경고만, 저장은 가능
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

  // 초기 호출
  validate();
})();
