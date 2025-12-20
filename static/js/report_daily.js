document.addEventListener("DOMContentLoaded", () => {
  /* 안전 체크 (디버깅용) */
  //console.log("[report_daily] DOMContentLoaded ✅");

  /* 하루 요약 영양소 더미 데이터 (DB에서 온다고 가정) */
  const nutritionData = {
    calorie: { intake: 1800, recommended: 2000, unit: "kcal" },
    carb: { intake: 220, recommended: 300, unit: "g" },
    protein: { intake: 130, recommended: 120, unit: "g" },
    fat: { intake: 70, recommended: 60, unit: "g" },
  };

  const COLOR_FULL = "#F47900"; // 권장량 충족/초과
  const COLOR_LOW = "#FFA636"; // 부족

  /* 하루 요약 막대(그래프처럼 보이는 progress) 렌더링 */
  const nutRows = document.querySelectorAll(".nut-row");
  // console.log("nutRows:", nutRows.length);

  nutRows.forEach((row) => {
    const key = row.dataset.nutrient;
    const data = nutritionData[key];

    // 방어코드: key가 틀리면 여기서 종료 (전체 중단 방지)
    if (!data) return;

    const textEl = row.querySelector(".nut-text");
    const barEl = row.querySelector(".nut-bar span");

    if (!textEl || !barEl) return;

    const percent = (data.intake / data.recommended) * 100;
    const width = Math.min(percent, 100);

    const color = data.intake >= data.recommended ? COLOR_FULL : COLOR_LOW;

    // 텍스트
    textEl.textContent = `${data.intake} / ${data.recommended} ${data.unit}`;

    // 막대
    barEl.style.width = `${width}%`;
    barEl.style.backgroundColor = color;
  });

  /* 요약/자세히 토글 */
  const toggleButtons = document.querySelectorAll(".nutrition-toggle .toggle-btn");
  const summaryContent = document.querySelector(".summary-content");
  const detailContent = document.querySelector(".detail-content");

  if (toggleButtons.length && summaryContent && detailContent) {
    toggleButtons.forEach((button) => {
      button.addEventListener("click", () => {
        toggleButtons.forEach((btn) => btn.classList.remove("active"));
        button.classList.add("active");

        const target = button.dataset.target;

        summaryContent.style.display = target === "summary" ? "block" : "none";
        detailContent.style.display = target === "detail" ? "block" : "none";

        // detail 탭으로 넘어갈 때 차트가 안 보이면, 여기서 한 번 더 렌더(안전)
        if (target === "detail") {
          // detail이 display:none -> block으로 바뀐 직후라 size 계산이 안정적
          renderMacroChart(getMealLabel("morning"), mealMacroData.morning);
        }
      });
    });
  }

  /* 끼니별 탄단지 더미 데이터 */
  const mealMacroData = {
    morning: { carb: 260, protein: 120, fat: 140, kcal: 1020 },
    lunch:   { carb: 300, protein: 180, fat: 160, kcal: 640 },
    dinner:  { carb: 200, protein: 220, fat: 180, kcal: 600 },
  };

  /* 끼니 버튼 DOM */
  const mealButtons = document.querySelectorAll(".meal-btn");

  /* 영양 도넛 차트 */
  let macroDonutChart = null;

  const centerTextPlugin = {
      id: "centerText",
      beforeDraw(chart) {
        const { width, height, ctx } = chart;
        const text = chart.config.options.plugins.centerText?.text;

        if (!text) return;

        ctx.save();
        ctx.font = "700 18px Inter, sans-serif";
        ctx.fillStyle = "#3C3C43";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";

        ctx.fillText(text, width / 2, height / 2);
        ctx.restore();
      }
    };

  function renderMacroDonut(data) {
      const canvas = document.getElementById("macroDonutChart");
      if (!canvas || !window.Chart) return;

      const ctx = canvas.getContext("2d");

      if (macroDonutChart) macroDonutChart.destroy();

      macroDonutChart = new Chart(ctx, {
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
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: ctx => `${ctx.label}: ${ctx.raw} g`
              }
            },
            centerText: {
              text: `${data.kcal} kcal`
            }
          }
        },
        plugins: [centerTextPlugin]
      });
    }

  /*끼니 버튼 클릭 이벤트 */
  mealButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      mealButtons.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");

      const meal = btn.dataset.meal;
      if (mealMacroData[meal]) {
        renderMacroDonut(mealMacroData[meal]);
      }
    });
  });

  /* 초기 상태 (detail 탭 열렸을 때) */
  const morningBtn = document.querySelector('.meal-btn[data-meal="morning"]');
  if (morningBtn) morningBtn.classList.add("active");

  // detail-content가 보인 이후에 호출하는 게 가장 안전
  renderMacroDonut(mealMacroData.morning);

  /* 하루 감정 더미 데이터 */
  const moodRatioData = {
      positive: 0.5,
      neutral: 0.3,
      negative: 0.2
    };

  /* 하루 감정에 따른 캐릭터(이미지) 설정 */
  function getDominantMood(moodData) {
      return Object.entries(moodData)
        .sort((a, b) => b[1] - a[1])[0][0];
    }

  const moodCharacterMap = {
      positive: "/static/icons_img/긍정.png",
      neutral:  "/static/icons_img/중립.png",
      negative: "/static/icons_img/부정.png"
    };

  const moodTextMap = {
      positive: "오늘은 긍정 감정을 많이 느꼈어요!",
      neutral:  "오늘의 감정은 무난했어요!",
      negative: "오늘은 부정 감정을 많이 느꼈어요!"
    };

  /* 기분 도넛 차트 render */
  function renderMoodCharacterText(moodData) {
      const dominantMood = getDominantMood(moodData);
      const imgSrc = moodCharacterMap[dominantMood];
      const text = moodTextMap[dominantMood];

      const imgContainer = document.querySelector(".mood_img");
      const textContainer = document.querySelector(".mood_text");

      if (!imgContainer || !textContainer || !imgSrc || !text) return;

      imgContainer.innerHTML = `
        <img src="${imgSrc}" alt="${dominantMood} mood character">
      `;

      textContainer.textContent = text;
  }

  let moodDonutChart = null;

  function renderMoodDonut(moodData) {
      const canvas = document.getElementById("moodDonutChart");
      if (!canvas || !window.Chart) return;

      const ctx = canvas.getContext("2d");

      if (moodDonutChart) moodDonutChart.destroy();

      moodDonutChart = new Chart(ctx, {
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
              "#FFD07C",  // 긍정
              "#FFE2B6",  // 중립
              "#FFB845"   // 부정
            ],
            borderWidth: 0
          }]
        },
        options: {
          cutout: "65%",
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: ctx =>
                  `${ctx.label}: ${(ctx.raw * 100).toFixed(1)}%`
              }
            },
            centerText: {
              text: `긍정 ${Math.round(moodRatioData.positive * 100)} %`
            }
          }
        },
        plugins: [centerTextPlugin]
      });
  }
  /* 실행은 항상 맨 마지막 */
  renderMoodCharacterText(moodRatioData);
  renderMoodDonut(moodRatioData);
});

