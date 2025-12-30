// static/js/home.js
document.addEventListener("DOMContentLoaded", () => {
  /* =========================================================
     1) 긍정 도넛 차트 (Chart.js)
     ========================================================= */

  if (typeof Chart === "undefined") {
    console.warn("[home.js] Chart.js가 로딩되지 않았습니다.");
  } else {
    const el = document.getElementById("donut-data");
    if (!el) {
      console.warn("[home.js] donut-data script 태그를 찾지 못했습니다.");
    } else {
      let donut = null;
      try {
        donut = JSON.parse(el.textContent);
      } catch (e) {
        console.warn("[home.js] donut-data JSON 파싱 실패:", e);
        donut = null;
      }

      // donut이 None이면 기록 없음 상태 → 템플릿에서 empty-state가 이미 처리
      if (donut) {
        const pos_count = Number(donut.pos_count ?? 0);
        const rest_count = Number(donut.rest_count ?? 0);
        const total = Number(donut.total ?? 0);

        if (total > 0) {
          const canvas = document.getElementById("positiveDonutChart");
          // donut 섹션이 empty-state면 canvas가 없을 수 있음(정상)
          if (canvas) {
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
          }
        }
      }
    }
  }

  /* =========================================================
     2) 오늘 먹은 것들 (막대 그래프: g 기준)
     ========================================================= */

  const payloadEl = document.getElementById("foodPayload");
  const rowsEl = document.getElementById("foodRows");

  if (!payloadEl) {
    console.warn("[home.js] foodPayload script 태그 없음");
  } else if (!rowsEl) {
    console.warn("[home.js] foodRows 컨테이너 없음");
  } else {
    let payload;
    try {
      payload = JSON.parse(payloadEl.textContent);
    } catch (e) {
      console.error("[home.js] foodPayload JSON 파싱 실패", e);
      payload = null;
    }

    if (!payload || !Array.isArray(payload.slots)) {
      console.warn("[home.js] foodPayload 구조 이상", payload);
    } else {
      rowsEl.innerHTML = "";

      payload.slots.forEach((slot) => {
        const row = document.createElement("div");
        row.className = "food-row";

        // 왼쪽: 아침/점심/저녁
        const slotEl = document.createElement("div");
        slotEl.className = "food-slot";
        slotEl.textContent = slot.label ?? "";

        // 가운데: kcal
        const kcalEl = document.createElement("div");
        kcalEl.className = "food-kcal";
        kcalEl.textContent = slot.kcal_display ?? "-";
        if (kcalEl.textContent === "-") {
          kcalEl.classList.add("is-dash");
        }

        // 오른쪽: bar
        const bar = document.createElement("div");
        bar.className = "food-bar";

        const totalG = Number(slot.total_g ?? 0);
        if (!totalG || totalG <= 0) {
          bar.classList.add("is-empty");
        }

        (slot.segments || []).forEach((seg) => {
          const segEl = document.createElement("div");
          segEl.className = `food-seg ${seg.key}`;

          const pct = typeof seg.pct === "number" ? seg.pct : Number(seg.pct ?? 0);
          const safePct = Math.max(0, Math.min(1, isFinite(pct) ? pct : 0));
          segEl.style.width = `${safePct * 100}%`;

          if (seg.showText) {
            segEl.textContent = `${Math.round(Number(seg.g ?? 0))}g`;
          } else {
            segEl.classList.add("no-text");
            // 텍스트 숨김이어도 세그먼트 높이/정렬 유지용(투명 처리됨)
            segEl.textContent = "0g";
          }

          bar.appendChild(segEl);
        });

        // tooltip: bar 전체 1개 (빈 슬롯이면 비활성)
        if (slot.tooltip_enabled) {
          bar.title = slot.tooltip_text ?? "";
        }

        row.appendChild(slotEl);
        row.appendChild(kcalEl);
        row.appendChild(bar);

        rowsEl.appendChild(row);
      });
    }
  }

  /* =========================================================
     3) Home - Daily Report Section
     ========================================================= */

  const section = document.getElementById("section-daily-report");
  if (!section) return;

  const todayYmd = section.dataset.todayYmd || ""; // "YYYYMMDD"
  const hasReport = section.dataset.hasReport === "1";

  const elDateTop = document.getElementById("dailyReportDateTop");
  const elContent = document.getElementById("dailyReportContent");
  if (!elDateTop || !elContent) return;

  const monthNames = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];

  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  function ymdToMonthDayEnglish(ymd) {
    if (!ymd || ymd.length !== 8) {
      const d = new Date();
      return `${monthNames[d.getMonth()]}, ${pad2(d.getDate())}`;
    }
    const m = Number(ymd.slice(4, 6));
    const d = Number(ymd.slice(6, 8));
    const month = monthNames[Math.max(0, Math.min(11, m - 1))];
    return `${month}, ${pad2(d)}`;
  }

  elDateTop.textContent = ymdToMonthDayEnglish(todayYmd);

  const serverContent = (elContent.textContent || "").trim();

  function isAfterOrAt20() {
    const now = new Date(); // 클라이언트 시간
    const hh = now.getHours();
    const mm = now.getMinutes();
    return hh > 20 || (hh === 20 && mm >= 0);
  }

  function setStatusMessageBefore20() {
    elContent.classList.add("is-empty");
    elContent.textContent = "리포트가 생성중입니다.\n저녁 8시 이후 확인해 주세요.";
  }

  function setStatusMessageAfter20() {
    elContent.classList.add("is-empty");
    elContent.textContent = "오늘 기록을 하지 않았어요. 기록을 남기면 리포트가 생성돼요.";
  }

  const finalHasContent = hasReport && serverContent.length > 0;

  if (!finalHasContent) {
    if (isAfterOrAt20()) setStatusMessageAfter20();
    else setStatusMessageBefore20();
  } else {
    elContent.classList.remove("is-empty");
  }
});
