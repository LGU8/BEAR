// static/js/record_food/food_search.js
console.log("[food_search] FILE EXECUTED v=20260107-1");

document.addEventListener("DOMContentLoaded", () => {
  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(";").shift();
    return "";
  }

  // ✅ HTML escape (제품명 안전 처리)
  const safeText = (s) =>
    String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");

  const safeNum = (v) => {
    if (v === null || v === undefined) return "0";
    const n = Number(v);
    if (Number.isNaN(n)) return "0";
    return String(n);
  };

  const inputEl = document.getElementById("food-search-input");
  const btnEl = document.getElementById("food-search-btn");
  const tbody = document.getElementById("record-items-tbody");
  const selectedBar = document.getElementById("selected-bar");
  const saveBtn = document.getElementById("btn-save-meal");

  const sumKcalEl = document.getElementById("sum-kcal");
  const sumCarbEl = document.getElementById("sum-carb");
  const sumProteinEl = document.getElementById("sum-protein");
  const sumFatEl = document.getElementById("sum-fat");

  // ✅ 권장 칼로리 대비 progress (있으면 사용, 없으면 자동 스킵)
  const recoKcalEl = document.getElementById("ctx-reco-kcal");
  const kcalProgressWrap = document.getElementById("kcal-progress");
  const kcalPercentEl = document.getElementById("kcal-percent");
  const kcalNowEl = document.getElementById("kcal-now");
  const kcalRecoEl = document.getElementById("kcal-reco");
  const kcalFillEl = document.getElementById("kcal-progress-fill");
  const kcalBarEl = document.querySelector(".kcal-progress-bar");

  console.log("[food_search] DOMContentLoaded href=", location.href);
  console.log("[food_search] elems", { inputEl, btnEl, tbody, selectedBar, saveBtn });

  if (!inputEl || !btnEl || !tbody) {
    console.warn("[food_search] required elements not found");
    return;
  }

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

  function syncCheckbox(foodId, checked) {
    const cb = document.querySelector(`.row-check[data-food-id="${foodId}"]`);
    if (cb) cb.checked = checked;
  }

  function getRecoKcal() {
    const raw = (recoKcalEl?.value || "").trim();
    const n = Number(raw);
    return Number.isFinite(n) && n > 0 ? n : 0;
  }

  function renderKcalProgress(sumKcalRounded) {
    // progress UI가 없으면 그냥 스킵
    if (!kcalProgressWrap || !kcalFillEl || !kcalPercentEl || !kcalNowEl || !kcalRecoEl) return;

    const reco = getRecoKcal();
    if (!reco) {
      // 권장 칼로리가 없으면 숨김
      kcalProgressWrap.style.display = "none";
      return;
    }

    kcalProgressWrap.style.display = "";

    const now = Number(sumKcalRounded || 0);
    const pct = Math.round((now / reco) * 100);
    const clamped = Math.max(0, Math.min(pct, 100)); // bar는 0~100까지만

    kcalPercentEl.textContent = String(pct);
    kcalNowEl.textContent = String(now);
    kcalRecoEl.textContent = String(reco);

    kcalFillEl.style.width = `${clamped}%`;

    if (kcalBarEl) {
      kcalBarEl.setAttribute("aria-valuenow", String(clamped));
      kcalBarEl.setAttribute("aria-valuemin", "0");
      kcalBarEl.setAttribute("aria-valuemax", "100");
    }
  }

  function renderSelectedSummary() {
    if (!sumKcalEl || !sumCarbEl || !sumProteinEl || !sumFatEl) {
      // 합계 영역이 없더라도 progress는 계산 가능하니 아래는 진행
      // (하지만 지금은 sum DOM이 있어야 의미 있으므로 그대로 종료)
      return;
    }

    let kcal = 0,
      carb = 0,
      protein = 0,
      fat = 0;

    selectedMap.forEach((it) => {
      kcal += Number(it.kcal || 0);
      carb += Number(it.carb_g || 0);
      protein += Number(it.protein_g || 0);
      fat += Number(it.fat_g || 0);
    });

    const kcalR = Math.round(kcal);
    const carbR = Math.round(carb);
    const proteinR = Math.round(protein);
    const fatR = Math.round(fat);

    sumKcalEl.textContent = String(kcalR);
    sumCarbEl.textContent = String(carbR);
    sumProteinEl.textContent = String(proteinR);
    sumFatEl.textContent = String(fatR);

    // ✅ progress 동기화
    renderKcalProgress(kcalR);
  }

  function renderSelectedBar() {
    if (!selectedBar) return;

    if (selectedMap.size === 0) {
      selectedBar.innerHTML = `<span class="selected-bar-empty">선택된 메뉴가 없습니다.</span>`;
      renderSelectedSummary();
      return;
    }

    const chips = Array.from(selectedMap.values())
      .map(
        (item) => `
        <span class="selected-chip" data-food-id="${item.food_id}">
          ${item.name}
          <button type="button" class="chip-remove" aria-label="삭제">✕</button>
        </span>
      `
      )
      .join("");

    selectedBar.innerHTML = chips;
    renderSelectedSummary();
  }

  function addFromRow(tr, checked) {
    const foodId = Number(tr.dataset.foodId);
    if (!foodId) return;

    if (checked) {
      // ✅ 핵심: dataset에서 kcal/carb/protein/fat 읽기 (runSearch에서 data-*를 심어줘야 함)
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

  function resetAfterSave() {
    // 1) 선택 상태 초기화
    selectedMap.clear();
    renderSelectedBar(); // 내부에서 summary+progress도 같이 갱신됨

    // 2) 입력창 초기화(원하면)
    inputEl.value = "";

    // 3) 테이블을 "첫 화면"처럼 비우기
    renderEmptyState();

    // 4) 스크롤 위치도 위로
    const tableWrap = document.querySelector(".table-wrap");
    if (tableWrap) tableWrap.scrollTop = 0;
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

    // ✅ 렌더링 (핵심 수정: data-kcal/data-carb/data-protein/data-fat 주입)
    tbody.innerHTML = items
      .map(
        (it) => `
        <tr class="food-row"
          data-food-id="${it.food_id}"
          data-name="${safeText(it.name)}"
          data-kcal="${safeNum(it.kcal)}"
          data-carb="${safeNum(it.carb_g)}"
          data-protein="${safeNum(it.protein_g)}"
          data-fat="${safeNum(it.fat_g)}"
        >
          <td class="col-check-cell">
            <input class="row-check" type="checkbox" data-food-id="${it.food_id}">
          </td>
          <td>${safeText(it.name)}</td>
          <td>${it.kcal ?? 0}</td>
          <td>${it.carb_g ?? 0}</td>
          <td>${it.protein_g ?? 0}</td>
          <td>${it.fat_g ?? 0}</td>
        </tr>
      `
      )
      .join("");

    restoreChecksAfterRender();
  }

  // ===== 저장 버튼 =====
  if (saveBtn) {
    saveBtn.addEventListener("click", async () => {
      const foodIds = Array.from(selectedMap.keys());
      console.log("[meal_save] selected foodIds =", foodIds);

      if (foodIds.length === 0) {
        alert("음식을 선택해주세요.");
        return;
      }

      const csrfToken = getCookie("csrftoken");
      if (!csrfToken) {
        alert("CSRF 토큰이 없습니다. 페이지를 새로고침(F5) 후 다시 시도해주세요.");
        console.warn("[meal_save] csrftoken cookie missing. document.cookie=", document.cookie);
        return;
      }

      console.log("[meal_save] csrfToken(cookie) =", csrfToken);

      const res = await fetch("/record/api/meal/save/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify({ food_ids: foodIds }),
      });

      const data = await res.json().catch(() => null);
      console.log("[meal_save] status=", res.status, "data=", data);

      if (!res.ok || !data?.ok) {
        alert("저장 실패");
        return;
      }

      // ✅ 저장 성공 → 홈으로 이동
      const go = data.redirect_url || "/home/";
      console.log("[meal_save] redirect to =", go);
      window.location.replace(go);
      return;
    });
  }

  // ===== 초기 화면 =====
  renderEmptyState();
  renderSelectedBar(); // 내부에서 summary/progress 포함

  // ===== 검색 버튼/엔터 =====
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

  // ===== 체크 변경 =====
  tbody.addEventListener("change", (e) => {
    const cb = e.target.closest(".row-check");
    if (!cb) return;

    const tr = cb.closest("tr.food-row");
    if (!tr) return;

    tr.classList.toggle("is-selected", cb.checked);
    addFromRow(tr, cb.checked);
  });

  // ===== row 클릭 토글 =====
  tbody.addEventListener("click", (e) => {
    const tr = e.target.closest("tr.food-row");
    if (!tr) return;

    if (e.target.classList.contains("row-check")) return;

    const cb = tr.querySelector(".row-check");
    if (!cb) return;

    cb.checked = !cb.checked;
    cb.dispatchEvent(new Event("change", { bubbles: true }));
  });

  // ===== 선택 바에서 X 누르면 해제 =====
  if (selectedBar) {
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
});
