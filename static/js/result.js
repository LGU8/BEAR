// static/js/result.js
(function () {
  const params = new URLSearchParams(location.search);
  const date = params.get("date");
  const meal = params.get("meal");
  const key = `scanDraft:${date}:${meal}`;

  const draftRaw = localStorage.getItem(key);
  if (!draftRaw) {
    console.error("[result] scanDraft not found:", key);
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

  // 3) draft.result로 input 채우기(더미/실데이터 모두 대응)
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

  // 4) 저장: UI에서 입력한 값으로 최종 payload 만들기
  const btnSave = document.getElementById("btn-save");
  if (!btnSave) return;

  btnSave.addEventListener("click", () => {
    const payload = {
      date,
      meal,
      mode,
      image: draft.image || null,
      // 한 끼 카드에 “여러 항목”이 들어갈 수 있게 items 배열 구조 권장
      items: [
        {
          type: (mode === "nutrition") ? "nutrition" : "barcode",
          brand: (mode === "nutrition") ? document.getElementById("n-brand")?.value : document.getElementById("b-brand")?.value,
          name:  (mode === "nutrition") ? document.getElementById("n-name")?.value  : document.getElementById("b-name")?.value,
          serving: (mode === "nutrition") ? document.getElementById("n-serving")?.value : document.getElementById("b-serving")?.value,
          kcal: (mode === "nutrition") ? document.getElementById("n-kcal")?.value : document.getElementById("b-kcal")?.value,
          carb: (mode === "nutrition") ? document.getElementById("n-carb")?.value : document.getElementById("b-carb")?.value,
          protein: (mode === "nutrition") ? document.getElementById("n-protein")?.value : document.getElementById("b-protein")?.value,
          fat: (mode === "nutrition") ? document.getElementById("n-fat")?.value : document.getElementById("b-fat")?.value,
        }
      ],
      savedAt: Date.now(),
    };

    // (임시) 최종 저장
    const finalKey = `mealRecords:${date}:${meal}`;
    localStorage.setItem(finalKey, JSON.stringify(payload));

    // draft는 정리
    localStorage.removeItem(key);

    // record로 복귀
    location.href = `/record/?date=${encodeURIComponent(date)}&meal=${encodeURIComponent(meal)}`;
  });
})();
