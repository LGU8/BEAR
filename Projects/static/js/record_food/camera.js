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

// ✅ CSRF 토큰을 cookie에서 읽는 공통 함수 (1단계 A안)
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== "") {
    const cookies = document.cookie.split(";");
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.startsWith(name + "=")) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
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
  // 필요하면 rgs_dt/time_slot 유지해서 돌아가도록 확장 가능
  // location.href = `/record/meal/?rgs_dt=${encodeURIComponent(rgsDt)}&time_slot=${encodeURIComponent(timeSlot)}`;
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

let scanMode = "barcode"; // 기본값
console.log("[init] scanMode =", scanMode);

(async function () {
  const params = new URLSearchParams(location.search);

  // ✅ 1) 진짜 기준값: rgs_dt(YYYYMMDD), time_slot(M/L/D)
  const rgsDt = params.get("rgs_dt");
  const timeSlot = params.get("time_slot");

  // ✅ 2) 없으면 fallback 금지 → 기록 흐름이 끊긴 것
  if (!rgsDt || !timeSlot) {
    console.error("[camera] missing rgs_dt/time_slot. query=", location.search);
    alert("식단 기록 정보(rgs_dt/time_slot)가 없습니다. 감정 기록부터 다시 진행해주세요.");
    safeGoBackToMeal(rgsDt, timeSlot);
    return;
  }

  // ✅ 3) UI/기존 API 호환용: date/meal로 변환 (필요할 때만 사용)
  function rgsDtToDate(yyyymmdd) {
    // "20251224" -> "2025-12-24"
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

  // ===== Guard: HTTPS / Secure Context =====
  // HTTP(insecure)에서는 navigator.mediaDevices 자체가 undefined가 되는 경우가 많음
  if (!window.isSecureContext) {
    console.error("[camera] insecure context. protocol=", location.protocol);

    // 사용자에게 확실히 안내
    setCameraStatus("카메라는 HTTPS 환경에서만 사용할 수 있어요. 주소를 https로 접속해 주세요.");

    // (선택) 자동 https 리다이렉트: 커스텀 도메인/HTTPS가 붙어있을 때만 의미 있음
    // if (location.protocol === "http:") {
    //   const httpsUrl = "https://" + location.host + location.pathname + location.search + location.hash;
    //   console.log("[camera] redirect to", httpsUrl);
    //   location.replace(httpsUrl);
    // }

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

  // 버튼 활성화는 메타데이터 로드 이후(영상 크기 확보)로 유지
  video.addEventListener("loadedmetadata", () => {
    enableShoot(btnShoot);
  });

  // 1) 카메라 켜기 (try/catch로 권한/장치 오류 처리)
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

  // 페이지 이탈/리로드 시 카메라 끄기(리소스 누수 방지)
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

    // 1) 토글 버튼 UI 동기화
    document.querySelectorAll(".scan-toggle-btn").forEach((b) => {
      const on = b.dataset.scanMode === scanMode;
      b.classList.toggle("is-active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });

    // 2) 안내 문구 변경
    if (descEl) {
      descEl.textContent =
        scanMode === "barcode"
          ? "네모칸 안에 바코드를 스캔해주세요"
          : "네모칸 안에 영양성분을 스캔해주세요";
    }

    // 3) 가이드 박스 모드 class 변경
    if (stageEl) {
      stageEl.classList.toggle("is-barcode", scanMode === "barcode");
      stageEl.classList.toggle("is-nutrition", scanMode === "nutrition");
    }

    console.log("[setScanMode] scanMode =", scanMode);
  }

  // 초기값: HTML의 is-active 기준으로 동기화
  const active = document.querySelector(".scan-toggle-btn.is-active");
  setScanMode(active?.dataset.scanMode || "barcode");

  // 클릭 이벤트
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
    disableShoot(btnShoot);

    // video 준비 확인
    if (!video.videoWidth) {
      enableShoot(btnShoot);
      alert("카메라 준비가 아직 안 됐어요. 잠시 후 다시 눌러주세요.");
      return;
    }

    // 1) 캔버스(#cam-canvas)에 현재 프레임 캡처
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);

    // 2) Blob으로 변환 → 서버로 업로드
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

        // ✅ 기준값(저장/세션 매칭용)
        fd.append("rgs_dt", rgsDt);
        fd.append("time_slot", timeSlot);

        // ✅ 호환/표시용
        fd.append("date", date);
        fd.append("meal", meal);

        fd.append("mode", scanMode);

        // ✅ mode에 따라 endpoint 분기
        const endpoint =
          scanMode === "nutrition" ? "/record/api/ocr/job/create/" : "/record/api/scan/barcode/";

        console.log("[shoot] endpoint =", endpoint);

        // ✅ CSRF token
        const csrftoken = getCookie("csrftoken");

        let res = null;
        try {
          res = await fetch(endpoint, {
            method: "POST",
            body: fd,
            credentials: "same-origin",
            headers: {
              "X-CSRFToken": csrftoken,
            },
          });
        } catch (e) {
          console.error("[fetch] failed", e);
          alert("네트워크 오류로 서버에 요청하지 못했어요. 잠시 후 다시 시도해 주세요.");
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

        // ✅ nutrition 모드: job_id 받고 result로 이동
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
          // 1) 인식 실패 → 카메라에서 재시도
          if (data.reason === "SCAN_FAIL") {
            showScanFailUI(data.message);
            // showScanFailUI 안에서 버튼을 다시 활성화하도록 되어 있음
            return;
          }

          // 2) 후보 없음 → record 페이지 이동 + 검색창 포커스
          const isNoMatch =
            data.reason === "NO_MATCH" || data.error === "no candidates found";

          if (isNoMatch) {
            alert(data.message || "해당 바코드로 조회되는 제품이 없습니다. 검색으로 추가해 주세요.");
            location.href =
              `/record/?date=${encodeURIComponent(date)}` +
              `&meal=${encodeURIComponent(meal)}` +
              `&focus=search`;
            return;
          }

          // 3) 그 외 에러
          alert(data.message || data.error || "바코드 처리 중 오류가 발생했어요.");
          enableShoot(btnShoot);
          return;
        }

        // ✅ barcode 성공: draft_id로 result 페이지 이동
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
