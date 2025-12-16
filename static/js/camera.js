// static/js/camera.js

let scanMode = "barcode"; // 기본값


(async function () {
  const params = new URLSearchParams(location.search);
  const date = params.get("date");
  const meal = params.get("meal");

  const video = document.getElementById("cam-video");
  const canvas = document.getElementById("cam-canvas");
  const btnShoot = document.getElementById("btn-shoot");
  
  if (!video || !canvas || !btnShoot) {
  console.error("[camera] missing element", { video, canvas, btnShoot });
  return;
}

  document.querySelectorAll(".scan-toggle-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    scanMode = btn.dataset.scanMode;

    console.log("TOGGLE CLICKED =>", scanMode);
    console.log("[toggle] scanMode =", scanMode);


    document.querySelectorAll(".scan-toggle-btn").forEach(b => {
      b.classList.remove("is-active");
      b.setAttribute("aria-selected", "false");
    });

    btn.classList.add("is-active");
    btn.setAttribute("aria-selected", "true");
  });
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
    // 2) 캡처
    console.log("[shoot] clicked");
    console.log("SAVE MODE =>", scanMode);
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0);

    // 3) 이미지 DataURL 저장
    const dataUrl = canvas.toDataURL("image/png");

    // 4) (UI 단계) 인식 결과 더미
    //    나중에 /record/api/scan/ 으로 보내서 OCR/Barcode 결과 받아오면 됨
    const fakeResult = {
      brand: "브랜드명(임시)",
      name: "제품명(임시)",
      kcal: "200",
      carb: "30",
      protein: "10",
      fat: "5",
    };

    // 5) localStorage에 저장(결과 페이지에서 읽기)
    const key = `scanDraft:${date}:${meal}`;
    localStorage.setItem(key, JSON.stringify({ date, meal, mode: scanMode, image: dataUrl, result: fakeResult }));

    // 6) 결과 페이지로 이동
    location.href = `/record/scan/result/?date=${encodeURIComponent(date)}&meal=${encodeURIComponent(meal)}`;
  });
})();
