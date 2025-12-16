// static/js/result.js

console.log("[result.js] loaded");

(function () {
  const params = new URLSearchParams(location.search);
  const date = params.get("date");
  const meal = params.get("meal");
  const draftKey = `scanDraft:${date}:${meal}`;

  // 0) draft 확인
  const draftRaw = localStorage.getItem(draftKey);
  if (!draftRaw) {
    console.error("[result] scanDraft not found:", draftKey);
    return;
  }

  const draft = JSON.parse(draftRaw);
  const mode = draft.mode || "barcode";

  // 1) 이미지 표시
  const imgEl = document.getElementById("result-img");
  if (imgEl && draft.image) imgEl.src = draft.image;

  // 2) mode에 따라 패널 표시
  const panelBarcode = document.getElementById("result-barcode");
  const panelNutrition = document.getElementById("result-nutrition");

  if (mode === "nutrition") {
    if (panelNutrition) panelNutrition.style.display = "";
    if (panelBarcode) panelBarcode.style.display = "none";
  } else {
    if (panelBarcode) panelBarcode.style.display = "";
    if (panelNutrition) panelNutrition.style.display = "none";
  }

  // 3) draft.result로 input 채우기
  const r = draft.result || {};
  function setVal(id, v) {
    const el = document.getElementById(id);
    if (el && v != null) el.value = v;
  }

  if (mode === "nutrition") {
    setVal("n-brand", r.brand);
    setVal("n-name", r.name);
    setVal("n-serving", r.serving);
    setVal("n-kcal", r.kcal);
    setVal("n-carb", r.carb);
    setVal("n-protein", r.protein);
    setVal("n-fat", r.fat);
  } else {
    setVal("b-brand", r.brand);
    setVal("b-name", r.name);
    setVal("b-serving", r.serving);
    setVal("b-kcal", r.kcal);
    setVal("b-carb", r.carb);
    setVal("b-protein", r.protein);
    setVal("b-fat", r.fat);
  }

  // 4) 저장 버튼
  const btnSave = document.getElementById("btn-save");
  if (!btnSave) {
    console.error("[result] #btn-save not found");
    return;
  }

  // (안전) 버튼이 form 안에 있어도 submit 안 되게
  btnSave.setAttribute("type", "button");

  btnSave.addEventListener("click", (e) => {
    e.preventDefault();

    // 4-1) mealRecords 누적 저장
    const finalKey = `mealRecords:${date}:${meal}`;
    const prevRaw = localStorage.getItem(finalKey);
    const prev = prevRaw ? JSON.parse(prevRaw) : { date, meal, items: [], savedAt: null };

    prev.items = Array.isArray(prev.items) ? prev.items : [];

    const get = (id) => document.getElementById(id)?.value || "";

    const item = {
      type: mode, // "barcode" | "nutrition"
      brand: (mode === "nutrition") ? get("n-brand") : get("b-brand"),
      name: (mode === "nutrition") ? get("n-name") : get("b-name"),
      serving: (mode === "nutrition") ? get("n-serving") : get("b-serving"),
      kcal: (mode === "nutrition") ? get("n-kcal") : get("b-kcal"),
      carb: (mode === "nutrition") ? get("n-carb") : get("b-carb"),
      protein: (mode === "nutrition") ? get("n-protein") : get("b-protein"),
      fat: (mode === "nutrition") ? get("n-fat") : get("b-fat"),
      image: draft.image || null,
      addedAt: Date.now(),
    };

    prev.items.push(item);
    prev.savedAt = Date.now();

    localStorage.setItem(finalKey, JSON.stringify(prev));

    // 4-2) ✅ 최근 3개 카드용 히스토리 저장(끼니별)
    const historyKey = `mealHistory:${meal}`;
    const historyRaw = localStorage.getItem(historyKey);
    const history = historyRaw ? JSON.parse(historyRaw) : [];

    const snapshot = {
      date,
      meal,
      items: prev.items,     // ✅ 누적된 전체 items
      savedAt: prev.savedAt,
    };

    history.unshift(snapshot);
    localStorage.setItem(historyKey, JSON.stringify(history.slice(0, 30)));

    // 4-3) draft 정리
    localStorage.removeItem(draftKey);

    // 4-4) record로 복귀
    location.href = `/record/?date=${encodeURIComponent(date)}&meal=${encodeURIComponent(meal)}`;
  });
})();
