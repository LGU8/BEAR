// static/js/camera.js

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

  btnShoot.addEventListener("click", async () => {
    if (!video.videoWidth || !video.videoHeight) {
      console.warn("[shoot] video metadata not ready yet");
      return;
    }
  
  if (!video || !canvas || !btnShoot) {
  console.error("[camera] missing element", { video, canvas, btnShoot });
  return;
  }
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

  // 3) 가이드 박스 모드 class 변경
  if (descEl) {
    descEl.textContent =
      (scanMode === "barcode")
        ? "네모칸 안에 바코드를 스캔해주세요"
        : "네모칸 안에 영양성분을 스캔해주세요";
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
  if (!video.videoWidth) return;

  // 1) 캔버스에 현재 프레임 캡처
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);

  // 2) Blob으로 변환 → 서버로 업로드
  canvas.toBlob(async (blob) => {
    const fd = new FormData();
    fd.append("image", blob, "barcode.jpg");
    fd.append("date", date);
    fd.append("meal", meal);

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
      if (data.reason === "NO_MATCH") {
        // ✅ 후보 없음 UX
        alert(data.message || "해당 바코드로 제품을 찾을 수 없어요.");

        // 선택지 UI를 띄우는 방식 3개 중 택1
        // 1) 재촬영: 그냥 return (사용자가 다시 찍음)
        // 2) 수동입력: 바코드 입력 모달/페이지로 이동
        // 3) 검색: 기존 검색 기록 플로우로 이동

        return;
      }
      
      alert(data.message || data.error || "바코드 처리 실패");
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
