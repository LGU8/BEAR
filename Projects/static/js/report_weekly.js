document.addEventListener("DOMContentLoaded", () => {

  /* ======================================================
     공통: has_data 제어
     ====================================================== */
  function handleHasData({ cardId, chartWrapId, emptyId }) {
    const card      = document.getElementById(cardId);
    const chartWrap = document.getElementById(chartWrapId);
    const emptyBox  = document.getElementById(emptyId);

    if (!card) return false;

    const hasData = card.dataset.hasData === "1";

    if (!hasData) {
      chartWrap?.style && (chartWrap.style.display = "none");
      emptyBox?.style  && (emptyBox.style.display  = "flex");
      return false;
    }

    chartWrap?.style && (chartWrap.style.display = "block");
    emptyBox?.style  && (emptyBox.style.display  = "none");
    return true;
  }

  /* ======================================================
   오늘의 요약 카드 (피드백)
   ====================================================== */
  (function () {
    const card = document.getElementById("weekly-feedback-card");
    if (!card) return;

    const hasData = card.dataset.hasData === "1";

    const normalText = card.querySelector(".feedback-card:not(.card-empty)");
    const emptyText  = card.querySelector("#weekly-feedback-empty");

    if (hasData) {
    normalText.style.display = "";
    emptyText.style.display  = "none";
    } else {
    normalText.style.display = "none";
    emptyText.style.display  = "";
    }
  })();

  /* ======================================================
     공통 상수
     ====================================================== */
  const LABELS = ["월", "화", "수", "목", "금", "토", "일"];
  const COLOR_ACTIVE   = "#FC9027";
  const COLOR_INACTIVE = "#FFD17C";
  const COLOR_EMPTY    = "#C7C7CC";

  /* ======================================================
     영양소 카드
     ====================================================== */
  const canRenderNutrition = handleHasData({
    cardId: "weekly-nutrition-card",
    chartWrapId: "weekly-nutrition-chart-wrap",
    emptyId: "weekly-nutrition-empty"
  });
  if (!canRenderNutrition) return;

  const nutCard = document.getElementById("weekly-nutrition-card");
  const nutRaw  = JSON.parse(nutCard.dataset.nutWeek);

  const nutritionData = ["kcal","carb","protein","fat"]
    .reduce((acc, key) => {
      acc[key] = Object.values(nutRaw).map(d => d[key] === 0 ? null : d[key]);
      return acc;
    }, {});

  function isEmptyNutritionDay(i) {
    return Object.values(nutritionData).every(arr => arr[i] === null);
  }

  function xTickColor(ctx) {
    return isEmptyNutritionDay(ctx.index) ? COLOR_EMPTY : "#444";
  }

  const nutCtx = document
    .getElementById("weeklyNutritionChart")
    .getContext("2d");

  let activeType = "kcal";
  let nutritionChart = null;

  function createNutritionDataset(type, yAxisID) {
    const isActive = type === activeType;

    return {
      data: nutritionData[type],
      spanGaps: true,
      tension: 0.35,
      borderColor: isActive ? COLOR_ACTIVE : COLOR_INACTIVE,
      borderWidth: isActive ? 3 : 2.5,
      pointRadius: ctx => ctx.raw === null ? 0 : (isActive ? 4 : 3),
      pointBackgroundColor: ctx =>
        ctx.raw === null ? "#6f6f6f" : (isActive ? COLOR_ACTIVE : COLOR_INACTIVE),
      fill: false,
      yAxisID
    };
  }

  function renderNutritionChart() {
    nutritionChart?.destroy();

    nutritionChart = new Chart(nutCtx, {
      type: "line",
      data: {
        labels: LABELS,
        datasets: [
          createNutritionDataset("kcal", "yKcal"),
          createNutritionDataset("carb", "yGram"),
          createNutritionDataset("protein", "yGram"),
          createNutritionDataset("fat", "yGram")
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              color: xTickColor,
              font: { size: 14, weight: "600" }
            }
          },
          yKcal: {
            position: "left",
            beginAtZero: true,
            display: activeType === "kcal",
            grace: "25%",
            ticks: { display: false },
            grid: { color: "rgba(0,0,0,0.1)" }
          },
          yGram: {
            position: "right",
            beginAtZero: true,
            display: activeType !== "kcal",
            grace: "25%",
            ticks: { display: false },
            grid: { color: "rgba(0,0,0,0.1)" }
          }
        }
      }
    });
  }

  document.querySelectorAll(".nut-type-toggle .toggle-btn")
    .forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".nut-type-toggle .toggle-btn")
          .forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        activeType = btn.dataset.target;
        renderNutritionChart();
      });
    });

  renderNutritionChart();

  /* ======================================================
     기분 카드
     ====================================================== */
  const canRenderMood = handleHasData({
    cardId: "weekly-mood-card",
    chartWrapId: "weekly-mood-chart-wrap",
    emptyId: "weekly-mood-empty"
  });
  if (!canRenderMood) return;

  const moodCard = document.getElementById("weekly-mood-card");
  const moodRaw  = JSON.parse(moodCard.dataset.moodWeek);
  const overLast = moodCard.dataset.overLast === "true";

  function extractPosArray(start) {
    return Object.values(moodRaw)
      .slice(start, start + 7)
      .map(d => (d.pos + d.neu + d.neg === 0) ? null : Math.round(d.pos * 100));
  }

  const moodDatasets = [{
    label: "저번 주",
    data: extractPosArray(7),
    spanGaps: true,
    tension: 0.35,
    borderColor: COLOR_ACTIVE,
    borderWidth: 3,
    pointRadius: ctx => ctx.raw === null ? 0 : 4,
    pointBackgroundColor: COLOR_ACTIVE,
    fill: false
  }];

  if (overLast) {
    moodDatasets.push({
      label: "2주 전",
      data: extractPosArray(0),
      spanGaps: true,
      tension: 0.35,
      borderColor: "#FFD17C",
      borderDash: [5, 5],
      borderWidth: 3,
      pointRadius: ctx => ctx.raw === null ? 0 : 3,
      pointBackgroundColor: "#FFD17C",
      fill: false
    });
  } else {
    document.querySelector(".legend-prev-week")?.style &&
      (document.querySelector(".legend-prev-week").style.opacity = 0.3);
  }

  new Chart(
    document.getElementById("weeklyMoodChart").getContext("2d"),
    {
      type: "line",
      data: { labels: LABELS, datasets: moodDatasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              color: xTickColor,
              font: { size: 14, weight: "600" }
            }
          },
          y: {
            beginAtZero: true,
            grace: "5%",
            ticks: { display: false },
            grid: { color: "rgba(0,0,0,0.1)" }
          }
        }
      }
    }
  );

});
