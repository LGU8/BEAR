// static/js/result.js
(function () {
  // ✅ CSRF cookie 읽기 (result.js에서 필요)
  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(";").shift();
    return "";
  }

  const params = new URLSearchParams(location.search);
  const draftId = params.get("draft_id");

  if (!draftId) {
    console.error("[result] draft_id missing");
    alert("후보 데이터를 불러오기 위한 정보(draft_id)가 없어요.");
    return;
  }

  const listEl = document.getElementById("candidate-list");
  const btnSave = document.getElementById("btn-save");

  if (!listEl || !btnSave) {
    console.error("[result] required elements missing:", {
      candidateList: !!listEl,
      btnSave: !!btnSave,
    });
    alert("결과 페이지 UI 요소가 누락되었어요. (candidate-list / btn-save)");
    return;
  }

  // ✅ 영양 입력 input (result.html에 있어야 함)
  const panelBarcode = document.getElementById("result-barcode");
  const panelNutrition = document.getElementById("result-nutrition");

  const nutrKcal = document.getElementById("barcode-nutr-kcal");
  const nutrCarb = document.getElementById("barcode-nutr-carb");
  const nutrProtein = document.getElementById("barcode-nutr-protein");
  const nutrFat = document.getElementById("barcode-nutr-fat");
  const nutrErr = document.getElementById("barcode-nutr-error");

  if (panelBarcode) panelBarcode.style.display = "block";
  if (panelNutrition) panelNutrition.style.display = "none";

  btnSave.disabled = true;

  // ✅ single-select checkbox를 위한 상태
  let selectedId = null;
  let selectedCandidate = null;

  function showNutrError(msg) {
    if (!nutrErr) return;
    nutrErr.textContent = msg;
    nutrErr.style.display = "block";
  }
  function clearNutrError() {
    if (!nutrErr) return;
    nutrErr.textContent = "";
    nutrErr.style.display = "none";
  }

  function fmtNum(v) {
    // null/undefined/"" -> "-"
    if (v === null || v === undefined || v === "") return "-";
    const n = Number(v);
    if (Number.isNaN(n)) return String(v);
    return String(n);
  }

  function toNumberOrEmpty(v) {
    if (v === null || v === undefined) return "";
    const s = String(v).trim();
    if (!s || s === "-" || s.toLowerCase() === "na" || s.toLowerCase() === "n/a")
      return "";
    const n = Number(s);
    return Number.isFinite(n) ? String(n) : "";
  }

  function isValidNumInput(el) {
    const v = (el?.value || "").trim();
    if (!v) return false;
    const n = Number(v);
    return Number.isFinite(n) && n >= 0;
  }

  function readNum(el) {
    const v = (el?.value || "").trim();
    if (!v) return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : NaN;
  }

  function updateSaveEnabled() {
    const selectedOk = !!selectedId;
    const nutrOk =
      isValidNumInput(nutrKcal) &&
      isValidNumInput(nutrCarb) &&
      isValidNumInput(nutrProtein) &&
      isValidNumInput(nutrFat);

    btnSave.disabled = !(selectedOk && nutrOk);
  }

  [nutrKcal, nutrCarb, nutrProtein, nutrFat].forEach((el) => {
    el?.addEventListener("input", () => {
      clearNutrError();
      updateSaveEnabled();
    });
  });

  function renderCandidates(candidates) {
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
          checks.forEach((other) => {
            if (other !== chk) other.checked = false;
          });

          selectedId = cid;

          // ✅ 선택된 후보 객체 찾기
          selectedCandidate =
            (candidates || []).find((x) => String(x.candidate_id) === String(cid)) ||
            null;

          // ✅ 선택 후보 영양값 input에 prefill (누락은 빈칸)
          if (selectedCandidate) {
            if (nutrKcal) nutrKcal.value = toNumberOrEmpty(selectedCandidate.kcal);
            if (nutrCarb) nutrCarb.value = toNumberOrEmpty(selectedCandidate.carb_g);
            if (nutrProtein)
              nutrProtein.value = toNumberOrEmpty(selectedCandidate.protein_g);
            if (nutrFat) nutrFat.value = toNumberOrEmpty(selectedCandidate.fat_g);

            const missing = [];
            if (!nutrKcal?.value) missing.push("kcal");
            if (!nutrCarb?.value) missing.push("탄수화물(g)");
            if (!nutrProtein?.value) missing.push("단백질(g)");
            if (!nutrFat?.value) missing.push("지방(g)");

            if (missing.length) {
              showNutrError(
                `일부 영양 정보가 없습니다. 직접 입력해 주세요: ${missing.join(", ")}`
              );
            } else {
              clearNutrError();
            }
          }

          updateSaveEnabled();
        } else {
          selectedId = null;
          selectedCandidate = null;

          if (nutrKcal) nutrKcal.value = "";
          if (nutrCarb) nutrCarb.value = "";
          if (nutrProtein) nutrProtein.value = "";
          if (nutrFat) nutrFat.value = "";
          clearNutrError();

          updateSaveEnabled();
        }
      });
    });
  }

  async function loadCandidates() {
    const res = await fetch(
      `/record/api/scan/draft/?draft_id=${encodeURIComponent(draftId)}`
    );
    const data = await res.json();

    if (!data.ok) {
      alert(data.error || "후보를 불러오지 못했어요.");
      return;
    }

    renderCandidates(data.candidates || []);
    updateSaveEnabled();
  }

  btnSave.addEventListener("click", async () => {
    if (!selectedId) return;

    const csrfToken = getCookie("csrftoken");
    if (!csrfToken) {
      alert("CSRF 토큰이 없습니다. 새로고침(F5) 후 다시 시도해주세요.");
      return;
    }

    // ✅ 최종 입력값 읽기
    const kcal = readNum(nutrKcal);
    const carb_g = readNum(nutrCarb);
    const protein_g = readNum(nutrProtein);
    const fat_g = readNum(nutrFat);

    // ✅ 프론트 1차 검증(백엔드에서도 반드시 검증 권장)
    const missing = [];
    if (kcal === null) missing.push("kcal");
    if (carb_g === null) missing.push("탄수화물(g)");
    if (protein_g === null) missing.push("단백질(g)");
    if (fat_g === null) missing.push("지방(g)");

    const invalid = [];
    if (Number.isNaN(kcal)) invalid.push("kcal");
    if (Number.isNaN(carb_g)) invalid.push("탄수화물(g)");
    if (Number.isNaN(protein_g)) invalid.push("단백질(g)");
    if (Number.isNaN(fat_g)) invalid.push("지방(g)");

    if (missing.length) {
      showNutrError(`필수 입력값이 비었습니다: ${missing.join(", ")}`);
      updateSaveEnabled();
      return;
    }
    if (invalid.length) {
      showNutrError(`숫자 형식이 올바르지 않습니다: ${invalid.join(", ")}`);
      updateSaveEnabled();
      return;
    }

    const res = await fetch("/record/api/scan/commit/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      body: JSON.stringify({
        draft_id: draftId,
        candidate_id: selectedId,
        kcal,
        carb_g,
        protein_g,
        fat_g,
      }),
    });

    const data = await res.json().catch(() => null);

    if (!res.ok || !data?.ok) {
      alert(data?.error || "DB_SAVE_FAILED");
      return;
    }

    location.href = data.redirect_url || "/record/meal/";
  });

  loadCandidates();
})();
