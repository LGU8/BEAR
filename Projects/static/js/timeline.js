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
    if (!isTop) return 0;

    // ✅ 픽셀 기반 radius 제한 + 정수화(미세 seam 완화)
    const h = Math.abs(ctx.element?.height ?? 0);
    const rEff = h > 0 ? Math.min(r, Math.max(0, Math.floor(h / 2) - 1)) : r;
    const rr = Math.max(0, Math.floor(rEff)); // 정수로

    // ✅ 단일이든 다중이든 무조건 '상단만' 라운드
    return {
      topLeft: rr,
      topRight: rr,
      bottomLeft: 0,
      bottomRight: 0,
    };
  }

  // ✅ seam(가로줄) 마스킹 플러그인 (정확한 y 위치 = yScale.getPixelForValue(total))
// - 각 x index에서 (pos+neu+neg) 총합의 픽셀 위치를 계산해 top을 정확히 덮음
const maskTopSeamPlugin = {
  id: "maskTopSeam",
  afterDatasetsDraw(chart, args, pluginOptions) {
    const thickness = pluginOptions?.thickness ?? 2;

    const { ctx, data, scales } = chart;
    const yScale = scales?.y;
    if (!yScale) return;

    // pos/neu/neg 데이터셋(순서 고정 가정: 0,1,2)
    // 혹시 순서가 바뀔 수 있으면 label로 찾아도 됨
    const dsPos = data.datasets?.[0];
    const dsNeu = data.datasets?.[1];
    const dsNeg = data.datasets?.[2];
    if (!dsPos || !dsNeu || !dsNeg) return;

    const N = data.labels?.length ?? 0;

    for (let i = 0; i < N; i++) {
      const p = Number(dsPos.data?.[i] ?? 0);
      const n = Number(dsNeu.data?.[i] ?? 0);
      const g = Number(dsNeg.data?.[i] ?? 0);

      const total = p + n + g;
      if (total <= 0) continue;

      // ✅ 해당 날짜의 "최상단 조각" dataset 찾기 (값이 있는 마지막 dataset)
      let topDs = null;
      if (g > 0) topDs = dsNeg;
      else if (n > 0) topDs = dsNeu;
      else if (p > 0) topDs = dsPos;
      else continue;

      // ✅ top bar element의 x/width는 meta에서 가져오고,
      // ✅ y(top)는 total로부터 정확히 계산
      const topIndex =
        topDs === dsPos ? 0 : topDs === dsNeu ? 1 : 2;

      const meta = chart.getDatasetMeta(topIndex);
      const el = meta?.data?.[i];
      if (!el) continue;

      const x = el.x;
      const w = el.width;

      // ✅ 총합 기준으로 계산한 막대 top pixel
      const yTop = yScale.getPixelForValue(total);

      // backgroundColor 안전 처리
      let fill = topDs.backgroundColor;
      if (typeof fill === "function") fill = fill({ chart, dataset: topDs, dataIndex: i });
      if (Array.isArray(fill)) fill = fill[i] ?? fill[0];
      if (!fill) continue;

      ctx.save();
      ctx.fillStyle = fill;

      // ✅ seam은 보통 "막대 바로 위/경계"에 생기므로 살짝 위로 올려 덮기
      // -1을 주는 게 포인트 (너 케이스에서 두꺼워졌던 이유가 위치 오차였음)
      ctx.fillRect(x - w / 2, yTop - 1, w, thickness);

      ctx.restore();
    }
  },
};

  
  function syncXLabelsToChartArea(chartInstance) {
    const wrap = document.getElementById("weeklyDateLabels");
    if (!wrap || !chartInstance) return;

    const ca = chartInstance.chartArea;
    if (!ca) return;

    // ✅ chartArea 폭/시작점 그대로 사용
    const areaWidth = ca.right - ca.left;

    wrap.style.boxSizing = "border-box";
    wrap.style.width = `${areaWidth}px`;
    wrap.style.marginLeft = `${ca.left}px`;
    wrap.style.marginRight = `0px`;

    // 혹시 기존에 padding으로 남아있던 값 제거
    wrap.style.paddingLeft = "0px";
    wrap.style.paddingRight = "0px";
  }
  function clamp(n, min, max) {
  return Math.max(min, Math.min(max, n));
}

/**
 * chartAreaWidth: chartInstance.chartArea.right - chartInstance.chartArea.left
 * N: 막대 개수(보통 7)
 */
function calcBarThickness(chartAreaWidth, N) {
  // 카테고리 1칸의 대략적인 폭
  const slot = chartAreaWidth / Math.max(1, N);

  // ✅ “겹침 방지” 핵심:
  // - 막대는 slot보다 충분히 작아야 함
  // - stacked bar라서 너비만 안정적이면 겹침 거의 해결됨
  // - 모바일에서도 너무 얇아지지 않게 최소값 보장
  const thickness = Math.floor(slot * 0.55);      // 55% 정도
  const maxThickness = Math.floor(slot * 0.70);   // 70% 정도

  return {
    barThickness: clamp(thickness, 6, 26),        // 모바일 최소 6px, PC 최대 26px 정도
    maxBarThickness: clamp(maxThickness, 8, 32),
  };
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

    const isMobile = window.matchMedia("(max-width: 480px)").matches;

    const initialThickness = {
      barThickness: isMobile ? 10 : 44,
      maxBarThickness: isMobile ? 12 : 56,
    };


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

            barThickness: initialThickness.barThickness,
            maxBarThickness: initialThickness.maxBarThickness,
            categoryPercentage: 0.8,
            barPercentage: 0.9,


            borderWidth: 0,
          },
          {
            label: "Neutral (중립)",
            data: neu,
            stack: "feeling",
            backgroundColor: "#FFE2B6",
            borderSkipped: false,

            barThickness: initialThickness.barThickness,
            maxBarThickness: initialThickness.maxBarThickness,
            categoryPercentage: 0.8,
            barPercentage: 0.9,


            borderWidth: 0,
          },
          {
            label: "Negative (부정)",
            data: neg,
            stack: "feeling",
            backgroundColor: "#FFB845",
            borderSkipped: false,

            barThickness: initialThickness.barThickness,
            maxBarThickness: initialThickness.maxBarThickness,
            categoryPercentage: 0.8,
            barPercentage: 0.9,



            borderWidth: 0,
          }
        ],

      },
      plugins: [maskTopSeamPlugin],
      options: {
        responsive: true,
        maintainAspectRatio: false,
        onResize: (chart) => syncXLabelsToChartArea(chart),
        elements: {
          bar: {
            borderWidth: 0,
            borderColor: "transparent",
          },
        },
        layout: { padding: { top: 8, left: 10, right: 10, bottom: 0 } },
        plugins: {
          maskTopSeam: { thickness: 0}, // ✅ 1~3 추천

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
            offset: true,
            grid: { display: false, drawBorder: false },
            border: { display: false }, // ✅ 추가
            ticks: { display: false },
          },
          y: {
            stacked: true,
            beginAtZero: true,
            max: payload?.y_max ?? 10,
            grid: { display: false, drawBorder: false },
            border: { display: false }, // ✅ 추가
            ticks: { display: false, stepSize: 1 },
          },
        },
      },
    });
    // ✅ 차트가 그려진 후 chartArea가 생기므로, 다음 프레임에 동기화
    requestAnimationFrame(() => {
      // 1) x라벨 위치 맞추기
      syncXLabelsToChartArea(chartInstance);

      // 2) chartArea 기준으로 막대 두께 정확히 계산
      const ca = chartInstance?.chartArea;
      if (!ca) return;

      const isMobileNow = window.matchMedia("(max-width: 480px)").matches;

      if (isMobileNow) {
        const areaWidth = ca.right - ca.left;
        const t = calcBarThickness(areaWidth, N);

        chartInstance.data.datasets.forEach((ds) => {
          ds.barThickness = t.barThickness;
          ds.maxBarThickness = t.maxBarThickness;
        });

        chartInstance.update("none");
      }

    });


    // ✅ 리사이즈 시에도 계속 맞추기
    if (!window.__weeklyEmotionResizeBound) {
      window.__weeklyEmotionResizeBound = true;

      window.addEventListener("resize", () => {
        if (!chartInstance) return;

        syncXLabelsToChartArea(chartInstance);

        const ca = chartInstance.chartArea;
        if (!ca) return;

        const isMobileNow = window.matchMedia("(max-width: 480px)").matches;

        // ✅ PC면 원래 두께로 되돌리고 종료
        if (!isMobileNow) {
          chartInstance.data.datasets.forEach((ds) => {
            ds.barThickness = 44;
            ds.maxBarThickness = 56;
          });
          chartInstance.update("none");
          return;
        }

        const areaWidth = ca.right - ca.left;
        const t = calcBarThickness(areaWidth, chartInstance.data.labels?.length ?? 7);

        chartInstance.data.datasets.forEach((ds) => {
          ds.barThickness = t.barThickness;
          ds.maxBarThickness = t.maxBarThickness;
        });

        chartInstance.update("none");
      });
    }




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
