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
  const date = params.get("date") || new Date().toISOString().slice(0,10);
  const meal = params.get("meal") || "breakfast";

  const video = document.getElementById("cam-video");
  const canvas = document.getElementById("cam-canvas");
  const btnShoot = document.getElementById("btn-shoot");
  btnShoot.disabled = true;               // ✅ 처음엔 비활성
  btnShoot.style.opacity = "0.6";
  btnShoot.style.pointerEvents = "none";

  video.addEventListener("loadedmetadata", () => {
    btnShoot.disabled = false;            // ✅ 메타데이터 준비 후 활성화
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

  if (!video.videoWidth) return;

  // 1) 캔버스(#cam-canvas)에 현재 프레임 캡처 (재사용)
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);

  // 2) Blob으로 변환 → 서버로 업로드
  canvas.toBlob(async (blob) => {
    const fd = new FormData();
    fd.append("image", blob, "barcode.jpg");
    fd.append("date", date);
    fd.append("meal", meal);
    fd.append("mode", scanMode);

    const rgsDt = (document.getElementById("ctx-rgs-dt")?.value || "").trim();
    const seq = (document.getElementById("ctx-seq")?.value || "").trim();
    const timeSlot = (document.getElementById("ctx-time-slot")?.value || "").trim();

    if (!rgsDt || !seq || !timeSlot) {
      alert("감정 기록(session)이 없어서 스캔할 수 없어요. 감정 기록부터 진행해 주세요.");
      return;
    }
    
    const res = await fetch("/record/api/scan/barcode/", {
      method: "POST",
      body: fd,
      credentials: "same-origin",
    });

    const raw = await res.text();
    console.log("[scan] status", res.status);
    console.log("[scan] raw", raw.slice(0, 600));

    let data = null;
    try {
      data = JSON.parse(raw);
    } catch (e) {
      alert("서버 응답이 JSON이 아니에요(500/HTML일 수 있음). 콘솔 raw를 확인해줘.");
      return;
    }

    console.log("[scan] json", data);

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

    // 3) draft_id 받아서 result 페이지로 이동
    location.href =
      `/record/scan/result/?date=${encodeURIComponent(date)}` +
      `&meal=${encodeURIComponent(meal)}` +
      `&draft_id=${encodeURIComponent(data.draft_id)}`;

  }, "image/jpeg", 0.85);
});
})();
