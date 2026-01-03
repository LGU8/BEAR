/* static/js/settings/settings_s3.js */

/* =========================
   Settings S3 (Preferences Edit) - 3단 선택
   - UI: 별로(-1) / 보통(0) / 많이(1)
   - 저장: ratio 3개 합=10 유지 (기존 서버 검증 그대로)
   - ⚠️ 중요: "기존 DB ratio"가 3단 매핑으로 정확히 표현 불가할 수 있으므로
     ▸ 로드시 ratio는 그대로 유지 (자동 변환으로 값 바뀌지 않게)
     ▸ 사용자가 클릭하여 변경할 때만 ratio를 새로 계산/갱신
   ========================= */

(function () {
  const form = document.getElementById("prefForm");
  if (!form) return;

  const saveBtn = document.getElementById("saveBtn");
  const helperText = document.getElementById("helperText");
  const sumNowEl = document.getElementById("sumNow");

  // hidden ratio (서버로 보낼 최종 저장값)
  const hidRatio = {
    carb: document.getElementById("ratioCarb"),
    protein: document.getElementById("ratioProtein"),
    fat: document.getElementById("ratioFat"),
  };

  // hidden choice (UI 상태 저장용)
  const hidChoice = {
    carb: document.getElementById("choiceCarb"),
    protein: document.getElementById("choiceProtein"),
    fat: document.getElementById("choiceFat"),
  };

  function toInt(x, d = 0) {
    const v = parseInt(String(x ?? ""), 10);
    return Number.isNaN(v) ? d : v;
  }

  function clamp(v, min, max) {
    v = toInt(v, 0);
    return Math.max(min, Math.min(max, v));
  }

  // --------------------------------
  // -1/0/1 -> ratio 합10 변환 (accounts Step3와 동일)
  // --------------------------------
  function choicesToRatios(c, p, f) {
    // weight = 2 + choice => -1:1, 0:2, 1:3
    const weights = [
      { k: "carb",    w: 2 + c },
      { k: "protein", w: 2 + p },
      { k: "fat",     w: 2 + f },
    ];
    const sumW = weights.reduce((a, x) => a + x.w, 0);

    const raws = weights.map((x) => {
      const raw = (10 * x.w) / sumW;
      const flo = Math.floor(raw);
      return { ...x, raw, flo, rem: raw - flo };
    });

    let total = raws.reduce((a, x) => a + x.flo, 0);

    // remainder distribute (tie-break: carb > protein > fat)
    const order = { carb: 0, protein: 1, fat: 2 };
    raws.sort((a, b) => (b.rem - a.rem) || (order[a.k] - order[b.k]));

    let i = 0;
    while (total < 10) {
      raws[i].flo += 1;
      total += 1;
      i = (i + 1) % raws.length;
    }

    const out = { ratio_carb: 0, ratio_protein: 0, ratio_fat: 0 };
    raws.forEach((x) => (out[`ratio_${x.k}`] = x.flo));
    return out;
  }

  // --------------------------------
  // DB ratio(0~10) -> choice(-1/0/1) 매핑 (UI 초기상태용)
  // - 값은 "표시"만; 로드시 ratio를 자동 변환하지 않음
  // --------------------------------
  function ratioToChoice(ratio) {
    const r = clamp(ratio, 0, 10);
    // 추천 경계: <=2 별로, 3~4 보통, >=5 많이
    if (r <= 2) return -1;
    if (r <= 4) return 0;
    return 1;
  }

  // 초기 ratio(서버 렌더 값)
  const initialRatio = {
    carb: clamp(hidRatio.carb.value, 0, 10),
    protein: clamp(hidRatio.protein.value, 0, 10),
    fat: clamp(hidRatio.fat.value, 0, 10),
  };

  // 현재 choice 상태
  const stateChoice = {
    carb: ratioToChoice(initialRatio.carb),
    protein: ratioToChoice(initialRatio.protein),
    fat: ratioToChoice(initialRatio.fat),
  };

  // UI 버튼 on/off
  function setActiveUI(rowEl, v) {
    const btns = Array.from(rowEl.querySelectorAll(".tri-btn"));
    btns.forEach((b) => {
      const on = String(b.dataset.v) === String(v);
      b.classList.toggle("is-on", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function sumRatio() {
    return (
      clamp(hidRatio.carb.value, 0, 10) +
      clamp(hidRatio.protein.value, 0, 10) +
      clamp(hidRatio.fat.value, 0, 10)
    );
  }

  function updateSumUI() {
    if (sumNowEl) sumNowEl.textContent = String(sumRatio());
  }

  function updateHelper() {
    const c = clamp(hidRatio.carb.value, 0, 10);
    const p = clamp(hidRatio.protein.value, 0, 10);
    const f = clamp(hidRatio.fat.value, 0, 10);
    if (helperText) {
      helperText.textContent = `적용 비율(합10): 탄 ${c} · 단 ${p} · 지 ${f}`;
    }
  }

  function isChanged() {
    const c = clamp(hidRatio.carb.value, 0, 10);
    const p = clamp(hidRatio.protein.value, 0, 10);
    const f = clamp(hidRatio.fat.value, 0, 10);
    return (
      c !== initialRatio.carb ||
      p !== initialRatio.protein ||
      f !== initialRatio.fat
    );
  }

  function isValid() {
    return sumRatio() === 10;
  }

  function updateSaveBtn() {
    // “값 변경 + 합=10”일 때만 저장 활성화
    const ok = isChanged() && isValid();
    if (saveBtn) saveBtn.disabled = !ok;
  }

  // choice hidden 갱신(디버깅/상태용)
  function syncChoiceHidden() {
    hidChoice.carb.value = String(stateChoice.carb);
    hidChoice.protein.value = String(stateChoice.protein);
    hidChoice.fat.value = String(stateChoice.fat);
  }

  // 사용자가 클릭해서 choice가 바뀌었을 때만 ratio를 새로 계산
  function applyChoiceToRatio() {
    const ratios = choicesToRatios(stateChoice.carb, stateChoice.protein, stateChoice.fat);

    hidRatio.carb.value = String(ratios.ratio_carb);
    hidRatio.protein.value = String(ratios.ratio_protein);
    hidRatio.fat.value = String(ratios.ratio_fat);

    syncChoiceHidden();
    updateHelper();
    updateSumUI();
    updateSaveBtn();
  }

  // 초기 렌더: UI는 choice로 표시하되, ratio는 서버값 유지
  document.querySelectorAll(".q-row").forEach((row) => {
    const key = row.dataset.key;
    if (!key) return;

    const v = stateChoice[key];
    setActiveUI(row, v);

    row.querySelectorAll(".tri-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const nv = toInt(btn.dataset.v, 0);
        stateChoice[key] = nv;

        setActiveUI(row, nv);
        applyChoiceToRatio(); // ✅ 클릭한 순간에만 ratio 재계산/저장값 갱신
      });
    });
  });

  // 초기 helper/sum은 “서버 ratio”로 표시
  syncChoiceHidden();
  updateHelper();
  updateSumUI();
  updateSaveBtn();

  // 제출 직전 검증(방어)
  form.addEventListener("submit", (e) => {
    if (!isValid()) {
      e.preventDefault();
      updateSumUI();
      updateSaveBtn();
      if (helperText) helperText.textContent = "오류: 탄/단/지 합계가 10이 되어야 저장할 수 있어요.";
    }
  });
})();
