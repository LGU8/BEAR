// static/js/result.js

console.log("[result.js] loaded ✅");

(function () {
  // -------------------------
  // 0) CSRF cookie
  // -------------------------
  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(";").shift();
    return "";
  }

  // -------------------------
  // 1) Helpers
  // -------------------------
  function fmtNum(v) {
    if (v === null || v === undefined || v === "") return "-";
    const n = Number(v);
    if (Number.isNaN(n)) return String(v);
    return String(n);
  }

  function isVisible(el) {
    if (!el) return false;
    // inline style 우선, 없으면 computed로 판단
    if (el.style && el.style.display) return el.style.display !== "none";
    const cs = window.getComputedStyle(el);
    return cs.display !== "none";
  }

  function showError(el, msg) {
    if (!el) return;
    el.textContent = msg;
    
    // ✅ 무조건 보이게
    el.style.display = "block";
    el.style.visibility = "visible";
    el.style.opacity = "1";

    // ✅ class로 숨기는 경우도 방어
    el.classList.remove("hidden", "is-hidden");
  }

  function clearError(el) {
    if (!el) return;
    el.textContent = "";
    el.style.display = "none";
  }

  function numOrEmpty(v) {
    const s = (v ?? "").toString().trim();
    if (!s) return null;
    const n = Number(s);
    if (!Number.isFinite(n) || n < 0) return null;
    return n;
  }

  function hasAllNutrition(candidate) {
    if (!candidate) return false;

    const kcal = candidate.kcal;
    const carb = candidate.carb_g;
    const protein = candidate.protein_g;
    const fat = candidate.fat_g;

    // null / undefined / 빈 문자열이면 false
    return (
      kcal !== null && kcal !== undefined && kcal !== "" &&
      carb !== null && carb !== undefined && carb !== "" &&
      protein !== null && protein !== undefined && protein !== "" &&
      fat !== null && fat !== undefined && fat !== ""
    );
  }

  // -------------------------
  // 2) Context & mode
  // -------------------------
  const params = new URLSearchParams(location.search);
  const draftId = params.get("draft_id");
  const modeParam = (params.get("mode") || "").toLowerCase(); // "ocr" / "nutrition" 같은 값 추천

  const panelBarcode = document.getElementById("result-barcode");
  const panelNutrition = document.getElementById("result-nutrition");

  // ✅ mode 판별: URL param 우선, 없으면 panel visibility로 fallback
  const useOcr =
    modeParam === "ocr" ||
    modeParam === "nutrition" ||
    (isVisible(panelNutrition) && !isVisible(panelBarcode));

  const btnSave = document.getElementById("btn-save");
  if (!btnSave) {
    alert("결과 페이지 UI 요소가 누락되었어요. (btn-save)");
    return;
  }

  // barcode에서만 필요한 요소
  const listEl = document.getElementById("candidate-list");

  // 공통 hidden ctx (있으면 사용, 없어도 세션 기반이라 큰 문제 없음)
  const ctxRgsDt = document.getElementById("ctx-rgs-dt")?.value || "";
  const ctxSeq = document.getElementById("ctx-seq")?.value || "";

  // -------------------------
  // 3) Barcode flow
  // -------------------------
  let selectedId = null;

    // ✅ barcode 영양 input 참조 (initBarcodeCommit에서 세팅)
  let barcodeNutr = {
    nameEl: null,
    kcalEl: null,
    carbEl: null,
    protEl: null,
    fatEl: null,
    errEl: null,
  };

  // ✅ (C안) nutr_source 기반으로 수동 입력 여부 판단
  function needManualBySource(candidate) {
    const src = (candidate && candidate.nutr_source) || "api"; // 기본 api 취급
    return src !== "api";
  }

  function showManualHintIfNeeded(candidate) {
    const { errEl } = barcodeNutr;
    if (!errEl) return;

    if (needManualBySource(candidate)) {
      showError(errEl, "일부 영양 정보가 없습니다. 직접 입력해 주세요");
    } else {
      clearError(errEl);
    }
  }

  // ✅ 후보 선택 시: input 채우기 + 입력 활성화 + 문구 표시
  function applyCandidateToNutrUI(candidate) {
    const { nameEl, kcalEl, carbEl, protEl, fatEl } = barcodeNutr;
    if (!candidate) return;

    // 1) 이름 prefill (있을 때만)
    if (nameEl) nameEl.value = candidate.name ?? "";

    // 2) 영양 prefill: C안에서는 fallback이면 null로 내려오므로, null이면 빈칸
    if (kcalEl) kcalEl.value = candidate.kcal ?? "";
    if (carbEl) carbEl.value = candidate.carb_g ?? "";
    if (protEl) protEl.value = candidate.protein_g ?? "";
    if (fatEl) fatEl.value = candidate.fat_g ?? "";

    // 3) 입력 가능하게(체크하면 입력 가능이 요구사항이었지)
    // - C안 정석: nutr_source가 api가 아니면 반드시 입력 가능
    // - 실무 추천: api여도 사용자가 수정할 수 있게 항상 enabled로 두는 편이 UX가 좋음
    if (kcalEl) kcalEl.disabled = false;
    if (carbEl) carbEl.disabled = false;
    if (protEl) protEl.disabled = false;
    if (fatEl) fatEl.disabled = false;

    // 4) 문구 표시/숨김: nutr_source로 결정
    showManualHintIfNeeded(candidate);
  }

  // ✅ 체크 해제 시: 문구 숨김 + 입력 잠금(정책)
  function resetNutrUIOnUncheck() {
    const { kcalEl, carbEl, protEl, fatEl, errEl } = barcodeNutr;

    if (errEl) clearError(errEl);

    // 해제하면 다시 잠그고 싶으면 true, 계속 열어둘 거면 false
    // 지금 요구는 “체크하면 입력 가능”이므로 해제 시 잠금이 자연스러움
    if (kcalEl) kcalEl.disabled = true;
    if (carbEl) carbEl.disabled = true;
    if (protEl) protEl.disabled = true;
    if (fatEl) fatEl.disabled = true;
  }



  function renderCandidates(candidates) {
    if (!listEl) return;

    listEl.innerHTML = (candidates || [])
      .map((c) => {
        const cid = c.candidate_id;
        const name = c.name || "";
        const brand = c.brand || "";
        const flavor = c.flavor || "";

        const kcal = fmtNum(c.kcal);
        const carb = fmtNum(c.carb_g);
        const prot = fmtNum(c.protein_g);
        const fat = fmtNum(c.fat_g);

        return `
          <label class="cand-row" data-cid="${cid}">
            <input type="checkbox" class="cand-check" value="${cid}">
            <div class="cand-body">
              <div class="cand-title"><strong>${name}</strong></div>
              <div class="cand-meta">${brand}${brand && flavor ? " · " : ""}${flavor}</div>
              <div class="cand-nutri">
                <span>${kcal} kcal</span>
                <span>탄 ${carb} g</span>
                <span>단 ${prot} g</span>
                <span>지 ${fat} g</span>
              </div>
            </div>
          </label>
        `;
      })
      .join("");

    const checks = listEl.querySelectorAll("input.cand-check");

    checks.forEach((chk) => {
      chk.addEventListener("change", () => {
        const cid = chk.value;

        if (chk.checked) {
          // 다른 체크 해제
          checks.forEach((other) => {
            if (other !== chk) other.checked = false;
          });

          selectedId = cid;
          btnSave.disabled = false;

          // ✅ 1) 선택된 candidate 찾기
          const candidate = candidates.find(
            (x) => String(x.candidate_id) === String(cid)
          );

          // ✅ 2) 영양 input 값 채우기 (이미 하고 있다면 유지)
          barcodeNutr.kcalEl.value = candidate.kcal ?? "";
          barcodeNutr.carbEl.value = candidate.carb_g ?? "";
          barcodeNutr.protEl.value = candidate.protein_g ?? "";
          barcodeNutr.fatEl.value = candidate.fat_g ?? "";

          // 문구 표시
          const needManual =
            candidate.nutr_source !== "api" &&
            !hasAllNutrition(candidate);

          if (needManual) {
            showError(
              barcodeNutr.errEl,
              "일부 영양 정보가 없습니다. 직접 입력해 주세요."
            );
          } else {
            clearError(barcodeNutr.errEl);
          }

          // ✅ 4) 입력 활성화
          barcodeNutr.kcalEl.disabled = false;
          barcodeNutr.carbEl.disabled = false;
          barcodeNutr.protEl.disabled = false;
          barcodeNutr.fatEl.disabled = false;

        } else {
          selectedId = null;
          btnSave.disabled = true;

          // 체크 해제 시 문구 숨김
          clearError(barcodeNutr.errEl);
        }
      });
    });
  }

  async function loadCandidates() {
    if (!draftId) return;

    const res = await fetch(
      `/record/api/scan/draft/?draft_id=${encodeURIComponent(draftId)}`
    );
    const data = await res.json();

    if (!data.ok) {
      alert(data.error || "후보를 불러오지 못했어요.");
      return;
    }

    renderCandidates(data.candidates || []);
  }

  function initBarcodeCommit() {
    // barcode 전용: draftId 필수
    if (!draftId) {
      alert("후보 데이터를 불러오기 위한 정보(draft_id)가 없어요.");
      return;
    }
    if (!listEl) {
      alert("결과 페이지 UI 요소가 누락되었어요. (candidate-list)");
      return;
    }

    // barcode 영양 수정 input (있으면 사용)
    const kcalEl = document.getElementById("barcode-nutr-kcal");
    const carbEl = document.getElementById("barcode-nutr-carb");
    const protEl = document.getElementById("barcode-nutr-protein");
    const fatEl = document.getElementById("barcode-nutr-fat");
    const errEl = document.getElementById("barcode-nutr-error");

    // ✅ (추가) 전역 참조로 연결 (renderCandidates의 change 이벤트에서 사용)
    barcodeNutr = { kcalEl, carbEl, protEl, fatEl, errEl };

    // ✅ (추가) 최초엔 입력 잠금(후보 선택 전)
    if (kcalEl) kcalEl.disabled = true;
    if (carbEl) carbEl.disabled = true;
    if (protEl) protEl.disabled = true;
    if (fatEl)  fatEl.disabled  = true;
    clearError(errEl);


    btnSave.disabled = true;

    btnSave.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();

      if (!selectedId) return;

      const csrfToken = getCookie("csrftoken");
      if (!csrfToken) {
        alert("CSRF 토큰이 없습니다. 새로고침(F5) 후 다시 시도해주세요.");
        return;
      }

      // ✅ 단건일 때만 body override 허용 (서버도 동일 정책)
      // input이 없으면 payload에 영양값을 안 넣음 -> 서버는 candidate값 사용
      const payload = {
        draft_id: draftId,
        candidate_id: selectedId,
      };

      if (kcalEl && carbEl && protEl && fatEl) {
        // 숫자가 들어온 것만 넣기
        const kcal = numOrEmpty(kcalEl.value);
        const carb = numOrEmpty(carbEl.value);
        const prot = numOrEmpty(protEl.value);
        const fat = numOrEmpty(fatEl.value);

        if (kcal !== null) payload.kcal = kcal;
        if (carb !== null) payload.carb_g = carb;
        if (prot !== null) payload.protein_g = prot;
        if (fat !== null) payload.fat_g = fat;
      }

      clearError(errEl);

      const res = await fetch("/record/api/scan/commit/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify(payload),
      });

      const data = await res.json().catch(() => null);

      if (!res.ok || !data?.ok) {
        const msg = data?.error || "DB_SAVE_FAILED";
        if (errEl) showError(errEl, msg);
        else alert(msg);
        return;
      }

      location.href = data.redirect_url || "/home/";
    });
  }

  // -------------------------
  // 4) OCR flow
  // -------------------------
  async function initOcrCommit() {
    // OCR 입력 요소
    const nameEl = document.getElementById("nutrition-name-input");
    const kcalEl = document.getElementById("nutrition-nutr-kcal");
    const carbEl = document.getElementById("nutrition-nutr-carb");
    const protEl = document.getElementById("nutrition-nutr-protein");
    const fatEl  = document.getElementById("nutrition-nutr-fat");
    const errEl  = document.getElementById("nutrition-nutr-error");

    if (!nameEl || !kcalEl || !carbEl || !protEl || !fatEl) {
      // OCR 패널인데 입력요소가 없으면 조용히 종료(템플릿 분기 가능성 고려)
      return;
    }

    function isValid() {
      const nameOk = !!(nameEl.value || "").trim();
      const kcal = numOrEmpty(kcalEl.value);
      const carb = numOrEmpty(carbEl.value);
      const prot = numOrEmpty(protEl.value);
      const fat  = numOrEmpty(fatEl.value);
      return nameOk && kcal !== null && carb !== null && prot !== null && fat !== null;
    }

    function refreshBtn() {
      btnSave.disabled = !isValid();
    }

    [nameEl, kcalEl, carbEl, protEl, fatEl].forEach((el) => {
      el.addEventListener("input", () => {
        clearError(errEl);
        refreshBtn();
      });
    });

    // 1) 최신 OCR prefill
   
    try {
      const url = `/record/api/ocr/latest/?rgs_dt=${encodeURIComponent(ctxRgsDt)}&seq=${encodeURIComponent(ctxSeq)}`;
      const res = await fetch(url);

      // ✅ 404는 "OCR 실패"가 아니라 "API 없음"으로 구분
      if (res.status === 404) {
        showError(errEl, "서버에 OCR 결과 조회 API(/record/api/ocr/latest/)가 없습니다. (배포/URL 설정 확인 필요)");
        refreshBtn();
        return;
      }

      const latest = await res.json().catch(() => null);
      if (!res.ok || !latest?.ok) {
        throw new Error(latest?.error || `OCR_LOAD_FAILED (${res.status})`);
      }

      const n = latest.nutrition || {};
      if (n.kcal != null) kcalEl.value = String(n.kcal);
      if (n.carb_g != null) carbEl.value = String(n.carb_g);
      if (n.protein_g != null) protEl.value = String(n.protein_g);
      if (n.fat_g != null) fatEl.value = String(n.fat_g);

      const missing = latest.missing_fields || [];
      if (missing.length) {
        showError(errEl, `일부 영양 정보가 없습니다. 직접 입력해 주세요: ${missing.join(", ")}`);
      } else {
        clearError(errEl);
      }
    } catch (e) {
      showError(errEl, String(e.message || e));
    }

    refreshBtn();

    // 2) 저장
    btnSave.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      
      refreshBtn();
      if (btnSave.disabled) return;

      const csrfToken = getCookie("csrftoken");
      if (!csrfToken) {
        alert("CSRF 토큰이 없습니다. 새로고침(F5) 후 다시 시도해주세요.");
        return;
      }

      const jobId = sessionStorage.getItem("ocr_job_id");
      console.log("[result.js] ocr_job_id =", jobId);

      if (!jobId) {
        alert("OCR 작업 정보(job_id)를 찾을 수 없습니다. 다시 스캔해주세요.");
        return;
      }

      const payload = {
        mode: "ocr",
        job_id: jobId,
        name: (nameEl.value || "").trim(),
        kcal: Number(kcalEl.value),
        carb_g: Number(carbEl.value),
        protein_g: Number(protEl.value),
        fat_g: Number(fatEl.value),
      };

      console.log("[OCR commit payload]", payload);
      
      clearError(errEl);

      const endpoint =
        payload.mode === "ocr"
          ? "/record/api/ocr/commit/manual/"
          : "/record/api/scan/commit/";

      const res = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify(payload),
      });

      const data = await res.json().catch(() => null);
      if (!res.ok || !data?.ok) {
        showError(errEl, data?.error || "DB_SAVE_FAILED");
        return;
      }

      location.href = data.redirect_url || "/home/";
    });
  }

  // -------------------------
  // 5) Bootstrap
  // -------------------------
  if (useOcr) {
    // ✅ OCR 화면: nutrition만 보이게
  if (panelBarcode) panelBarcode.style.display = "none";
  if (panelNutrition) panelNutrition.style.display = "block";

    btnSave.disabled = true;
    initOcrCommit();
  } else {
    // ✅ Barcode 화면: barcode만 보이게
  if (panelBarcode) panelBarcode.style.display = "block";
  if (panelNutrition) panelNutrition.style.display = "none";
  
    btnSave.disabled = true;
    loadCandidates();
    initBarcodeCommit();
  }
})();
