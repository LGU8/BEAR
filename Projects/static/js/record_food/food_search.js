// static/js/record_food/food_search.js
console.log("[food_search] FILE EXECUTED v=20251222-3");

document.addEventListener("DOMContentLoaded", () => {

  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(";").shift();
    return "";
  }

  // ✅ HTML escape (제품명 안전 처리)
  const safeText = (s) => String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

  const inputEl = document.getElementById("food-search-input");
  const btnEl = document.getElementById("food-search-btn");
  const tbody = document.getElementById("record-items-tbody");
  const selectedBar = document.getElementById("selected-bar");
  const saveBtn = document.getElementById("btn-save-meal");
  const rgsDt = (document.getElementById("ctx-rgs-dt")?.value || "").trim();
  const seq = (document.getElementById("ctx-seq")?.value || "").trim();
  const timeSlot = (document.getElementById("ctx-time-slot")?.value || "").trim();

  
  console.log("[food_search] DOMContentLoaded href=", location.href);
  console.log("[food_search] elems", { inputEl, btnEl, tbody, selectedBar });
  console.log("[meal_save] saveBtn", saveBtn);

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

  const selectedMap = new Map(); // foodId -> item

  function renderEmptyState() {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" style="text-align:center; padding:12px; opacity:0.7;">
          검색어를 입력하고 Search를 눌러주세요.
        </td>
      </tr>
    `;
  }

  function resetAfterSave() {
    // 1) 선택 상태 초기화
    selectedMap.clear();
    renderSelectedBar();

    // 2) 입력창 초기화(원하면)
    if (inputEl) inputEl.value = "";

    // 3) 테이블을 "첫 화면"처럼 비우기
    renderEmptyState(); // ✅ 이게 제일 자연스러움 (tbody.innerHTML="" 대신)

    // 4) 스크롤 위치도 위로
    const tableWrap = document.querySelector(".table-wrap");
    if (tableWrap) tableWrap.scrollTop = 0;
  }

  function syncCheckbox(foodId, checked) {
    const cb = document.querySelector(`.row-check[data-food-id="${foodId}"]`);
    if (cb) cb.checked = checked;
  }

  function renderSelectedBar() {
    if (!selectedBar) return;

    if (selectedMap.size === 0) {
      selectedBar.innerHTML = `<span class="selected-bar-empty">선택된 메뉴가 없습니다.</span>`;
      return;
    }

    const chips = Array.from(selectedMap.values()).map(item => `
      <span class="selected-chip" data-food-id="${item.food_id}">
        ${item.name}
        <button type="button" class="chip-remove" aria-label="삭제">✕</button>
      </span>
    `).join("");

    selectedBar.innerHTML = chips;
  }

  function addFromRow(tr, checked) {
    const foodId = Number(tr.dataset.foodId);
    if (!foodId) return;

    if (checked) {
      selectedMap.set(foodId, {
        food_id: foodId,
        name: tr.dataset.name || "",
        kcal: Number(tr.dataset.kcal || 0),
        carb_g: Number(tr.dataset.carb || 0),
        protein_g: Number(tr.dataset.protein || 0),
        fat_g: Number(tr.dataset.fat || 0),
      });
    } else {
      selectedMap.delete(foodId);
    }

    renderSelectedBar();
  }

  function restoreChecksAfterRender() {
    selectedMap.forEach((_, foodId) => {
      syncCheckbox(foodId, true);

      // ✅ 행 강조도 같이 복원
      const tr = document.querySelector(`tr.food-row[data-food-id="${foodId}"]`);
      if (tr) tr.classList.add("is-selected");
    });
  }

  function getSelectedFoodIds() {
    return Array.from(selectedMap.keys());
  }

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

    // ✅ 렌더링
    tbody.innerHTML = items.map((it) => `
      <tr class="food-row"
        data-food-id="${it.food_id}"
        data-name="${safeText(it.name)}">
      <td class="col-check-cell">
        <input class="row-check" type="checkbox" data-food-id="${it.food_id}">
      </td>
      <td>${safeText(it.name)}</td>
      <td>${it.kcal ?? 0}</td>
      <td>${it.carb_g ?? 0}</td>
      <td>${it.protein_g ?? 0}</td>
      <td>${it.fat_g ?? 0}</td>
    </tr>
  `).join("");

  restoreChecksAfterRender();

  }

  saveBtn.addEventListener("click", async () => {
    if (!rgsDt || !seq || !timeSlot) {
      alert("감정 기록(session)이 없어서 저장할 수 없어요. 감정 기록부터 진행해 주세요.");
      return;
    }

    const foodIds = Array.from(selectedMap.keys()); // 네 코드 구조에 맞춰 유지
    if (foodIds.length === 0) {
      alert("저장할 항목을 선택해 주세요.");
      return;
    }

    const csrfToken = document.querySelector("input[name=csrfmiddlewaretoken]")?.value;

    console.log("[meal_save] payload", {
      rgs_dt: rgsDt, seq, time_slot: timeSlot, food_ids: foodIds
    });

    const res = await fetch("/record/api/meal/save/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      credentials: "same-origin",
      body: JSON.stringify({
        food_ids: foodIds,
      }),
    });

    const data = await res.json().catch(() => null);
    if (!res.ok || !data?.ok) {
      alert(data?.message || "저장 실패");
      return;
    }

    alert("저장 완료!");

    // ✅ 저장 성공 후 선택 초기화
    selectedMap.clear();
    renderSelectedBar();

    // 테이블에 남아있는 체크/강조도 초기화
    tbody.querySelectorAll(".row-check").forEach(cb => (cb.checked = false));
    tbody.querySelectorAll("tr.food-row.is-selected").forEach(tr => tr.classList.remove("is-selected"));
  });

  renderEmptyState();

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

  tbody.addEventListener("change", (e) => {
    const cb = e.target.closest(".row-check");
    if (!cb) return;

    const tr = cb.closest("tr.food-row");
    if (!tr) return;

    // ✔ 체크 상태에 따라 행 강조
    tr.classList.toggle("is-selected", cb.checked);

    // ✔ 선택 상태 갱신
    addFromRow(tr, cb.checked);
  });

  tbody.addEventListener("click", (e) => {
    const tr = e.target.closest("tr.food-row");
    if (!tr) return;

    // checkbox 자체를 클릭한 경우는 change에서 처리
    if (e.target.classList.contains("row-check")) return;

    const cb = tr.querySelector(".row-check");
    if (!cb) return;

    cb.checked = !cb.checked;

    // ✅ 핵심: row 클릭으로 토글했을 때도 change 로직이 돌도록
    cb.dispatchEvent(new Event("change", { bubbles: true }));
  });

  // 선택 바에서 X 누르면 해제
  if(selectedBar) {
    selectedBar.addEventListener("click", (e) => {
      if (!e.target.classList.contains("chip-remove")) return;

      const chip = e.target.closest(".selected-chip");
      if (!chip) return;

      const foodId = Number(chip.dataset.foodId);
      selectedMap.delete(foodId);
      syncCheckbox(foodId, false);

      const tr = document.querySelector(`tr.food-row[data-food-id="${foodId}"]`);
      if (tr) tr.classList.remove("is-selected");

      renderSelectedBar();
    });
  }

  // 초기 상태
  renderSelectedBar();

});