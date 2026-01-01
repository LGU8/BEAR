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
  // ✅ 1) meal 버튼 클릭 이벤트 연결
  bindMealButtons();

  // ✅ 2) 최초 진입 시 현재 meal을 active 처리
  const date = getActiveDate();
  const meal = getActiveMeal();

  // ✅ (추가) camera에서 focus=search로 돌아온 경우 검색창에 커서
  const params = new URLSearchParams(location.search);
  if (params.get("focus") === "search") {
    const input = document.getElementById("food-search-input");
    if (input) {
      input.focus();
      input.scrollIntoView({ block: "center", behavior: "smooth" });
    } else {
      console.warn("[record] #food-search-input not found");
    }
  }

  const buttons = document.querySelectorAll(".meal-btn");
  buttons.forEach(b => b.classList.remove("is-active"));
  const initBtn = document.querySelector(`.meal-btn[data-meal="${meal}"]`);
  if (initBtn) initBtn.classList.add("is-active");

  const cardsWrap = document.getElementById("recent-cards");
  if (!cardsWrap) {
    console.warn("[record_state] #recent-cards not found");
    return;
  }

  const cards = cardsWrap.querySelectorAll(".meal-card");

  function resetCards() {
    cards.forEach(card => {
      card.classList.add("empty");
      const textEl = card.querySelector(".meal-card-text");
      if (textEl) textEl.innerHTML = "아직 기록 전입니다.<br>기록을 남겨보세요!";
    });
  }

  resetCards();

  const historyKey = `mealHistory:${meal}`;
  const historyRaw = localStorage.getItem(historyKey);
  if (!historyRaw) {
    console.warn("[record_state] no history:", historyKey);
    return;
  }

  let history;
  try {
    history = JSON.parse(historyRaw);
  } catch (e) {
    console.error("[record_state] history JSON parse error", e);
    return;
  }

  if (!Array.isArray(history) || history.length === 0) {
    console.warn("[record_state] history empty:", historyKey);
    return;
  }

  history.slice(0, 3).forEach((snap, idx) => {
    const card = cards[idx];
    if (!card) return;

    card.classList.remove("empty");

    const textEl = card.querySelector(".meal-card-text");
    if (!textEl) return;

    const items = Array.isArray(snap.items) ? snap.items : [];
    const names = items.map(it => it.name).filter(Boolean);

    const firstLine = names.slice(0, 3).join(", ");
    const more = names.length > 3 ? ` 외 ${names.length - 3}개` : "";

    textEl.innerHTML = `<strong>${snap.date}</strong><br>${firstLine}${more}`;
  });
});


// === camera 버튼: date / meal 유지해서 이동 ===
(function () {
  const camBtn = document.getElementById("btn-camera");
  if (!camBtn) return;

  camBtn.addEventListener("click", (e) => {
    e.preventDefault();

    
    // ✅ 1) hidden input에서 매번 안전하게 읽기
    const rgsDtEl = document.getElementById("ctx-rgs-dt");
    const timeSlotEl = document.getElementById("ctx-time-slot");

    const rgsDt = (rgsDtEl?.value || "").trim();
    const timeSlot = (timeSlotEl?.value || "").trim();

    // ✅ 2) 값 없으면 막고 사용자에게 안내
    if (!rgsDt || !timeSlot) {
      alert("날짜/식사시간(session)이 없어 카메라 페이지로 이동할 수 없어요. 감정 기록부터 다시 진행해 주세요.");
      console.error("[record_state] missing ctx:", { rgsDt, timeSlot });
      return;
    }

    // ✅ 3) 정상 이동
    location.href =
      `/record/camera/?rgs_dt=${encodeURIComponent(rgsDt)}` +
      `&time_slot=${encodeURIComponent(timeSlot)}`;
});
})();

// ===== 최근 3개 끼니 카드 렌더링 =====
(function () {
  const params = new URLSearchParams(location.search);
  const date = params.get("date");
  const meal = params.get("meal") || "breakfast";

  const cardsWrap = document.getElementById("recent-cards");
  if (!cardsWrap) return;

  const cards = cardsWrap.querySelectorAll(".meal-card");

  // 기본 초기화
  function resetCards() {
    cards.forEach(card => {
      card.classList.add("empty");
      const textEl = card.querySelector(".meal-card-text");
      if (textEl) {
        textEl.innerHTML = "아직 기록 전입니다.<br>기록을 남겨보세요!";
      }
    });
  }

  resetCards();

  // 끼니별 히스토리 읽기
  const historyKey = `mealHistory:${meal}`;
  const historyRaw = localStorage.getItem(historyKey);
  if (!historyRaw) return;

  let history;
  try {
    history = JSON.parse(historyRaw);
  } catch {
    return;
  }

  if (!Array.isArray(history) || history.length === 0) return;

  // 최근 3개만 카드에 반영
  history.slice(0, 3).forEach((snap, idx) => {
    const card = cards[idx];
    if (!card) return;

    card.classList.remove("empty");

    const textEl = card.querySelector(".meal-card-text");
    if (!textEl) return;

    const items = Array.isArray(snap.items) ? snap.items : [];

    // 음식 이름 요약
    const names = items.map(it => it.name).filter(Boolean);
    const firstLine = names.slice(0, 3).join(", ");
    const more = names.length > 3 ? ` 외 ${names.length - 3}개` : "";

    textEl.innerHTML = `
      <strong>${snap.date}</strong><br>
      ${firstLine}${more}
    `;
  });
})();

// 바코드 인식 -> record page로 돌아와서 검색창에 focus.
(function () {
  const params = new URLSearchParams(location.search);
  if (params.get("focus") !== "search") return;

  const input = document.getElementById("food-search-input");
  if (!input) return;

  input.focus();
})();