document.addEventListener("DOMContentLoaded", () => {

  /* ======================================================
     공통: has_data 카드 제어
     ====================================================== */
  function handleHasData({ cardId, chartWrapId, emptyId }) {
    const card      = document.getElementById(cardId);
    const chartWrap = document.getElementById(chartWrapId);
    const emptyBox  = document.getElementById(emptyId);

    if (!card) return false;

    const hasData = card.dataset.hasData === "1";

    if (!hasData) {
    chartWrap?.style && (chartWrap.style.display = "none"); // 👈 여기
    emptyBox?.style  && (emptyBox.style.display  = "flex"); // 👈 여기
    return false;
    }

    chartWrap?.style && (chartWrap.style.display = "block");
    emptyBox?.style  && (emptyBox.style.display  = "none");
    return true;
  }


  /* ======================================================
     1. 오늘의 요약 카드
     ====================================================== */
  (function () {
    const card = document.getElementById("daily-feedback-card");
    if (!card) return;

    const hasData = card.dataset.hasData === "1";

    const normalCard = card.querySelector(".feedback-card:not(.card-empty)");
    const emptyCard  = card.querySelector(".feedback-card.card-empty");

    if (hasData) {
    normalCard.style.display = "";
    emptyCard.style.display  = "none";
    } else {
    normalCard.style.display = "none";
    emptyCard.style.display  = "";
    }
  })();

  /* ======================================================
     2. 영양소 카드
     ====================================================== */
  const canRenderNutrition = handleHasData({
    cardId: "daily-nutrition-card",
    chartWrapId: "daily-nutrition-chart-wrap",
    emptyId: "daily-nutrition-empty"
  });

  if (!canRenderNutrition) return;

  const card = document.getElementById("daily-nutrition-card");

  /* ======================================================
     3. 영양소 데이터 파싱
     ====================================================== */
  const nutEl = card.querySelector("#report-nut-data");
  if (!nutEl) return;

  const nutritionData = JSON.parse(nutEl.dataset.nutDay || "{}");
  const total = nutritionData.total || {};
  const recom = nutritionData.recom || {};

  const COLOR_FULL = "#F47900";
  const COLOR_LOW  = "#FFA636";

  /* ======================================================
     3. 요약(progress bar) 렌더
     ====================================================== */
  card.querySelectorAll(".nut-row").forEach(row => {
    const key = row.dataset.nutrient; // kcal | carb | protein | fat
    const bar = row.querySelector(".nut-bar span");
    const txt = row.querySelector(".nut-text");

    if (!bar || !txt) return;

    const intake = total[key] ?? 0;
    const target = recom[key];

    if (!target) return;

    const percent = Math.min((intake / target) * 100, 100);
    bar.style.width = `${percent}%`;
    bar.style.backgroundColor =
      intake >= target ? COLOR_FULL : COLOR_LOW;

    txt.textContent =
      key === "kcal"
        ? `${intake} / ${target} kcal`
        : `${intake} / ${target} g`;
  });

  /* ======================================================
     4. 요약 / 자세히 토글 (🔥 카드 내부 기준)
     ====================================================== */
  const toggleBtns = card.querySelectorAll(".nut-sum-type-toggle .toggle-btn");
  const summaryBox = card.querySelector(".summary-content");
  const detailBox  = card.querySelector(".detail-content");

  toggleBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      toggleBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");

      const isSummary = btn.dataset.target === "summary";
      summaryBox.style.display = isSummary ? "block" : "none";
      detailBox.style.display  = isSummary ? "none"  : "block";
    });
  });

  /* ======================================================
     5. 끼니별 도넛 차트
     ====================================================== */
  const MEAL_MAP = { morning: "M", lunch: "L", dinner: "D" };
  const mealBtns = card.querySelectorAll(".meal-btn");
  const menuText = card.querySelector(".meal-menu-text");

  let donutChart = null;

  const centerTextPlugin = {
    id: "centerText",
    beforeDraw(chart) {
      const text = chart.options.plugins.centerText?.text;
      if (!text) return;

      const { ctx, width, height } = chart;
      ctx.save();
      ctx.font = "700 18px Inter, sans-serif";
      ctx.fillStyle = "#3C3C43";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(text, width / 2, height / 2);
      ctx.restore();
    }
  };

  function renderDonut(mealKey) {
    const data = nutritionData[mealKey];
    if (!data) return;

    menuText.textContent = data.f_name || "기록된 메뉴가 없어요";

    const canvas = card.querySelector("#macroDonutChart");
    if (!canvas || !window.Chart) return;

    donutChart?.destroy();

    donutChart = new Chart(canvas.getContext("2d"), {
      type: "doughnut",
      data: {
        labels: ["탄수화물", "단백질", "지방"],
        datasets: [{
          data: [data.carb, data.protein, data.fat],
          backgroundColor: ["#FFD07C", "#FFE2B6", "#FFB845"],
          borderWidth: 0
        }]
      },
      options: {
        cutout: "65%",
        animation: false,
        plugins: {
          legend: { display: false },
          centerText: { text: `${data.kcal} kcal` }
        }
      },
      plugins: [centerTextPlugin]
    });
  }

  mealBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      mealBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");

      const key = MEAL_MAP[btn.dataset.meal];
      if (key) renderDonut(key);
    });
  });

  /* 초기 렌더: 아침 */
  card.querySelector('.meal-btn[data-meal="morning"]')?.click();

  /* ======================================================
     6. 기분 카드
     ====================================================== */
  const moodCard = document.getElementById("daily-mood-card");
  if (!moodCard) return;

  const hasData = moodCard.dataset.hasData === "1";

  const chartWrap = document.getElementById("daily-mood-chart-wrap");
  const emptyBox  = document.getElementById("weekly-mood-empty");

  if (!chartWrap || !emptyBox) return;

  if (!hasData) {
    chartWrap.style.display = "none";
    emptyBox.style.display  = "flex";
    return;
  }

  chartWrap.style.display = "grid";
  emptyBox.style.display  = "none";

  /* 데이터 파싱 */
  const moodEl = document.getElementById("report-mood-data");
  if (!moodEl) return;

  let rawMood;
  try {
    rawMood = JSON.parse(moodEl.dataset.moodRatio);
  } catch (e) {
    console.error("mood_ratio JSON parse error", e);
    return;
  }

  const moodData = {
    positive: rawMood.pos ?? 0,
    neutral:  rawMood.neu ?? 0,
    negative: rawMood.neg ?? 0
  };

  /* ======================================================
     7. 지배 감정 판별
     ====================================================== */
  function getDominantMood(data) {
    const entries = Object.entries(data);
    const values  = entries.map(e => e[1]);

    // 모두 동일 → 중립
    if (values.every(v => v === values[0])) return "neutral";

    // 최대값
    return entries.sort((a, b) => b[1] - a[1])[0][0];
  }

  const dominant = getDominantMood(moodData);

  /* ======================================================
     8. 캐릭터 + 문구
     ====================================================== */
  const moodImgMap = {
    positive: "/static/icons_img/긍정.png",
    neutral:  "/static/icons_img/중립.png",
    negative: "/static/icons_img/부정.png"
  };

  const moodTextMap = {
    positive: "오늘은 긍정 감정을 많이 느꼈어요 😊",
    neutral:  "오늘의 감정은 무난했어요 🙂",
    negative: "오늘은 부정 감정을 많이 느꼈어요 🥺"
  };

  const moodLabelMap = {
    positive: "긍정",
    neutral:  "중립",
    negative: "부정"
  };

  const imgBox  = moodCard.querySelector(".mood_img");
  const textBox = moodCard.querySelector(".mood_text");

  if (imgBox) {
    imgBox.innerHTML = `<img src="${moodImgMap[dominant]}" alt="${dominant}">`;
  }

  if (textBox) {
    textBox.textContent = moodTextMap[dominant];
  }

  const centerText =
  `${moodLabelMap[dominant]} ${Math.round(moodData[dominant] * 100)} %`;

  /* ======================================================
     9. 도넛 차트
     ====================================================== */
  const canvas = document.getElementById("moodDonutChart");
  if (!canvas || !window.Chart) return;

  new Chart(canvas.getContext("2d"), {
    type: "doughnut",
    data: {
      labels: ["긍정", "중립", "부정"],
      datasets: [{
        data: [
          moodData.positive,
          moodData.neutral,
          moodData.negative
        ],
        backgroundColor: [
          "#FFD07C",
          "#FFE2B6",
          "#FFB845"
        ],
        borderWidth: 0
      }]
    },
    options: {
      animation: false,
      cutout: "65%",
      plugins: {
        legend: { display: false },
        centerText: {text: centerText}
        },
      },
    plugins: [centerTextPlugin]
  });
});