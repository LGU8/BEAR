document.addEventListener("DOMContentLoaded", () => {
  /* 안전 체크 (디버깅용) */
  //console.log("[report_daily] DOMContentLoaded ✅");

  /* 하루 요약 영양소 더미 데이터 (DB에서 온다고 가정) */
  const nutEl = document.getElementById("report-nut-data");
//  if (!nutEl) {
//    console.error("report-nut-data element not found");
//    return;
//  }

  const nutritionData = JSON.parse(nutEl.dataset.nutDay);

  const total = {kcal: 0, carb: 0, protein: 0, fat: 0};

  ["M", "L", "D"].forEach(slot => {
    if (!nutritionData[slot]) return;
    total.kcal += nutritionData[slot].kcal || 0;
    total.carb += nutritionData[slot].carb || 0;
    total.protein += nutritionData[slot].protein || 0;
    total.fat += nutritionData[slot].fat || 0;
  });

  const COLOR_FULL = "#F47900"; // 권장량 충족/초과
  const COLOR_LOW = "#FFA636"; // 부족

  /* 하루 요약 막대(그래프처럼 보이는 progress) 렌더링 */
  document.querySelectorAll(".nut-row").forEach(row => {
    const key = row.dataset.nutrient; // calorie, carb, protein, fat
    const textEl = row.querySelector(".nut-text");
    const barEl = row.querySelector(".nut-bar span");

    if (!textEl || !barEl) return;

    // calorie는 kcal로 매핑
    const dataKey = key === "calorie" ? "kcal" : key;

    const intake = total[dataKey];
    const recommended = nutritionData.recom[dataKey];

    // 방어: 기준값 없으면 표시 안 함
    if (recommended == null || recommended === 0) return;

    const percent = (intake / recommended) * 100;
    const width = Math.min(percent, 100);
    const color = intake >= recommended ? COLOR_FULL : COLOR_LOW;

    // 텍스트 출력
    if (dataKey === "kcal") {
    textEl.textContent = `${intake} / ${recommended} kcal`;
    } else {
    textEl.textContent = `${intake} / ${recommended} g`;
    }

    // 막대 스타일
    barEl.style.width = `${width}%`;
    barEl.style.backgroundColor = color;
  });

  /* 요약/자세히 토글 */
  const toggleButtons = document.querySelectorAll(".nut-sum-type-toggle .toggle-btn");
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
      });
    });
  }

  /* 끼니별 버튼 매핑 */
  const MEAL_KEY_MAP = {
    morning: "M",
    lunch: "L",
    dinner: "D"
  };

  /* 끼니 버튼 DOM */
  const mealButtons = document.querySelectorAll(".meal-btn");
  const menuTextEl = document.querySelector(".meal-menu-text");

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

  function renderMacroDonut(mealKey) {
    const data = nutritionData[mealKey];
    if (!data) return;

    /* ---- 메뉴명 렌더 ---- */
    if (menuTextEl) {
    if (data.f_name && data.f_name.length > 0) {
      menuTextEl.textContent = data.f_name.join(", ");
    } else {
      menuTextEl.textContent = "기록된 메뉴가 없어요";
    }
    }

    /* ---- 도넛 차트 렌더 ---- */
    const canvas = document.getElementById("macroDonutChart");
    if (!canvas || !window.Chart) return;

    const ctx = canvas.getContext("2d");

    if (macroDonutChart) {
    macroDonutChart.destroy();
    }

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
      animation: false,
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

      const meal = btn.dataset.meal;          // morning / lunch / dinner
      const mealKey = MEAL_KEY_MAP[meal];     // M / L / D
      if (mealKey) {
        renderMacroDonut(mealKey);
      }
    });
  });

  /* 초기 상태-아침 (detail 탭 열렸을 때) */
  const morningBtn = document.querySelector('.meal-btn[data-meal="morning"]');
    if (morningBtn) {
      morningBtn.classList.add("active");
      renderMacroDonut("M");
  }

/* ─────────────────────────────
   감정 도넛 차트
   ───────────────────────────── */

  /* 하루 감정 더미 데이터 */
  const moodEl = document.getElementById("report-mood-data");

  if (!nutEl) {
    console.error("report-mood-data element not found");
    return;
  }
  const moodRatio = JSON.parse(moodEl.dataset.moodRatio);

  const moodRatioData = {
    positive: moodRatio.pos,
    neutral: moodRatio.neu,
    negative: moodRatio.neg
  };

  /* 하루 감정에 따른 캐릭터(이미지) 설정 */
  function getDominantMood(moodData) {
    const values = Object.values(moodData);

    // 1) 모든 값이 같은지 확인
    const allEqual = values.every(v => v === values[0]);

    if (allEqual) {
    return "neutral";
    }

    // 2) 모두 같지 않으면, 가장 큰 값의 감정 반환
    return Object.entries(moodData)
    .sort((a, b) => b[1] - a[1])[0][0];
  }

  const moodCharacterMap = {
      positive: "/static/icons_img/긍정.png",
      neutral:  "/static/icons_img/중립.png",
      negative: "/static/icons_img/부정.png"
    };

  const moodTextMap = {
      positive: "오늘은 긍정 감정을 많이 느꼈어요 😊",
      neutral:  "오늘의 감정은 무난했어요 🙂",
      negative: "오늘은 부정 감정을 많이 느꼈어요 🥺"
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
          animation: false,
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

