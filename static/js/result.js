(function () {
  const params = new URLSearchParams(location.search);
  const draftId = params.get("draft_id");
  const date = params.get("date");
  const meal = params.get("meal");

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
  let selectedId = null;

  async function loadCandidates() {
    const res = await fetch(
      `/record/api/scan/draft/?draft_id=${encodeURIComponent(draftId)}`
    );
    const data = await res.json();

    if (!data.ok) {
      alert(data.error || "후보를 불러오지 못했어요.");
      return;
    }

    // 요구사항: 제품명/브랜드/맛만 표시
    listEl.innerHTML = data.candidates
      .map(
        (c) => `
      <label class="cand-row">
        <input type="radio" name="cand" value="${c.candidate_id}">
        <div>
          <div><strong>${c.name || ""}</strong></div>
          <div class="cand-meta">${c.brand || ""} · ${c.flavor || ""}</div>
        </div>
      </label>
    `
      )
      .join("");

    const radios = listEl.querySelectorAll("input[name='cand']");
    radios.forEach((radio) => {
      radio.addEventListener("change", () => {
        selectedId = radio.value;
        btnSave.disabled = false; // ✅ 선택 전 저장 불가
      });
    });
  }

  btnSave.addEventListener("click", async () => {
    if (!selectedId) return;

    const fd = new FormData();
    fd.append("draft_id", draftId);
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

    // ✅ 1) record 페이지 카드가 읽을 키에 "최종 기록" 저장
  //    (네 프로젝트에서 가장 안정적인 키: mealRecords:date:meal)
  const recordKey = `mealRecords:${data.date}:${data.meal}`;

  const record = {
    date: data.date,
    meal: data.meal,
    items: [
      {
        type: "barcode",
        name: data.picked?.name || "",
        brand: data.picked?.brand || "",
        flavor: data.picked?.flavor || "",
        barcode: data.barcode || "",
      },
    ],
    savedAt: Date.now(),
  };

  localStorage.setItem(recordKey, JSON.stringify(record));

    // ✅ 저장 완료 후 record 페이지로 복귀
  location.href = `/record/?date=${encodeURIComponent(data.date)}&meal=${encodeURIComponent(data.meal)}`;
  });

  loadCandidates();
})();
