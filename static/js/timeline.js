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
   *    - x축 tick은 숨김 (DOM 날짜 7개가 담당)
   *    - labels가 비어도 week-picker-label로 생성
   * ====================================================== */
  const canvas = document.getElementById("weeklyEmotionChart");
  const dataTag = document.getElementById("weeklyEmotionData");
  let chartInstance = null;

  function renderWeeklyChart(payload) {
    if (!canvas) return;
    if (!window.Chart) {
      console.error("[timeline] Chart.js is not loaded (Chart is undefined).");
      return;
    }

    const range = getWeekRangeFromLabel();
    const fallbackLabels = buildWeekLabelsFromRange(range.start, range.end);

    // ✅ labels 우선순위: payload.labels > fallback(week range)
    const labels =
      (Array.isArray(payload?.labels) && payload.labels.length > 0)
        ? payload.labels
        : fallbackLabels;

    // ✅ 날짜 7개는 무조건 렌더(데이터 없어도)
    renderWeekDateLabels(labels);

    const N = labels.length || 7;

    // ✅ 데이터가 비어도 0으로 채워서 차트가 “그려지게” 함
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
                data: pos,                 // 강도 score (0~9)
                stack: "feeling",
                backgroundColor: "rgba(245, 148, 30, 0.70)", // 긍정: 메인 오렌지
                borderRadius: 10,
                borderSkipped: false,
            },
            {
                label: "Neutral (중립)",
                data: neu,                 // 강도 score
                stack: "feeling",
                backgroundColor: "rgba(245, 148, 30, 0.35)", // 중립: 연한 톤
                borderRadius: 10,
                borderSkipped: false,
            },
            {
                label: "Negative (부정)",
                data: neg,                 // 강도 score
                stack: "feeling",
                backgroundColor: "rgba(180, 120, 60, 0.55)", // 부정: 더 무거운 색
                borderRadius: 10,
                borderSkipped: false,
            },
        ]

      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { top: 8, left: 10, right: 10, bottom: 0 } },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (c) => `${c.dataset.label}: ${c.parsed.y}%`,
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
            max: payload.y_max || 9,
            grid: { display: false, drawBorder: false },
            ticks: { display: false, stepSize: 1    },
          },
        },
      },
    });
  }

  if (canvas && dataTag) {
    let payload = {};
    try {
      payload = JSON.parse(dataTag.textContent || "{}");
    } catch (e) {
      console.error("[timeline] JSON parse failed:", e);
      // JSON이 깨져도 날짜는 range로라도 보이게
      payload = {};
    }
    renderWeeklyChart(payload);
  } else {
    // 데이터 태그가 없어도 날짜는 보여주기
    const range = getWeekRangeFromLabel();
    renderWeekDateLabels(buildWeekLabelsFromRange(range.start, range.end));
  }

  /* ======================================================
   * 2) Week Datepicker + Caret 아래 Arrow 정렬
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

    // ✅ (즉시 UI 반영) 페이지 이동 전에도 날짜 7개는 range로 갱신
    renderWeekDateLabels(buildWeekLabelsFromRange(fmtLabel(startDate), fmtLabel(endDate)));

    window.location.search = `?start=${fmtParam(startDate)}&end=${fmtParam(endDate)}`;
  });

  function alignDatepickerArrow() {
    const dp = $weekPicker.data("datepicker");
    if (!dp || !dp.picker) return;

    const pickerEl = dp.picker.get(0);
    const caretEl = document.querySelector(".timeline-datebar-caret");
    if (!pickerEl || !caretEl) return;

    const pickerRect = pickerEl.getBoundingClientRect();
    const caretRect = caretEl.getBoundingClientRect();
    const arrowLeft = (caretRect.left + caretRect.width / 2) - pickerRect.left;

    pickerEl.style.setProperty("--dp-arrow-left", `${arrowLeft}px`);
  }

  $trigger.on("click", function () {
    $weekPicker.datepicker("show");
    setTimeout(alignDatepickerArrow, 0);
    setTimeout(alignDatepickerArrow, 30);
  });
});
