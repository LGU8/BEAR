// static/js/camera.js

function showScanFailUI(msg) {
  const statusEl = document.getElementById("camera-desc");
  if (statusEl) {
    statusEl.textContent =
      msg || "바코드를 인식하지 못했어요. 바코드를 네모칸 안에 맞추고 다시 시도해 주세요.";
  } else {
    alert(msg || "바코드를 인식하지 못했어요. 다시 시도해 주세요.");
  }

  const btn = document.getElementById("btn-shoot");
  if (btn) {
    btn.disabled = false;
    btn.style.opacity = "1";
    btn.style.pointerEvents = "auto";
  }
}


let scanMode = "barcode"; // 기본값


(async function () {
  const params = new URLSearchParams(location.search);
  // ✅ 1) 진짜 기준값: rgs_dt(YYYYMMDD), time_slot(M/L/D)
  const rgsDt = params.get("rgs_dt");
  const timeSlot = params.get("time_slot");

   // ✅ 2) 없으면 fallback 금지 → 기록 흐름이 끊긴 것
  if (!rgsDt || !timeSlot) {
    console.error("[camera] missing rgs_dt/time_slot. query=", location.search);
    alert("식단 기록 정보(rgs_dt/time_slot)가 없습니다. 감정 기록부터 다시 진행해주세요.");
    location.href = "/record/meal/";
    return;
  }

  // ✅ 3) UI/기존 API 호환용: date/meal로 변환 (필요할 때만 사용)
  function rgsDtToDate(yyyymmdd) {
    // "20251224" -> "2025-12-24"
    return `${yyyymmdd.slice(0,4)}-${yyyymmdd.slice(4,6)}-${yyyymmdd.slice(6,8)}`;
  }
  function slotToMeal(slot) {
    if (slot === "M") return "breakfast";
    if (slot === "L") return "lunch";
    if (slot === "D") return "dinner";
    return "";
  }

  const date = rgsDtToDate(rgsDt);
  const meal = slotToMeal(timeSlot);

  if (!meal) {
    console.error("[camera] invalid time_slot:", timeSlot);
    alert("시간 정보(time_slot)가 올바르지 않습니다.");
    location.href = "/record/meal/";
    return;
  }

  const video = document.getElementById("cam-video");
  const canvas = document.getElementById("cam-canvas");
  const btnShoot = document.getElementById("btn-shoot");
  btnShoot.disabled = true;               // ✅ 처음엔 비활성
  btnShoot.style.opacity = "0.6";
  btnShoot.style.pointerEvents = "none";

  video.addEventListener("loadedmetadata", () => {
  btnShoot.disabled = false;
  btnShoot.style.opacity = "1";
  btnShoot.style.pointerEvents = "auto";
});

  // 1) 카메라 켜기
  const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
  video.srcObject = stream;

  const activeToggle = document.querySelector(".scan-toggle-btn.is-active");
  scanMode = activeToggle?.dataset.scanMode || "barcode";
  console.log("[init] scanMode =", scanMode);

  // ===== scan mode UI sync =====
const stageEl = document.getElementById("camera-stage");
const descEl = document.getElementById("camera-desc");

function setScanMode(nextMode) {
  scanMode = nextMode;

  // 1) 토글 버튼 UI 동기화
  document.querySelectorAll(".scan-toggle-btn").forEach(b => {
    const on = b.dataset.scanMode === scanMode;
    b.classList.toggle("is-active", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });

  // 2) 안내 문구 변경
  if (descEl) {
    descEl.textContent =
      (scanMode === "barcode")
        ? "네모칸 안에 바코드를 스캔해주세요"
        : "네모칸 안에 영양성분을 스캔해주세요";
  }


  // 3) 가이드 박스 모드 class 변경 (예: camera-stage에 모드 클래스 부여)
  if (stageEl) {
    stageEl.classList.toggle("is-barcode", scanMode === "barcode");
    stageEl.classList.toggle("is-nutrition", scanMode === "nutrition");
  }
}

// 초기값: HTML의 is-active 기준으로 동기화
const active = document.querySelector(".scan-toggle-btn.is-active");
setScanMode(active?.dataset.scanMode || "barcode");

// 클릭 이벤트
document.querySelectorAll(".scan-toggle-btn").forEach(btn => {
  btn.addEventListener("click", () => setScanMode(btn.dataset.scanMode));
});


  btnShoot.addEventListener("click", async () => {

  btnShoot.disabled = true;
  btnShoot.style.opacity = "0.6";
  btnShoot.style.pointerEvents = "none";

  if (!video.videoWidth) {
    btnShoot.disabled = false;
    btnShoot.style.opacity = "1";
    btnShoot.style.pointerEvents = "auto";
    alert("카메라 준비가 아직 안 됐어요. 잠시 후 다시 눌러주세요.");
    return;
  }

  // 1) 캔버스(#cam-canvas)에 현재 프레임 캡처 (재사용)
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);

  // 2) Blob으로 변환 → 서버로 업로드
  canvas.toBlob(async (blob) => {

    if (!blob) {
    alert("이미지 변환에 실패했어요. 다시 시도해 주세요.");
    btnShoot.disabled = false;
    btnShoot.style.opacity = "1";
    btnShoot.style.pointerEvents = "auto";
    return;
  }
    
    const fd = new FormData();
    const filename = (scanMode === "nutrition") ? "nutrition.jpg" : "barcode.jpg";
    fd.append("image", blob, filename);

    // ✅ 기준값(저장/세션 매칭용)
    fd.append("rgs_dt", rgsDt);
    fd.append("time_slot", timeSlot);
    
    // ✅ 호환/표시용(기존 로직이 date/meal 쓰는 경우 대비)
    fd.append("date", date);
    fd.append("meal", meal);

    fd.append("mode", scanMode);

    // ✅ 1) mode에 따라 endpoint 분기
    // - barcode: 기존 그대로(동기 처리)
    // - nutrition: OCR job 생성(= S3 업로드 + CUS_OCR_TH 대기 레코드 생성)
    const endpoint =
    (scanMode === "nutrition")
      ? "/record/api/ocr/job/create/"
      : "/record/api/scan/barcode/";

    // ✅ 2) 요청
    const res = await fetch(endpoint, {
      method: "POST",
      body: fd,
      credentials: "same-origin",
    });

    // ✅ 3) 응답 파싱(일단 text로 받고 JSON으로 변환)
    const raw = await res.text();
    console.log("[scan] endpoint", endpoint);
    console.log("[scan] status", res.status);
    console.log("[scan] raw", raw.slice(0, 600));

    let data = null;
    try {
      data = JSON.parse(raw);
    } catch (e) {
      alert("서버 응답이 JSON이 아니에요(500/HTML일 수 있음). 콘솔 raw를 확인해줘.");
      btnShoot.disabled = false;
      btnShoot.style.opacity = "1";
      btnShoot.style.pointerEvents = "auto";
      return;
    }

    console.log("[scan] json", data);

    // ✅ 4) nutrition 모드: job_id만 받고 result로 이동(Worker가 처리)
    if (scanMode === "nutrition") {
      if (!data.ok) {
        alert(data.message || data.error || "OCR 작업 생성 중 오류가 발생했어요.");
        btnShoot.disabled = false;
        btnShoot.style.opacity = "1";
        btnShoot.style.pointerEvents = "auto";
        return;
      }

    // ✅ result 페이지로 job_id 전달 (result.js에서 polling)
    location.href =
      `/record/scan/result/?rgs_dt=${encodeURIComponent(rgsDt)}` +
      `&time_slot=${encodeURIComponent(timeSlot)}` +
      `&date=${encodeURIComponent(date)}` +
      `&meal=${encodeURIComponent(meal)}` +
      `&mode=nutrition` +
      `&job_id=${encodeURIComponent(data.job_id)}`;
    return;
  }

    // ✅ 5) barcode 모드: 기존 로직 그대로 유지(아래는 너 코드 그대로)

    if (!data.ok) {
      // ✅ 1) 인식 실패면: 카메라 페이지에서 재시도
      if (data.reason === "SCAN_FAIL") {
        showScanFailUI(data.message);
        return; // ✅ record로 보내지 않음
      }

    // ✅ 2) 후보 없음이면: record 페이지로 보내고 검색창 포커스
    const isNoMatch =
      data.reason === "NO_MATCH" ||
      data.error === "no candidates found"; // 혹시 구버전 응답이 섞일 때 대비

    if (isNoMatch) {
      alert(data.message || "해당 바코드로 조회되는 제품이 없습니다. 검색으로 추가해 주세요.");
      location.href =
        `/record/?date=${encodeURIComponent(date)}` +
        `&meal=${encodeURIComponent(meal)}` +
        `&focus=search`;
      return;
    }

    // ✅ 3) 그 외 에러
    alert(data.message || data.error || "바코드 처리 중 오류가 발생했어요.");
    btnShoot.disabled = false;
    btnShoot.style.opacity = "1";
    btnShoot.style.pointerEvents = "auto";
    return;
  }

    // ✅ 6) barcode 성공: draft_id로 result 페이지 이동
    location.href =
    `/record/scan/result/?rgs_dt=${encodeURIComponent(rgsDt)}` +
    `&time_slot=${encodeURIComponent(timeSlot)}` +
    `&date=${encodeURIComponent(date)}` +
    `&meal=${encodeURIComponent(meal)}` +
    `&draft_id=${encodeURIComponent(data.draft_id)}`;
  }, "image/jpeg", 0.92);
});
})();
