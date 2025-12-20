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
      cutout: "65%",
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


/* ==============================
   Home - Daily Report Section
   ============================== */

(function () {
  const section = document.getElementById("section-daily-report");
  if (!section) return;

  const todayYmd = section.dataset.todayYmd || ""; // "YYYYMMDD"
  const hasReport = section.dataset.hasReport === "1";

  const elDateTop = document.getElementById("dailyReportDateTop");
  const elContent = document.getElementById("dailyReportContent");

  // 안전장치
  if (!elDateTop || !elContent) return;

  // 1) 오늘 날짜를 "April, 08" 형태로 표시 (월은 무조건 영어)
  // todayYmd가 비어 있으면 브라우저 Date로 fallback
  const monthNames = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December"
  ];

  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  function ymdToMonthDayEnglish(ymd) {
    // ymd: "YYYYMMDD"
    if (!ymd || ymd.length !== 8) {
      const d = new Date();
      return `${monthNames[d.getMonth()]}, ${pad2(d.getDate())}`;
    }
    const y = Number(ymd.slice(0, 4));
    const m = Number(ymd.slice(4, 6));
    const d = Number(ymd.slice(6, 8));
    // month index: m-1
    const month = monthNames[Math.max(0, Math.min(11, m - 1))];
    return `${month}, ${pad2(d)}`;
  }

  elDateTop.textContent = ymdToMonthDayEnglish(todayYmd);

  // 2) 리포트가 없거나 content가 비어있으면 시간 분기 후 문구 주입
  // 서버가 content를 넣어줬더라도, 공백만 있는 경우는 "없음"으로 처리
  const serverContent = (elContent.textContent || "").trim();

  function isAfterOrAt20() {
    const now = new Date(); // ✅ 클라이언트 시간
    const hh = now.getHours();
    const mm = now.getMinutes();
    // >= 20:00
    return hh > 20 || (hh === 20 && mm >= 0);
  }

  function setStatusMessageBefore20() {
    // ✅ 두 줄로
    elContent.classList.add("is-empty");
    elContent.textContent = "리포트가 생성중입니다.\n저녁 8시 이후 확인해 주세요.";
  }

  function setStatusMessageAfter20() {
    elContent.classList.add("is-empty");
    elContent.textContent = "오늘 기록을 하지 않았어요. 기록을 남기면 리포트가 생성돼요.";
  }

  // “hasReport”는 서버가 내려준 값이지만, 혹시 서버/템플릿 실수로 깨질 수 있으니
  // serverContent 기준으로 최종 판단을 한번 더 해줌.
  const finalHasContent = hasReport && serverContent.length > 0;

  if (!finalHasContent) {
    if (isAfterOrAt20()) setStatusMessageAfter20();
    else setStatusMessageBefore20();
  } else {
    // content가 있으면 empty 스타일 제거
    elContent.classList.remove("is-empty");
  }
})();
