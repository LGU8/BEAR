// static/js/record_state.js

// ---------- (1) Query string ----------
function getQS(name) {
  const params = new URLSearchParams(window.location.search);
  return params.get(name);
}
function getActiveDate() {
  const qsDate = getQS("date");
  if (qsDate) return qsDate;
  // fallback(보험)
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}
function getActiveMeal() {
  return getQS("meal") || "breakfast";
}

// ---------- (2) localStorage helpers ----------
function loadJSON(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (e) {
    return fallback;
  }
}
function saveJSON(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

// ---------- (3) 계산(합계) ----------
function sumMacros(items) {
  let kcal = 0, carb = 0, protein = 0, fat = 0;
  for (const it of items) {
    kcal += Number(it.kcal || 0);
    carb += Number(it.carb || 0);
    protein += Number(it.protein || 0);
    fat += Number(it.fat || 0);
  }
  return { kcal, carb, protein, fat };
}

// ---------- (4) 카드 렌더 ----------
function renderRecentMealCards(date, meal) {
  const container = document.getElementById("recent-cards");
  const tpl = document.getElementById("tpl-meal-record-card");
  if (!container || !tpl) return;

  const key = `mealRecords:${date}:${meal}`;
  const records = loadJSON(key, []); // 배열: 최신이 뒤에 저장되든 앞에 저장되든 규칙만 통일하면 됨

  // 최신 3개만 뽑기: 여기서는 "createdAt 내림차순"으로 정렬 후 상위 3개
  const sorted = [...records].sort((a, b) => {
    const ta = new Date(a.createdAt || 0).getTime();
    const tb = new Date(b.createdAt || 0).getTime();
    return tb - ta;
  });
  const top3 = sorted.slice(0, 3);

  container.innerHTML = "";

  // 기록이 0개면 빈 카드 3개 유지
  if (top3.length === 0) {
    for (let i = 0; i < 3; i++) {
      const empty = document.createElement("article");
      empty.className = "meal-record-tile is-empty";
      empty.innerHTML = `
        <div class="tile-thumb"></div>
        <div class="tile-meta">
          <div class="tile-time">아직 기록이 없습니다.</div>
          <ul class="tile-items"><li>기록을 남겨보세요!</li></ul>
        </div>`;
      container.appendChild(empty);
    }
    return;
  }

  // top3 렌더 + 남는 칸은 빈 카드로 채우기
  for (let i = 0; i < 3; i++) {
    const rec = top3[i];
    if (!rec) {
      const empty = document.createElement("article");
      empty.className = "meal-record-tile is-empty";
      empty.innerHTML = `
        <div class="tile-thumb"></div>
        <div class="tile-meta">
          <div class="tile-time">기록이 더 없습니다.</div>
          <ul class="tile-items"><li>다른 끼니를 선택해보세요.</li></ul>
        </div>`;
      container.appendChild(empty);
      continue;
    }

    const node = tpl.content.firstElementChild.cloneNode(true);
    node.dataset.recordId = rec.id || "";

    // (a) 시간 표시
    const timeEl = node.querySelector(".tile-time");
    const createdAt = rec.createdAt ? new Date(rec.createdAt) : null;
    timeEl.textContent = createdAt
      ? `${createdAt.getHours().toString().padStart(2, "0")}:${createdAt.getMinutes().toString().padStart(2, "0")}`
      : "기록 시간";

    // (b) 대표 이미지
    const imgEl = node.querySelector(".tile-img");
    const firstImgItem = (rec.items || []).find(x => x.imageDataUrl);
    if (firstImgItem && firstImgItem.imageDataUrl) {
      imgEl.src = firstImgItem.imageDataUrl;
      imgEl.style.display = "block";
    } else {
      // 기본 이미지가 있으면 여기에 경로 넣기(예: /static/nav_img/...)
      imgEl.src = ""; // 비워두면 CSS로 placeholder 처리 가능
      imgEl.style.display = "none";
    }

    // (c) items 전부 표시(단, 카드에서는 최대 4줄 + N개 더)
    const ul = node.querySelector(".tile-items");
    ul.innerHTML = "";

    const items = rec.items || [];
    const maxLines = 4;
    const shown = items.slice(0, maxLines);

    for (const it of shown) {
      const li = document.createElement("li");
      // 식품/레시피 공통 이름 필드: name
      li.textContent = it.name || "(이름 없음)";
      ul.appendChild(li);
    }

    if (items.length > maxLines) {
      const li = document.createElement("li");
      li.textContent = `+ ${items.length - maxLines}개 더`;
      ul.appendChild(li);
    }

    // (d) 요약
    const { kcal, carb, protein, fat } = sumMacros(items);
    node.querySelector(".sum-kcal").textContent = `${kcal} kcal`;
    node.querySelector(".sum-macro").textContent = `C ${carb}g · P ${protein}g · F ${fat}g`;

    container.appendChild(node);
  }
}

// ---------- (5) 끼니 버튼 클릭 연결 ----------
function bindMealButtons() {
  const buttons = document.querySelectorAll(".meal-btn");
  buttons.forEach(btn => {
    btn.addEventListener("click", () => {
      const date = getActiveDate();
      const meal = btn.dataset.meal;

      // URL도 업데이트(추천): 뒤로가기/디버깅 쉬움
      const url = new URL(window.location.href);
      url.searchParams.set("date", date);
      url.searchParams.set("meal", meal);
      history.replaceState({}, "", url.toString());

      // 버튼 active UI(원하면 CSS에서 .is-active 활용)
      buttons.forEach(b => b.classList.remove("is-active"));
      btn.classList.add("is-active");

      renderRecentMealCards(date, meal);
    });
  });
}

// ---------- (6) 초기 실행 ----------
document.addEventListener("DOMContentLoaded", () => {
  const date = getActiveDate();
  const meal = getActiveMeal();

  // hidden input에 date 넣기(필요 시)
  const dateInput = document.getElementById("record-date");
  if (dateInput) dateInput.value = date;

  // 현재 meal 버튼 활성화
  const btn = document.querySelector(`.meal-btn[data-meal="${meal}"]`);
  if (btn) btn.classList.add("is-active");

  // 링크들에 query 유지(레시피/카메라)
  const recipeBtn = document.getElementById("btn-my-recipe");
  if (recipeBtn) recipeBtn.href = `/record/recipes/?date=${encodeURIComponent(date)}&meal=${encodeURIComponent(meal)}`;

  const camBtn = document.getElementById("btn-camera");
  if (camBtn) camBtn.href = `/record/camera/?date=${encodeURIComponent(date)}&meal=${encodeURIComponent(meal)}`;

  bindMealButtons();
  renderRecentMealCards(date, meal);
});
