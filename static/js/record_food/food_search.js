// static/js/record_food/food_search.js
console.log("[food_search] FILE EXECUTED v=20251222-3");

document.addEventListener("DOMContentLoaded", () => {
  console.log("[food_search] DOMContentLoaded href=", location.href);

  const inputEl = document.getElementById("food-search-input");
  const btnEl = document.getElementById("food-search-btn");
  const tbody = document.getElementById("record-items-tbody");

  // ✅ 한 번만 등록 (중복 등록 방지)
  if (!tbody.dataset.clickBound) {
    tbody.dataset.clickBound = "1";

    tbody.addEventListener("click", (e) => {
        const tr = e.target.closest("tr.food-row");
        if (!tr) return;

        tr.classList.toggle("is-selected");

        // 디버깅용(선택 확인)
        console.log("[select] food_id=", tr.dataset.foodId, "selected=", tr.classList.contains("is-selected"));
    });
}

  console.log("[food_search] elems", { inputEl, btnEl, tbody });

  if (!inputEl || !btnEl || !tbody) {
    console.warn("[food_search] required elements not found");
    return;
  }

  const safeNum = (v) => {
    if (v === null || v === undefined) return "0";
    const n = Number(v);
    if (Number.isNaN(n)) return "0";
    return String(n);
  };

  async function runSearch() {
    const q = (inputEl.value || "").trim();
    console.log("[food_search] runSearch q=", q);

    tbody.innerHTML = "";
    if (!q) return;

    const url = `/record/api/foods/search/?q=${encodeURIComponent(q)}`;
    console.log("[food_search] fetch", url);

    const res = await fetch(url, { method: "GET" });
    console.log("[food_search] status", res.status);

    if (!res.ok) {
      const t = await res.text().catch(() => "");
      console.error("[food_search] API error", res.status, t);
      return;
    }

    const data = await res.json();
    console.log("[food_search] data", data);

    const items = data.items || [];

    tbody.innerHTML = items.map((it, idx) => `
      <tr class="food-row" data-food-id="${it.food_id}">
        <td>${idx + 1}</td>
        <td>${it.name ?? ""}</td>
        <td>${it.kcal ?? 0}</td>
        <td>${it.carb_g ?? 0}</td>
        <td>${it.protein_g ?? 0}</td>
        <td>${it.fat_g ?? 0}</td>
      </tr>
    `).join("");
  }

  btnEl.addEventListener("click", (e) => {
    e.preventDefault();
    console.log("[food_search] click fired");
    runSearch().catch(console.error);
  });

  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      console.log("[food_search] enter fired");
      runSearch().catch(console.error);
    }
  });
});

function getSelectedFoodIds() {
  return Array.from(document.querySelectorAll("tr.food-row.is-selected"))
    .map(tr => Number(tr.dataset.foodId))
    .filter(n => !Number.isNaN(n) && n > 0);
}