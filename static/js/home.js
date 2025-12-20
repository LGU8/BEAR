// static/js/home.js
document.addEventListener("DOMContentLoaded", () => {
  // Chart.js 로딩 확인
  if (typeof Chart === "undefined") {
    console.warn("[home.js] Chart.js가 로딩되지 않았습니다.");
    return;
  }

  // json_script로 주입된 donut-data 가져오기
  const el = document.getElementById("donut-data");
  if (!el) {
    console.warn("[home.js] donut-data script 태그를 찾지 못했습니다.");
    return;
  }

  let donut = null;
  try {
    donut = JSON.parse(el.textContent);
  } catch (e) {
    console.warn("[home.js] donut-data JSON 파싱 실패:", e);
    return;
  }

  // donut이 None이면 기록 없음 상태 → 템플릿에서 empty-state가 이미 처리
  if (!donut) return;

  const pos_count = Number(donut.pos_count ?? 0);
  const rest_count = Number(donut.rest_count ?? 0);
  const total = Number(donut.total ?? 0);

  if (!total || total <= 0) return;

  const canvas = document.getElementById("positiveDonutChart");
  if (!canvas) return;

  const ctx = canvas.getContext("2d");

  // 중복 생성 방지
  if (canvas._chartInstance) {
    canvas._chartInstance.destroy();
  }

  const chart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["긍정", "긍정 외"],
      datasets: [
        {
          data: [pos_count, rest_count],
          backgroundColor: ["#FFB845", "#FFD07C"],
          borderWidth: 0,
          hoverOffset: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "55%",
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (context) => {
              const label = context.label || "";
              const value = context.raw ?? 0;
              return `${label}: ${value}`;
            },
          },
        },
      },
      animation: {
        animateRotate: true,
        duration: 700,
        easing: "easeOutQuart",
      },
    },
  });

  canvas._chartInstance = chart;
});
