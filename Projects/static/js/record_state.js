// static/js/record_state.js
// BEAR 정답: session ctx(rgs_dt, seq, time_slot)를 단일 원천으로 사용

function getCtx() {
  const rgsDt = (document.getElementById("ctx-rgs-dt")?.value || "").trim();
  const seq = (document.getElementById("ctx-seq")?.value || "").trim();
  const timeSlot = (document.getElementById("ctx-time-slot")?.value || "").trim();

  if (!rgsDt || !seq || !timeSlot) {
    console.error("[record_state] missing session ctx", { rgsDt, seq, timeSlot });
    return null;
  }
  return { rgsDt, seq, timeSlot };
}

document.addEventListener("DOMContentLoaded", () => {
  // 1) focus=search 처리(기존 대화 기능 유지)
  const params = new URLSearchParams(location.search);
  if (params.get("focus") === "search") {
    const input = document.getElementById("food-search-input");
    if (input) {
      input.focus();
      input.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }

  // 2) ctx 확인(없으면 페이지 기능 제한)
  const ctx = getCtx();
  if (!ctx) {
    // 카드만 초기 상태로 두고 종료(사용자에게 감정 기록부터 유도)
    return;
  }

  // 3) camera 버튼: session 유지 이동
  const camBtn = document.getElementById("btn-camera");
  if (camBtn) {
    camBtn.addEventListener("click", (e) => {
      e.preventDefault();
      location.href = "/record/camera/";
    });
  }

  // 4) 최근 3카드: (권장) DB API로 채우기
  //   - 이 단계는 record_state가 아니라, api_meals_recent3 응답 스펙 확정 후 붙이는 게 안전함
  //   - 지금은 꼬임 방지 위해 비워둠
});
