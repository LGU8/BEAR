document.addEventListener("DOMContentLoaded", () => {
  const canvas = document.getElementById("weeklyEmotionChart");
  if (!canvas) return;

  const dataTag = document.getElementById("weeklyEmotionData");
  if (!dataTag) return;

  let payload;
  try {
    payload = JSON.parse(dataTag.textContent);
  } catch (e) {
    console.error("[timeline] weeklyEmotionData JSON parse failed:", e);
    console.error("[timeline] raw payload:", dataTag.textContent);
    return;
  }

  const labels = payload.labels || [];
  const pos = payload.pos || [];
  const neu = payload.neu || [];
  const neg = payload.neg || [];

  // 데이터 길이 불일치 방어(디버깅 도움)
  if (!(labels.length === pos.length && labels.length === neu.length && labels.length === neg.length)) {
    console.error("[timeline] data length mismatch", {
      labels: labels.length,
      pos: pos.length,
      neu: neu.length,
      neg: neg.length
    });
    return;
  }

  const ctx = canvas.getContext("2d");

  new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Positive(pos) %", data: pos, stack: "emotion" },
        { label: "Neutral(neu) %", data: neu, stack: "emotion" },
        { label: "Negative(neg) %", data: neg, stack: "emotion" },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom" },
        tooltip: {
          callbacks: {
            label: (c) => `${c.dataset.label}: ${c.parsed.y}%`,
          },
        },
      },
      scales: {
        x: {
          stacked: true,
          grid: { display: false },
        },
        y: {
          stacked: true,
          beginAtZero: true,
          max: 100,
          ticks: {
            callback: (v) => `${v}%`,
          },
        },
      },
    },
  });
});
