// static/js/result.js

(function () {
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

  btnSave.disabled = true;

  // ✅ single-select checkbox를 위한 상태
  let selectedId = null;

  function fmtNum(v) {
    // null/undefined/"" -> "-"
    if (v === null || v === undefined || v === "") return "-";
    const n = Number(v);
    if (Number.isNaN(n)) return String(v);
    // 소수는 원하면 고정도 가능. 우선 자연스럽게.
    return String(n);
  }

  function renderCandidates(candidates) {
    listEl.innerHTML = candidates
      .map((c) => {
        const cid = c.candidate_id;
        const name = c.name || "";
        const brand = c.brand || "";
        const flavor = c.flavor || "";

        const kcal = fmtNum(c.kcal);
        const carb = fmtNum(c.carb_g);
        const prot = fmtNum(c.protein_g);
        const fat = fmtNum(c.fat_g);

        // ✅ checkbox + label 클릭 지원(접근성)
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

    // ✅ 이벤트 바인딩: single-select checkbox 로직
    const checks = listEl.querySelectorAll("input.cand-check");

    checks.forEach((chk) => {
      chk.addEventListener("change", () => {
        const cid = chk.value;

        if (chk.checked) {
          // ✅ 현재 체크된 것을 선택으로 확정하고,
          // ✅ 다른 체크박스는 전부 해제 (single-select)
          checks.forEach((other) => {
            if (other !== chk) other.checked = false;
          });
          selectedId = cid;
          btnSave.disabled = false;
        } else {
          // ✅ 체크 해제 -> 선택 없음
          selectedId = null;
          btnSave.disabled = true;
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

    // ✅ 후보 렌더
    renderCandidates(data.candidates || []);
  }

  btnSave.addEventListener("click", async () => {
    if (!selectedId) return;

    const fd = new FormData();
    fd.append("draft_id", draftId);

    // ✅ 저장은 1개만: 기존 단건 API 유지
    fd.append("candidate_id", selectedId);

    const res = await fetch("/record/api/scan/commit/", {
      method: "POST",
      body: fd,
    });
    const data = await res.json();

    if (!data.ok) {
      alert(data.error || "저장 실패");
      return;
    }

    // ✅ 서버는 현재 picked가 "리스트"로 내려올 수도 있고(다건 호환 코드),
    // ✅ 단건이라면 picked[0]을 사용
    const picked0 = Array.isArray(data.picked) ? data.picked[0] : data.picked;

    // ✅ record 페이지 카드가 읽을 키에 "최종 기록" 저장
    const recordKey = `mealRecords:${data.date}:${data.meal}`;
    const record = {
      date: data.date,
      meal: data.meal,
      items: [
        {
          type: "barcode",
          name: picked0?.name || "",
          brand: picked0?.brand || "",
          flavor: picked0?.flavor || "",
          barcode: data.barcode || "",
          kcal: picked0?.kcal ?? null,
          carb_g: picked0?.carb_g ?? null,
          protein_g: picked0?.protein_g ?? null,
          fat_g: picked0?.fat_g ?? null,
        },
      ],
      savedAt: Date.now(),
    };
    localStorage.setItem(recordKey, JSON.stringify(record));

    // ✅ 저장 완료 후 record 페이지로 복귀
    location.href = `/record/?date=${encodeURIComponent(
      data.date
    )}&meal=${encodeURIComponent(data.meal)}`;
  });

  loadCandidates();
})();
