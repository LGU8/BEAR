// static/js/settings/settings_s2.js
// S2 개인정보 수정: 변경 감지 + 검증 + 저장 버튼 활성화
// (추후 badges 페이지 완료 후, badge 선택/변경 hook 추가 예정)

(function () {
  const form = document.getElementById("s2Form");
  if (!form) return;

  const saveBtn = document.getElementById("saveBtn");
  const errBox = document.getElementById("s2Error");

  const nicknameEl = document.getElementById("nickname");
  const birthUIEl = document.getElementById("birth_date_ui");
  const birthDtEl = document.getElementById("birth_dt");
  const genderEl = document.getElementById("gender");
  const heightEl = document.getElementById("height_cm");
  const weightEl = document.getElementById("weight_kg");

  const genderBtns = Array.from(document.querySelectorAll(".seg-toggle-btn"));

  // -------------------------
  // 0) 상태
  // -------------------------
  let hasInteracted = false; // 초기 로드에서 에러를 숨기기 위한 플래그

  function setError(msg) {
    if (!errBox) return;
    errBox.textContent = msg || "";
  }

  function markInteracted() {
    hasInteracted = true;
  }

  function yyyymmddFromDateInput(v) {
    // v: "YYYY-MM-DD"
    if (!v || typeof v !== "string" || v.length !== 10) return "";
    return v.replaceAll("-", "");
  }

  function todayYYYYMMDD() {
    const d = new Date();
    const yyyy = String(d.getFullYear());
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${yyyy}${mm}${dd}`;
  }

  // -------------------------
  // 1) 초기 동기화(중요)
  // -------------------------
  // (1) date input -> hidden birth_dt 동기화
  if (birthUIEl && birthDtEl) {
    if (!birthDtEl.value && birthUIEl.value) {
      birthDtEl.value = yyyymmddFromDateInput(birthUIEl.value);
    }
  }

  // (2) hidden gender가 비어있으면 active 버튼 기준으로 동기화
  if (genderEl && (!genderEl.value || genderEl.value.trim() === "")) {
    const activeBtn = genderBtns.find((b) => b.classList.contains("is-active"));
    if (activeBtn) {
      const v = activeBtn.getAttribute("data-value") || "";
      genderEl.value = v;
    }
  }

  // --- initial snapshot (변경 감지용) : 초기 동기화 이후에 찍어야 정확함
  const initial = {
    nickname: (nicknameEl?.value || "").trim(),
    birth_dt: (birthDtEl?.value || "").trim(),
    gender: (genderEl?.value || "").trim(),
    height_cm: (heightEl?.value || "").trim(),
    weight_kg: (weightEl?.value || "").trim(),
  };

  function nowState() {
    return {
      nickname: (nicknameEl?.value || "").trim(),
      birth_dt: (birthDtEl?.value || "").trim(),
      gender: (genderEl?.value || "").trim(),
      height_cm: (heightEl?.value || "").trim(),
      weight_kg: (weightEl?.value || "").trim(),
    };
  }

  function isChanged() {
    const now = nowState();
    return Object.keys(initial).some((k) => (now[k] || "") !== (initial[k] || ""));
  }

  // -------------------------
  // 2) 검증(Validation)
  // -------------------------
  function validate() {
    // nickname: 한글/영문/숫자/_ 만 허용
    const nickname = (nicknameEl?.value || "").trim();
    if (!nickname) return { ok: false, msg: "닉네임을 입력해 주세요." };

    const reNick = /^[A-Za-z0-9_가-힣]+$/;
    if (!reNick.test(nickname)) {
      return { ok: false, msg: "닉네임은 한글/영문/숫자/밑줄(_)만 가능해요." };
    }

    // birth_dt: YYYYMMDD + 미래일 방지
    const birth_dt = (birthDtEl?.value || "").trim();
    if (!birth_dt || birth_dt.length !== 8) return { ok: false, msg: "생년월일을 선택해 주세요." };

    const reBirth = /^\d{8}$/;
    if (!reBirth.test(birth_dt)) return { ok: false, msg: "생년월일 형식이 올바르지 않아요." };

    const today = todayYYYYMMDD();
    if (birth_dt > today) return { ok: false, msg: "생년월일은 미래 날짜로 설정할 수 없어요." };

    // gender: M/F
    const gender = (genderEl?.value || "").trim();
    if (!(gender === "M" || gender === "F")) return { ok: false, msg: "성별을 선택해 주세요." };

    // height
    const hRaw = (heightEl?.value || "").trim();
    const h = parseInt(hRaw, 10);
    if (Number.isNaN(h)) return { ok: false, msg: "키를 입력해 주세요." };
    if (h < 90 || h > 250) return { ok: false, msg: "키는 90~250cm 범위로 입력해 주세요." };

    // weight
    const wRaw = (weightEl?.value || "").trim();
    const w = parseInt(wRaw, 10);
    if (Number.isNaN(w)) return { ok: false, msg: "몸무게를 입력해 주세요." };
    if (w < 20 || w > 300) return { ok: false, msg: "몸무게는 20~300kg 범위로 입력해 주세요." };

    return { ok: true, msg: "" };
  }

  // -------------------------
  // 3) 저장 버튼 상태 업데이트
  // -------------------------
  function updateSaveBtn() {
    if (!saveBtn) return;

    const changed = isChanged();
    const v = validate();

    // UX: 아직 사용자가 건드린 적 없고, 변경도 없다면 에러 노출 X
    if (!hasInteracted && !changed) {
      setError("");
      saveBtn.disabled = true;
      return;
    }

    // 유효성 실패: interacted 이후에만 에러 노출(타이핑 중 UX)
    if (!v.ok) {
      if (hasInteracted) setError(v.msg);
      saveBtn.disabled = true;
      return;
    }

    // 유효성 OK + 변경 있음 => enable
    setError("");
    saveBtn.disabled = !changed;
  }

  // -------------------------
  // 4) 이벤트 바인딩
  // -------------------------

  // (A) gender toggle
  genderBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      markInteracted();

      const value = btn.getAttribute("data-value") || "";
      if (genderEl) genderEl.value = value;

      genderBtns.forEach((b) => {
        const on = (b.getAttribute("data-value") || "") === value;
        b.classList.toggle("is-active", on);
        b.setAttribute("aria-pressed", on ? "true" : "false");
      });

      updateSaveBtn();
    });
  });

  // (B) birth date ui -> hidden birth_dt
  if (birthUIEl && birthDtEl) {
    birthUIEl.addEventListener("change", () => {
      markInteracted();
      birthDtEl.value = yyyymmddFromDateInput(birthUIEl.value);
      updateSaveBtn();
    });
  }

  // (C) inputs change
  [nicknameEl, heightEl, weightEl].forEach((el) => {
    if (!el) return;

    el.addEventListener("input", () => {
      markInteracted();
      updateSaveBtn();
    });

    el.addEventListener("change", () => {
      markInteracted();
      updateSaveBtn();
    });
  });

  // -------------------------
  // 5) submit 제어
  // -------------------------
  form.addEventListener("submit", (e) => {
    markInteracted();

    const v = validate();
    if (!v.ok) {
      e.preventDefault();
      setError(v.msg);
      if (saveBtn) saveBtn.disabled = true;
      return;
    }

    // 변경 없으면 submit 방지
    if (!isChanged()) {
      e.preventDefault();
      setError("");
      if (saveBtn) saveBtn.disabled = true;
      return;
    }

    // (추후 hook) badges 페이지 완료 후:
    // - badge 선택값(hidden input) 검증/변경 감지/submit payload에 포함
  });

  // initial run
  updateSaveBtn();
})();
