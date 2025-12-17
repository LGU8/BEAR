/* =========================
   settings_s3.js
   - 10칸 segmented click
   - 합=10 강제(자동 보정)
   - 변경 시 저장 버튼 활성화
   ========================= */

(function () {
  const form = document.getElementById("prefForm");
  if (!form) return;

  const sliders = Array.from(document.querySelectorAll(".seg-slider"));
  const saveBtn = document.getElementById("saveBtn");
  const sumNowEl = document.getElementById("sumNow");

  // hidden inputs
  const hid = {
    carb: document.getElementById("ratioCarb"),
    protein: document.getElementById("ratioProtein"),
    fat: document.getElementById("ratioFat"),
  };

  // 초기값(서버 렌더 값)
  const initial = {
    carb: parseInt(hid.carb.value || "0", 10),
    protein: parseInt(hid.protein.value || "0", 10),
    fat: parseInt(hid.fat.value || "0", 10),
  };

  // 현재값
  const state = { ...initial };

  function clamp(v, min, max) {
    v = parseInt(v, 10);
    if (Number.isNaN(v)) v = 0;
    return Math.max(min, Math.min(max, v));
  }

  function sum() {
    return state.carb + state.protein + state.fat;
  }

  function setHidden() {
    hid.carb.value = String(state.carb);
    hid.protein.value = String(state.protein);
    hid.fat.value = String(state.fat);
  }

  function setSumUI() {
    if (sumNowEl) sumNowEl.textContent = String(sum());
  }

  function renderSlider(key) {
    const slider = sliders.find(s => s.dataset.key === key);
    if (!slider) return;

    const v = state[key];
    slider.dataset.value = String(v);

    const segs = Array.from(slider.querySelectorAll(".seg"));
    segs.forEach((btn) => {
      const idx = parseInt(btn.dataset.idx || "0", 10);
      btn.classList.toggle("is-on", idx <= v);
    });
  }

  function renderAll() {
    renderSlider("carb");
    renderSlider("protein");
    renderSlider("fat");
    setHidden();
    setSumUI();
  }

  function isChanged() {
    return (
      state.carb !== initial.carb ||
      state.protein !== initial.protein ||
      state.fat !== initial.fat
    );
  }

  function isValid() {
    // 합=10 강제 정책이므로, 최종 체크도 10으로
    return sum() === 10;
  }

  function updateSaveBtn() {
    const ok = isChanged() && isValid();
    saveBtn.disabled = !ok;
  }

  // ✅ 합=10 강제 보정
  // - key를 newValue로 바꾼 뒤,
  // - 나머지 두 값을 합이 10이 되도록 조정(큰 값부터 줄이기/늘리기)
  function rebalance(key, newValue) {
    newValue = clamp(newValue, 0, 10);
    state[key] = newValue;

    const keys = ["carb", "protein", "fat"].filter(k => k !== key);
    const a = keys[0];
    const b = keys[1];

    // 현재 합이 10이 되도록 a/b 조정
    let curSum = sum();
    let diff = 10 - curSum; // +면 늘려야, -면 줄여야

    // helper: (targetKey) 한 칸씩 조정
    function addOne(k) {
      if (state[k] < 10) { state[k] += 1; return true; }
      return false;
    }
    function subOne(k) {
      if (state[k] > 0) { state[k] -= 1; return true; }
      return false;
    }

    // diff가 +면 a/b를 늘려야 함, diff가 -면 a/b를 줄여야 함
    // “큰 값부터 줄이기”, “작은 값부터 늘리기”가 자연스러움
    while (diff !== 0) {
      if (diff > 0) {
        // 늘리기: 더 작은 쪽부터 채우기
        const first = state[a] <= state[b] ? a : b;
        const second = first === a ? b : a;
        if (!addOne(first) && !addOne(second)) break;
        diff -= 1;
      } else {
        // 줄이기: 더 큰 쪽부터 줄이기
        const first = state[a] >= state[b] ? a : b;
        const second = first === a ? b : a;
        if (!subOne(first) && !subOne(second)) break;
        diff += 1;
      }
    }

    // 안전: 범위 클램프
    state.carb = clamp(state.carb, 0, 10);
    state.protein = clamp(state.protein, 0, 10);
    state.fat = clamp(state.fat, 0, 10);
  }

  // 이벤트 바인딩
  sliders.forEach((slider) => {
    slider.addEventListener("click", (e) => {
      const btn = e.target.closest(".seg");
      if (!btn) return;

      const key = slider.dataset.key;
      const idx = parseInt(btn.dataset.idx || "0", 10);

      if (!key || !idx) return;

      rebalance(key, idx);
      renderAll();
      updateSaveBtn();
    });
  });

  // 초기 렌더
  renderAll();
  updateSaveBtn();

  // 제출 직전 최종 검증(서버에서도 동일 검증 권장)
  form.addEventListener("submit", (e) => {
    if (!isValid()) {
      e.preventDefault();
      updateSaveBtn();
    }
  });
})();