document.addEventListener("DOMContentLoaded", () => {
  /* ======================================================
   * 0) 날짜 7개(DOM) 렌더 유틸
   * ====================================================== */
  function ensureDateLabelContainer() {
    let wrap = document.getElementById("weeklyDateLabels");
    if (wrap) return wrap;

    const canvas = document.getElementById("weeklyEmotionChart");
    if (!canvas) return null;

    const panel = canvas.closest(".timeline-chart-panel");
    if (!panel) return null;

    wrap = document.createElement("div");
    wrap.id = "weeklyDateLabels";
    wrap.className = "timeline-xlabels";
    wrap.setAttribute("aria-hidden", "true");
    panel.appendChild(wrap);
    return wrap;
  }

  function renderWeekDateLabels(labels) {
    const wrap = ensureDateLabelContainer();
    if (!wrap) return;

    const normalized = (labels || []).slice(0, 7);
    while (normalized.length < 7) normalized.push("");

    wrap.innerHTML = normalized
      .map((t) => `<span class="timeline-xlabel">${t || ""}</span>`)
      .join("");
  }

  function getWeekRangeFromLabel() {
    const el = document.getElementById("week-picker-label");
    if (!el) return { start: "", end: "" };

    const txt = (el.textContent || "").trim(); // "2025.12.11 ~ 2025.12.17"
    const parts = txt.split("~").map((s) => s.trim());
    return { start: parts[0] || "", end: parts[1] || "" };
  }

  function buildWeekLabelsFromRange(weekStartStr, weekEndStr) {
    const norm = (s) => (s || "").replace(/\./g, "-").trim(); // 2025.12.11 -> 2025-12-11
    const start = new Date(norm(weekStartStr));
    const end = new Date(norm(weekEndStr));

    if (isNaN(start.getTime()) || isNaN(end.getTime())) return [];

    const out = [];
    const cur = new Date(start);
    while (cur <= end) {
      const m = cur.getMonth() + 1;
      const d = cur.getDate();
      out.push(`${m}/${d}`);
      cur.setDate(cur.getDate() + 1);
    }
    return out;
  }

  function normalizeToLength(arr, n, fill = 0) {
    const out = Array.isArray(arr) ? arr.slice(0, n) : [];
    while (out.length < n) out.push(fill);
    return out;
  }

  /* ======================================================
   * 1) Chart.js (주간 감정 누적 막대)
   *    - 막대 높이: score 합 (0~9)
   *    - 누적 구성: pos/neu/neg score
   *    - x축 tick 숨김 (DOM 날짜 7개가 담당)
   * ====================================================== */
  const canvas = document.getElementById("weeklyEmotionChart");
  const dataTag = document.getElementById("weeklyEmotionData");
  let chartInstance = null;

  // ✅ 라운드 규칙:
  // - 그 날짜 막대가 단일 조각이면 전체 radius 10
  // - 여러 조각이면 최상단 조각만 topLeft/topRight radius 10
  function getTopRadius(ctx, r) {
    const chart = ctx.chart;
    const dataIndex = ctx.dataIndex;
    const stackKey = ctx.dataset.stack;

    const stackDatasets = chart.data.datasets.filter((ds) => ds.stack === stackKey);
    const nonZero = stackDatasets.filter((ds) => Number(ds.data?.[dataIndex] ?? 0) > 0);

    if (nonZero.length === 0) return 0;

    const isTop = nonZero[nonZero.length - 1] === ctx.dataset;

    // 단일 조각이면 전체 둥글게
    if (nonZero.length === 1 && isTop) return r;

    // 여러 조각이면 최상단만 윗모서리 둥글게
    if (isTop) {
      return { topLeft: r, topRight: r, bottomLeft: 0, bottomRight: 0 };
    }

    return 0;
  }
  function syncXLabelsToChartArea(chartInstance) {
    const wrap = document.getElementById("weeklyDateLabels");
    if (!wrap || !chartInstance) return;

    const ca = chartInstance.chartArea;
    if (!ca) return;

    const canvas = chartInstance.canvas;

    // canvas의 내부 pixel 기준으로 padding 계산
    const leftPad = ca.left;
    const rightPad = canvas.width - ca.right;

    // 날짜 그리드가 chartArea 폭과 동일해지도록 좌/우 padding을 맞춤
    wrap.style.paddingLeft = `${leftPad}px`;
    wrap.style.paddingRight = `${rightPad}px`;

    // 혹시 이전 CSS에서 margin/transform이 있으면 영향 줄이기
    wrap.style.boxSizing = "border-box";
  }

  function renderWeeklyChart(payload) {
    if (!canvas) return;
    if (!window.Chart) {
      console.error("[timeline] Chart.js is not loaded (Chart is undefined).");
      return;
    }

    const range = getWeekRangeFromLabel();
    const fallbackLabels = buildWeekLabelsFromRange(range.start, range.end);

    const labels =
      (Array.isArray(payload?.labels) && payload.labels.length > 0)
        ? payload.labels
        : fallbackLabels;

    // ✅ 날짜 7개는 무조건 렌더
    renderWeekDateLabels(labels);

    const N = labels.length || 7;

    // ✅ score 데이터(0~9), 비어도 0으로 채움
    const pos = normalizeToLength(payload?.pos, N, 0);
    const neu = normalizeToLength(payload?.neu, N, 0);
    const neg = normalizeToLength(payload?.neg, N, 0);

    const ctx = canvas.getContext("2d");

    if (chartInstance) {
      chartInstance.destroy();
      chartInstance = null;
    }

    chartInstance = new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Positive (긍정)",
            data: pos,
            stack: "feeling",
            backgroundColor: "#FFD07C",
            borderSkipped: false,
            borderRadius: (c) => getTopRadius(c, 10),
          },
          {
            label: "Neutral (중립)",
            data: neu,
            stack: "feeling",
            backgroundColor: "#FFE2B6",
            borderSkipped: false,
            borderRadius: (c) => getTopRadius(c, 10),
          },
          {
            label: "Negative (부정)",
            data: neg,
            stack: "feeling",
            backgroundColor: "#FFB845",
            borderSkipped: false,
            borderRadius: (c) => getTopRadius(c, 10),
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { top: 8, left: 10, right: 10, bottom: 0 } },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              // ✅ 점수 기반이므로 % 제거
              label: (c) => `${c.dataset.label}: ${c.parsed.y}점`,
            },
          },
        },
        scales: {
          x: {
            stacked: true,
            grid: { display: false, drawBorder: false },
            ticks: { display: false }, // ✅ DOM 날짜 사용
          },
          y: {
            stacked: true,
            beginAtZero: true,
            max: payload?.y_max ?? 9, // ✅ 고정 스케일 (기본 9)
            grid: { display: false, drawBorder: false },
            ticks: { display: false, stepSize: 1 },
          },
        },
      },
    });
    // ✅ 차트가 그려진 후 chartArea가 생기므로, 다음 프레임에 동기화
    requestAnimationFrame(() => syncXLabelsToChartArea(chartInstance));

    // ✅ 리사이즈 시에도 계속 맞추기
    window.addEventListener("resize", () => {
        if (chartInstance) syncXLabelsToChartArea(chartInstance);
    });


  }

  if (canvas && dataTag) {
    let payload = {};
    try {
      payload = JSON.parse(dataTag.textContent || "{}");
    } catch (e) {
      console.error("[timeline] JSON parse failed:", e);
      payload = {};
    }
    renderWeeklyChart(payload);
  } else {
    // 데이터 태그가 없어도 날짜는 보여주기
    const range = getWeekRangeFromLabel();
    renderWeekDateLabels(buildWeekLabelsFromRange(range.start, range.end));
  }

  /* ======================================================
   * 2) Week Datepicker
   * ====================================================== */
  if (!window.jQuery) return;
  const $ = window.jQuery;

  const $weekPicker = $("#week-picker");
  const $trigger = $("#week-picker-trigger");
  const $label = $("#week-picker-label");

  if ($weekPicker.length === 0) return;

  const today = new Date();
  const maxStart = new Date();
  maxStart.setDate(today.getDate() - 6);

  $weekPicker.datepicker({
    format: "yyyy-mm-dd",
    language: "ko",
    autoclose: true,
    endDate: maxStart,
    todayHighlight: false,
    container: "body",
  }).on("changeDate", function (e) {
    const startDate = e.date;
    const endDate = new Date(startDate);
    endDate.setDate(startDate.getDate() + 6);

    const fmtParam = (d) => {
      const y = d.getFullYear();
      const m = String(d.getMonth() + 1).padStart(2, "0");
      const day = String(d.getDate()).padStart(2, "0");
      return `${y}${m}${day}`;
    };

    const fmtLabel = (d) => {
      const y = d.getFullYear();
      const m = String(d.getMonth() + 1).padStart(2, "0");
      const day = String(d.getDate()).padStart(2, "0");
      return `${y}.${m}.${day}`;
    };

    $label.text(`${fmtLabel(startDate)} ~ ${fmtLabel(endDate)}`);

    // ✅ 페이지 이동 전에도 날짜 7개만 즉시 갱신
    renderWeekDateLabels(buildWeekLabelsFromRange(fmtLabel(startDate), fmtLabel(endDate)));

    window.location.search = `?start=${fmtParam(startDate)}&end=${fmtParam(endDate)}`;
  });

  $trigger.on("click", function () {
    $weekPicker.datepicker("show");
  });
});
