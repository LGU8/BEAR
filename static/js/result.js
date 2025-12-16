// static/js/result.js
(function () {
  const params = new URLSearchParams(location.search);
  const date = params.get("date");
  const meal = params.get("meal");

  const keyDraft = `scanDraft:${date}:${meal}`;
  const draftRaw = localStorage.getItem(keyDraft);
  if (!draftRaw) return;

  const draft = JSON.parse(draftRaw);

  // 1) 이미지/필드 채우기
  document.getElementById("result-img").src = draft.image;
  document.getElementById("f-brand").value = draft.result.brand || "";
  document.getElementById("f-name").value = draft.result.name || "";
  document.getElementById("f-kcal").value = draft.result.kcal || "";
  document.getElementById("f-carb").value = draft.result.carb || "";
  document.getElementById("f-protein").value = draft.result.protein || "";
  document.getElementById("f-fat").value = draft.result.fat || "";

  // 2) 저장: 한 끼(MealRecord)에 item으로 추가
  document.getElementById("btn-save").addEventListener("click", () => {
    const item = {
      type: "food",                 // recipe도 들어오면 "recipe"로 구분
      source: "scan",               // scan|search|recipe
      brand: document.getElementById("f-brand").value,
      name: document.getElementById("f-name").value,
      kcal: document.getElementById("f-kcal").value,
      carb: document.getElementById("f-carb").value,
      protein: document.getElementById("f-protein").value,
      fat: document.getElementById("f-fat").value,
      image: draft.image,
    };

    const keyMeal = `mealRecords:${date}:${meal}`;
    const current = JSON.parse(localStorage.getItem(keyMeal) || "null") || {
      date,
      meal,
      items: [],
      createdAt: new Date().toISOString(),
    };

    current.items.push(item);
    localStorage.setItem(keyMeal, JSON.stringify(current));

    // draft 삭제
    localStorage.removeItem(keyDraft);

    // 3) record로 복귀(같은 date/meal 유지)
    location.href = `/record/?date=${encodeURIComponent(date)}&meal=${encodeURIComponent(meal)}`;
  });
})();
