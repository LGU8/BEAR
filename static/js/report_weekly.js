document.addEventListener("DOMContentLoaded", () => {

  /* 버튼 */
  const nutTypeButtons = document.querySelectorAll(".nut-type-toggle .toggle-btn");

  /* 더미 데이터 */
  const weeklyNutritionData = {
    labels: ["월", "화", "수", "목", "금", "토", "일"],
    kcal:    [1800, 1950, 1700, 2000, 2100, 2300, 1900],
    carb:    [220, 240, 210, 260, 270, 300, 230],
    protein: [90,  100, 95,  110, 120, 130, 105],
    fat:     [50,  55,  48,  60,  65,  70,  58]
  };

  const NUT_LABEL_MAP = {
    kcal: "칼로리",
    carb: "탄수화물",
    protein: "단백질",
    fat: "지방"
  };

  const COLOR_ACTIVE   = "#FC9027"; // 진한 주황
  const COLOR_INACTIVE = "#FFD17C"; // 연한 주황

  const NutCanvas = document.getElementById("weeklyNutritionChart");
  if (!NutCanvas || !window.Chart) return;

  const ctx = NutCanvas.getContext("2d");

  let activeType = "kcal";
  let weeklyChart = null;

  function renderWeeklyNutritionChart(active) {
    if (weeklyChart) weeklyChart.destroy();

    weeklyChart = new Chart(ctx, {
      type: "line",
      data: {
        labels: weeklyNutritionData.labels,
        datasets: [
          createDataset("kcal",    "yKcal", active),
          createDataset("carb",    "yGram", active),
          createDataset("protein", "yGram", active),
          createDataset("fat",     "yGram", active)
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              color: "#444",
              font: { size: 16, weight: "700" }
            }
          },

          /* kcal 전용 y축 (왼쪽) */
          yKcal: {
            position: "left",
            beginAtZero: true,
            display: active === "kcal",
            grace: '20%',

            title: { display: false },   // y축 제목 제거
            ticks: { display: false },   // 숫자 제거

            grid: {
              display: true,
              color: "rgba(0,0,0,0.1)"
            }
          },

          /* g 전용 y축 (오른쪽) */
          yGram: {
            position: "right",
            beginAtZero: true,
            display: active !== "kcal",
            grace: '20%',

            title: { display: false },   // y축 제목 제거
            ticks: { display: false },   // 숫자 제거

            grid: {
              display: true,
              color: "rgba(0,0,0,0.1)"
            }
          }
        }
      }
    });
  }

  function createDataset(type, yAxisID, active) {
    const isActive = type === active;

    return {
        label: NUT_LABEL_MAP[type],
        data: weeklyNutritionData[type],
        borderColor: isActive ? COLOR_ACTIVE : COLOR_INACTIVE,
        borderWidth: isActive ? 4 : 2.5,
        tension: 0.35,

        pointRadius: isActive ? 5 : 4,
        pointHoverRadius: isActive ? 6 : 5,
        pointBackgroundColor: isActive ? COLOR_ACTIVE : COLOR_INACTIVE,
        pointBorderWidth: 0,

        fill: false,
        yAxisID
        };
  }

  /* 버튼 이벤트 */
  nutTypeButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      nutTypeButtons.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");

      activeType = btn.dataset.target;
      renderWeeklyNutritionChart(activeType);
    });
  });

  /* 초기 렌더 */
  renderWeeklyNutritionChart("kcal");

/* ─────────────────────────────
   감정 그래프
   ───────────────────────────── */
  const weeklyMoodDummy = {
    thisWeek:    [60, 55, 70, 68, 72, 75, 65], // 이번 주 긍정비율
    previousWeek: [50, 52, 58, 60, 62, 64, 59] // 저저번 주 긍정비율
  };

  const weekStartStr = "{{ week_start }}";
  const weekEndStr   = "{{ week_end }}";

  const labels = ["월", "화", "수", "목", "금", "토", "일"];

  const moodData = {
    thisWeek:    [60, 55, 70, 68, 72, 75, 65],
    previousWeek: [50, 52, 58, 60, 62, 64, 59]
  };

  const MoodCanvas = document.getElementById("weeklyMoodChart");

  if (MoodCanvas && window.Chart) {
    const moodCtx = MoodCanvas.getContext("2d");

    new Chart(moodCtx, {
        type: "line",
        data: {
          labels: ["월", "화", "수", "목", "금", "토", "일"],
          datasets: [
            {
              label: " 저번 주 긍정 비율",
              data: moodData.thisWeek,
              borderColor: "#FC9027",
              borderWidth: 4,
              tension: 0.35,
              pointRadius: 4,
              pointBackgroundColor: "#FC9027",
              fill: false
            },
            {
              label: " 2주 전 긍정 비율",
              data: moodData.previousWeek,
              borderColor: "#FFD17C",
              borderWidth: 3,
              borderDash: [6, 6],
              tension: 0.35,
              pointRadius: 4,
              pointBackgroundColor: "#FFD17C",
              fill: false
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: ctx => `${ctx.dataset.label}: ${ctx.raw}%`
              }
            }
          },
          scales: {
            x: {
              grid: { display: false },
              ticks: {
                font: { size: 16, weight: "700" }
              }
            },
            y: {
              beginAtZero: true,
              max: 100,
              ticks: { stepSize: 20, display: false },
              grid: {
                color: "rgba(0,0,0,0.1)"
              }
            }
          }
        }
    });
  }
});
