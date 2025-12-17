// static/js/settings/settings_s2.js

(function () {
  const form = document.getElementById("s2Form");
  const saveBtn = document.getElementById("saveBtn");
  const errBox = document.getElementById("s2Error");

  const nicknameEl = document.getElementById("nickname");
  const birthUIEl = document.getElementById("birth_date_ui");
  const birthDtEl = document.getElementById("birth_dt");
  const genderEl = document.getElementById("gender");
  const heightEl = document.getElementById("height_cm");
  const weightEl = document.getElementById("weight_kg");

  const genderBtns = Array.from(document.querySelectorAll(".seg-toggle-btn"));

  // --- initial snapshot (변경 감지용)
  const initial = {
    nickname: (nicknameEl?.value || "").trim(),
    birth_dt: (birthDtEl?.value || "").trim(),
    gender: (genderEl?.value || "").trim(),
    height_cm: (heightEl?.value || "").trim(),
    weight_kg: (weightEl?.value || "").trim(),
  };

  function setError(msg) {
    errBox.textContent = msg || "";
  }

  function yyyymmddFromDateInput(v) {
    // v: YYYY-MM-DD
    if (!v || typeof v !== "string" || v.length !== 10) return "";
    return v.replaceAll("-", "");
  }

  function isChanged() {
    const now = {
      nickname: (nicknameEl?.value || "").trim(),
      birth_dt: (birthDtEl?.value || "").trim(),
      gender: (genderEl?.value || "").trim(),
      height_cm: (heightEl?.value || "").trim(),
      weight_kg: (weightEl?.value || "").trim(),
    };

    return Object.keys(initial).some((k) => (now[k] || "") !== (initial[k] || ""));
  }

  function validate() {
    setError("");

    // nickname: 한글/영문/숫자/_
    const nickname = (nicknameEl?.value || "").trim();
    if (!nickname) return { ok: false, msg: "닉네임을 입력해 주세요." };

    const re = /^[A-Za-z0-9_가-힣]+$/;
    if (!re.test(nickname)) return { ok: false, msg: "닉네임은 한글/영문/숫자/밑줄(_)만 가능해요." };

    // birth_dt: YYYYMMDD
    const birth_dt = (birthDtEl?.value || "").trim();
    if (!birth_dt || birth_dt.length !== 8) return { ok: false, msg: "생년월일을 선택해 주세요." };

    // gender: M/F
    const gender = (genderEl?.value || "").trim();
    if (!(gender === "M" || gender === "F")) return { ok: false, msg: "성별을 선택해 주세요." };

    // height
    const h = parseInt((heightEl?.value || "").trim(), 10);
    if (Number.isNaN(h)) return { ok: false, msg: "키를 입력해 주세요." };
    if (h < 90 || h > 250) return { ok: false, msg: "키는 90~250cm 범위로 입력해 주세요." };

    // weight
    const w = parseInt((weightEl?.value || "").trim(), 10);
    if (Number.isNaN(w)) return { ok: false, msg: "몸무게를 입력해 주세요." };
    if (w < 20 || w > 300) return { ok: false, msg: "몸무게는 20~300kg 범위로 입력해 주세요." };

    return { ok: true, msg: "" };
  }

  function updateSaveBtn() {
    const v = validate();
    if (!v.ok) {
      setError(v.msg);
      saveBtn.disabled = true;
      return;
    }

    // 유효성 OK + 변경 있음 => enable
    saveBtn.disabled = !isChanged();
    if (!isChanged()) setError("");
  }

  // --- gender toggle
  genderBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const value = btn.getAttribute("data-value") || "";
      genderEl.value = value;

      genderBtns.forEach((b) => {
        const on = (b.getAttribute("data-value") || "") === value;
        b.classList.toggle("is-active", on);
        b.setAttribute("aria-pressed", on ? "true" : "false");
      });

      updateSaveBtn();
    });
  });

  // --- birth date ui -> birth_dt
  if (birthUIEl) {
    birthUIEl.addEventListener("change", () => {
      birthDtEl.value = yyyymmddFromDateInput(birthUIEl.value);
      updateSaveBtn();
    });

    // 초기 동기화(혹시 hidden이 비었고 ui에만 값이 있으면)
    if (!birthDtEl.value && birthUIEl.value) {
      birthDtEl.value = yyyymmddFromDateInput(birthUIEl.value);
    }
  }

  // --- inputs change
  [nicknameEl, heightEl, weightEl].forEach((el) => {
    if (!el) return;
    el.addEventListener("input", updateSaveBtn);
    el.addEventListener("change", updateSaveBtn);
  });

  // --- submit
  form.addEventListener("submit", (e) => {
    const v = validate();
    if (!v.ok) {
      e.preventDefault();
      setError(v.msg);
      saveBtn.disabled = true;
      return;
    }
    // 변경 없으면 submit 방지
    if (!isChanged()) {
      e.preventDefault();
      setError("");
      saveBtn.disabled = true;
    }
  });

  // initial run
  updateSaveBtn();
})();