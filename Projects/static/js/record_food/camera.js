// static/js/camera.js

console.log("[camera.js] LOADED ✅", location.href);

function showScanFailUI(msg) {
  const statusEl = document.getElementById("camera-desc");
  if (statusEl) {
    statusEl.textContent =
      msg ||
      "바코드를 인식하지 못했어요. 바코드를 네모칸 안에 맞추고 다시 시도해 주세요.";
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

// ✅ CSRF 토큰을 cookie에서 읽는 함수 (정규식 버전: 안정적)
function getCookie(name) {
  const v = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
  return v ? v.pop() : "";
}

// ✅ 공통 POST(fetch) 래퍼: 쿠키 포함 + CSRF 헤더 확정
async function postWithCSRF(url, formData) {
  const csrftoken = getCookie("csrftoken");

  if (!csrftoken) {
    console.error("[CSRF] csrftoken not found. document.cookie=", document.cookie);
    alert(
      "CSRF 토큰(csrftoken)을 찾지 못했어요.\n" +
        "페이지를 새로고침한 뒤 다시 시도해 주세요.\n" +
        "(서버에서 CSRF 쿠키 발급이 안 된 상태일 수 있어요)"
    );
    throw new Error("CSRF token missing");
  }

  return fetch(url, {
    method: "POST",
    body: formData,
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": csrftoken,
    },
  });
}

// ===== UI helpers =====
function setCameraStatus(msg) {
  const el = document.getElementById("camera-desc");
  if (el) el.textContent = msg;
  console.log("[camera][status]", msg);
}

function enableShoot(btn) {
  if (!btn) return;
  btn.disabled = false;
  btn.style.opacity = "1";
  btn.style.pointerEvents = "auto";
}

function disableShoot(btn) {
  if (!btn) return;
  btn.disabled = true;
  btn.style.opacity = "0.6";
  btn.style.pointerEvents = "none";
}

function safeGoBackToMeal(rgsDt, timeSlot) {
  location.href = "/record/meal/";
}

function stopStream(stream) {
  try {
    if (!stream) return;
    stream.getTracks().forEach((t) => t.stop());
  } catch (e) {
    console.warn("[camera] stopStream failed", e);
  }
}

let scanMode = "barcode";
console.log("[init] scanMode =", scanMode);

(async function () {
  const params = new URLSearchParams(location.search);

  // ✅ 1) 기준값: rgs_dt(YYYYMMDD), time_slot(M/L/D)
  const hiddenRgsDt = document.getElementById("ctx-rgs-dt")?.value || "";
  const hiddenTimeSlot = document.getElementById("ctx-time-slot")?.value || "";

  const rgsDt = params.get("rgs_dt") || hiddenRgsDt;
  const timeSlot = params.get("time_slot") || hiddenTimeSlot;

  if (!rgsDt || !timeSlot) {
    console.error("[camera] missing rgs_dt/time_slot. query=", location.search);
    alert("식단 기록 정보(rgs_dt/time_slot)가 없습니다. 감정 기록부터 다시 진행해주세요.");
    safeGoBackToMeal(rgsDt, timeSlot);
    return;
  }

  function rgsDtToDate(yyyymmdd) {
    return `${yyyymmdd.slice(0, 4)}-${yyyymmdd.slice(4, 6)}-${yyyymmdd.slice(6, 8)}`;
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
    safeGoBackToMeal(rgsDt, timeSlot);
    return;
  }

  const video = document.getElementById("cam-video");
  const canvas = document.getElementById("cam-canvas");
  const btnShoot = document.getElementById("btn-shoot");

  // ✅ 처음엔 비활성
  disableShoot(btnShoot);

  // ===== Guard: DOM 존재 확인 =====
  if (!video || !canvas || !btnShoot) {
    console.error("[camera] missing DOM elements", { video, canvas, btnShoot });
    alert("카메라 화면 구성 요소를 찾지 못했어요. (cam-video/cam-canvas/btn-shoot)");
    safeGoBackToMeal(rgsDt, timeSlot);
    return;
  }

  // ✅ iOS Safari 안정화를 위한 속성(HTML에 있어도 한 번 더 세팅)
  // - playsinline: 전체화면 전환/재생 정책 이슈 감소
  // - muted: autoplay/play 허용 가능성 증가
  // - autoplay: 일부 브라우저에서 play 트리거 보조
  video.setAttribute("playsinline", "");
  video.setAttribute("webkit-playsinline", "");
  video.muted = true;
  video.autoplay = true;

  // ===== Guard: HTTPS / Secure Context =====
  if (!window.isSecureContext) {
    console.error("[camera] insecure context. protocol=", location.protocol);
    setCameraStatus("카메라는 HTTPS 환경에서만 사용할 수 있어요. 주소를 https로 접속해 주세요.");
    disableShoot(btnShoot);
    return;
  }

  // ===== Guard: getUserMedia 지원 여부 =====
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    console.error("[camera] mediaDevices/getUserMedia not available", navigator.mediaDevices);
    setCameraStatus("이 환경에서는 카메라 기능을 사용할 수 없어요. (브라우저/보안 설정 확인)");
    disableShoot(btnShoot);
    return;
  }

  // ✅ 버튼 활성화 트리거를 다양화(loadedmetadata만 믿지 않기)
  const tryEnable = (tag) => {
    console.log(`[camera] enable trigger: ${tag}`, {
      readyState: video.readyState,
      paused: video.paused,
      w: video.videoWidth,
      h: video.videoHeight,
    });

    // videoWidth가 0이어도, "일단 버튼은 켜서 사용자가 눌러볼 수 있게" 만드는 전략
    // (클릭 시 videoWidth 0이면 안내 후 다시 활성화하므로 안전)
    enableShoot(btnShoot);
  };

  video.addEventListener("loadedmetadata", () => tryEnable("loadedmetadata"));
  video.addEventListener("loadeddata", () => tryEnable("loadeddata"));
  video.addEventListener("canplay", () => tryEnable("canplay"));

  // 1) 카메라 켜기
  let stream = null;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" },
      audio: false,
    });
  } catch (e) {
    console.error("[camera] getUserMedia failed:", e);
    const name = e?.name || "UnknownError";

    const msg =
      name === "NotAllowedError"
        ? "카메라 권한이 거부됐어요. 브라우저 사이트 설정에서 카메라를 허용해 주세요."
        : name === "NotFoundError"
        ? "사용 가능한 카메라 장치를 찾지 못했어요."
        : name === "NotReadableError"
        ? "카메라를 사용할 수 없어요. 다른 앱이 카메라를 사용 중인지 확인해 주세요."
        : `카메라 실행에 실패했어요. (${name})`;

    setCameraStatus(msg);
    disableShoot(btnShoot);
    return;
  }

  // 스트림 연결
  video.srcObject = stream;

  // ✅ iOS/모바일에서 srcObject만으로는 재생이 시작 안 되는 케이스가 많아서 play() 시도
  try {
    const p = video.play();
    if (p && typeof p.then === "function") {
      await p;
    }
    console.log("[camera] video.play() OK");
  } catch (e) {
    // play()가 막혀도 스트림은 붙어있을 수 있음. 대신 버튼을 켜서 사용자가 재시도하게 함.
    console.warn("[camera] video.play() blocked or failed:", e);
    setCameraStatus("카메라가 자동 재생되지 않을 수 있어요. 버튼을 눌러 캡처를 시도해 주세요.");
  }

  // ✅ play 성공/실패와 관계없이, 최소한 버튼은 켜는 fallback
  // (이게 없으면 loadedmetadata 미발생 시 버튼 영원히 disabled로 남을 수 있음)
  setTimeout(() => {
    if (btnShoot.disabled) {
      console.warn("[camera] fallback enableShoot after timeout");
      enableShoot(btnShoot);
    }
  }, 700);

  window.addEventListener("beforeunload", () => stopStream(stream));

  // ===== scan mode init =====
  const activeToggle = document.querySelector(".scan-toggle-btn.is-active");
  scanMode = activeToggle?.dataset.scanMode || "barcode";
  console.log("[init] scanMode =", scanMode);

  // ===== scan mode UI sync =====
  const stageEl = document.getElementById("camera-stage");
  const descEl = document.getElementById("camera-desc");

  function setScanMode(nextMode) {
    scanMode = nextMode === "nutrition" ? "nutrition" : "barcode";

    document.querySelectorAll(".scan-toggle-btn").forEach((b) => {
      const on = b.dataset.scanMode === scanMode;
      b.classList.toggle("is-active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });

    if (descEl) {
      descEl.textContent =
        scanMode === "barcode"
          ? "네모칸 안에 바코드를 스캔해주세요"
          : "네모칸 안에 영양성분을 스캔해주세요";
    }

    if (stageEl) {
      stageEl.classList.toggle("is-barcode", scanMode === "barcode");
      stageEl.classList.toggle("is-nutrition", scanMode === "nutrition");
    }

    console.log("[setScanMode] scanMode =", scanMode);
  }

  const active = document.querySelector(".scan-toggle-btn.is-active");
  setScanMode(active?.dataset.scanMode || "barcode");

  document.querySelectorAll(".scan-toggle-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const next = btn.dataset.scanMode || "barcode";
      setScanMode(next);
      console.log("[toggle] changed to =", next, " / now scanMode =", scanMode);
    });
  });

  // ===== shoot =====
  btnShoot.addEventListener("click", async () => {
    alert("CLICK OK");
    console.log("[CAMERA] REAL CLICK ✅", {
      disabled: btnShoot.disabled,
      readyState: video.readyState,
      paused: video.paused,
      w: video.videoWidth,
      h: video.videoHeight,
      mode: scanMode,
    });

    disableShoot(btnShoot);

    // video 준비 확인
    if (!video.videoWidth) {
      enableShoot(btnShoot);
      alert("카메라 준비가 아직 안 됐어요. 잠시 후 다시 눌러주세요.");
      return;
    }

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);

    canvas.toBlob(
      async (blob) => {
        if (!blob) {
          alert("이미지 변환에 실패했어요. 다시 시도해 주세요.");
          enableShoot(btnShoot);
          return;
        }

        const fd = new FormData();
        const filename = scanMode === "nutrition" ? "nutrition.jpg" : "barcode.jpg";
        fd.append("image", blob, filename);

        fd.append("rgs_dt", rgsDt);
        fd.append("time_slot", timeSlot);

        fd.append("date", date);
        fd.append("meal", meal);

        fd.append("mode", scanMode);

        const endpoint =
          scanMode === "nutrition"
            ? "/record/api/ocr/job/create/"
            : "/record/api/scan/barcode/";

        console.log("[shoot] endpoint =", endpoint);

        let res = null;
        try {
          res = await postWithCSRF(endpoint, fd);
        } catch (e) {
          console.error("[postWithCSRF] failed", e);
          enableShoot(btnShoot);
          return;
        }

        const raw = await res.text();
        console.log("[scan] endpoint", endpoint);
        console.log("[scan] status", res.status);
        console.log("[scan] raw", raw.slice(0, 600));

        let data = null;
        try {
          data = JSON.parse(raw);
        } catch (e) {
          alert("서버 응답이 JSON이 아니에요(500/HTML일 수 있음). 콘솔 raw를 확인해줘.");
          enableShoot(btnShoot);
          return;
        }

        if (data && data.ok && data.job_id) {
          sessionStorage.setItem("ocr_job_id", data.job_id);
          console.log("[camera.js] saved ocr_job_id =", data.job_id);
        } else {
          console.warn("[camera.js] job_id missing / response not ok:", data);
        }

        console.log("[scan] json", data);

        if (scanMode === "nutrition") {
          if (!data.ok) {
            alert(data.message || data.error || "OCR 작업 생성 중 오류가 발생했어요.");
            enableShoot(btnShoot);
            return;
          }

          location.href =
            `/record/scan/result/?rgs_dt=${encodeURIComponent(rgsDt)}` +
            `&time_slot=${encodeURIComponent(timeSlot)}` +
            `&date=${encodeURIComponent(date)}` +
            `&meal=${encodeURIComponent(meal)}` +
            `&mode=nutrition` +
            `&job_id=${encodeURIComponent(data.job_id)}`;
          return;
        }

        // ✅ barcode 모드
        if (!data.ok) {
          if (data.reason === "SCAN_FAIL") {
            showScanFailUI(data.message);
            // showScanFailUI 내부에서 버튼 다시 활성화함
            return;
          }

          const isNoMatch =
            data.reason === "NO_MATCH" || data.error === "no candidates found";

          if (isNoMatch) {
            alert(
              data.message ||
                "해당 바코드로 조회되는 제품이 없습니다. 검색으로 추가해 주세요."
            );
            location.href =
              `/record/?date=${encodeURIComponent(date)}` +
              `&meal=${encodeURIComponent(meal)}` +
              `&focus=search`;
            return;
          }

          alert(data.message || data.error || "바코드 처리 중 오류가 발생했어요.");
          enableShoot(btnShoot);
          return;
        }

        // ✅ barcode 성공
        location.href =
          `/record/scan/result/?rgs_dt=${encodeURIComponent(rgsDt)}` +
          `&time_slot=${encodeURIComponent(timeSlot)}` +
          `&date=${encodeURIComponent(date)}` +
          `&meal=${encodeURIComponent(meal)}` +
          `&draft_id=${encodeURIComponent(data.draft_id)}`;
      },
      "image/jpeg",
      0.92
    );
  });
})();
