// static/js/record_food/food_search.js
console.log("[food_search] FILE EXECUTED v=20251222-3");

document.addEventListener("DOMContentLoaded", () => {
  console.log("[food_search] DOMContentLoaded href=", location.href);

  const inputEl = document.getElementById("food-search-input");
  const btnEl = document.getElementById("food-search-btn");
  const tbody = document.getElementById("record-items-tbody");

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
      <tr data-food-id="${it.food_id}">
        <td>${idx + 1}</td>
        <td>${it.name ?? ""}</td>
        <td>${safeNum(it.kcal)}</td>
        <td>${safeNum(it.carb_g)}</td>
        <td>${safeNum(it.protein_g)}</td>
        <td>${safeNum(it.fat_g)}</td>
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
