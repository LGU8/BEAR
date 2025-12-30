// static/js/settings/settings_s2.js
// S2 개인정보 수정: 변경 감지 + 검증 + 저장 버튼 활성화
// + 프로필 배지(캐릭터) 선택 모달

(function () {
  const form = document.getElementById("s2Form");
  if (!form) return;

  const saveBtn = document.getElementById("saveBtn");
  const errBox = document.getElementById("s2Error");

  const nicknameEl = document.getElementById("nickname");
  const birthUIEl = document.getElementById("birth_date_ui");
  const birthDtEl = document.getElementById("birth_dt");
  const genderEl = document.getElementById("gender");
  const heightEl = document.getElementById("height_cm");
  const weightEl = document.getElementById("weight_kg");

  // ✅ badge
  const badgeOpenBtn = document.getElementById("badgeOpenBtn");
  const badgeModal = document.getElementById("badgeModal");
  const badgeApplyBtn = document.getElementById("badgeApplyBtn");
  const selectedBadgeInput = document.getElementById("selected_badge_id");
  const profileBadgeImg = document.getElementById("profileBadgeImg");

  const badgeTabs = Array.from(document.querySelectorAll(".badge-tab"));
  const badgePanes = Array.from(document.querySelectorAll(".badge-grid[data-pane]"));
  const badgeItems = Array.from(document.querySelectorAll(".badge-item"));
  const badgeIdEl = document.getElementById("selected_badge_id");

  const genderBtns = Array.from(document.querySelectorAll(".seg-toggle-btn"));

  // -------------------------
  // 0) 상태
  // -------------------------
  let hasInteracted = false;

  // 모달에서 선택한(아직 적용 전) 임시값
  let pendingBadgeId = "";
  let pendingBadgeImg = "";

  function setError(msg) {
    if (!errBox) return;
    errBox.textContent = msg || "";
  }

  function markInteracted() {
    hasInteracted = true;
  }

  function yyyymmddFromDateInput(v) {
    if (!v || typeof v !== "string" || v.length !== 10) return "";
    return v.replaceAll("-", "");
  }

  function todayYYYYMMDD() {
    const d = new Date();
    const yyyy = String(d.getFullYear());
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${yyyy}${mm}${dd}`;
  }

  // -------------------------
  // 1) 초기 동기화
  // -------------------------
  if (birthUIEl && birthDtEl) {
    if (!birthDtEl.value && birthUIEl.value) {
      birthDtEl.value = yyyymmddFromDateInput(birthUIEl.value);
    }
  }

  if (genderEl && (!genderEl.value || genderEl.value.trim() === "")) {
    const activeBtn = genderBtns.find((b) => b.classList.contains("is-active"));
    if (activeBtn) {
      genderEl.value = activeBtn.getAttribute("data-value") || "";
    }
  }

  if (selectedBadgeInput && !selectedBadgeInput.value) {
    // 값이 비어있으면 그냥 빈 값 유지(= default badge)
    selectedBadgeInput.value = "";
  }

    const initial = {
      nickname: (nicknameEl?.value || "").trim(),
      birth_dt: (birthDtEl?.value || "").trim(),
      gender: (genderEl?.value || "").trim(),
      height_cm: (heightEl?.value || "").trim(),
      weight_kg: (weightEl?.value || "").trim(),
      selected_badge_id: (badgeIdEl?.value || "").trim(),
    };

    function nowState() {
      return {
        nickname: (nicknameEl?.value || "").trim(),
        birth_dt: (birthDtEl?.value || "").trim(),
        gender: (genderEl?.value || "").trim(),
        height_cm: (heightEl?.value || "").trim(),
        weight_kg: (weightEl?.value || "").trim(),
        selected_badge_id: (badgeIdEl?.value || "").trim(),
  };
}


  function isChanged() {
    const now = nowState();
    return Object.keys(initial).some((k) => (now[k] || "") !== (initial[k] || ""));
  }

  // -------------------------
  // 2) 검증
  // -------------------------
  function validate() {
    const nickname = (nicknameEl?.value || "").trim();
    if (!nickname) return { ok: false, msg: "닉네임을 입력해 주세요." };

    const reNick = /^[A-Za-z0-9_가-힣]+$/;
    if (!reNick.test(nickname)) {
      return { ok: false, msg: "닉네임은 한글/영문/숫자/밑줄(_)만 가능해요." };
    }

    const birth_dt = (birthDtEl?.value || "").trim();
    if (!birth_dt || birth_dt.length !== 8) return { ok: false, msg: "생년월일을 선택해 주세요." };

    const reBirth = /^\d{8}$/;
    if (!reBirth.test(birth_dt)) return { ok: false, msg: "생년월일 형식이 올바르지 않아요." };

    const today = todayYYYYMMDD();
    if (birth_dt > today) return { ok: false, msg: "생년월일은 미래 날짜로 설정할 수 없어요." };

    const gender = (genderEl?.value || "").trim();
    if (!(gender === "M" || gender === "F")) return { ok: false, msg: "성별을 선택해 주세요." };

    const hRaw = (heightEl?.value || "").trim();
    const h = parseInt(hRaw, 10);
    if (Number.isNaN(h)) return { ok: false, msg: "키를 입력해 주세요." };
    if (h < 90 || h > 250) return { ok: false, msg: "키는 90~250cm 범위로 입력해 주세요." };

    const wRaw = (weightEl?.value || "").trim();
    const w = parseInt(wRaw, 10);
    if (Number.isNaN(w)) return { ok: false, msg: "몸무게를 입력해 주세요." };
    if (w < 20 || w > 300) return { ok: false, msg: "몸무게는 20~300kg 범위로 입력해 주세요." };

    // ✅ selected_badge_id는 서버에서 "획득 여부" 검증하므로 여기선 형식만 최소 체크
    const bid = (selectedBadgeInput?.value || "").trim();
    if (bid) {
      const reBid = /^[EF]\d{9}$/;
      if (!reBid.test(bid)) return { ok: false, msg: "배지 값이 올바르지 않아요." };
    }

    return { ok: true, msg: "" };
  }

  // -------------------------
  // 3) 저장 버튼 상태 업데이트
  // -------------------------
  function updateSaveBtn() {
    if (!saveBtn) return;

    const changed = isChanged();
    const v = validate();

    if (!hasInteracted && !changed) {
      setError("");
      saveBtn.disabled = true;
      return;
    }

    if (!v.ok) {
      if (hasInteracted) setError(v.msg);
      saveBtn.disabled = true;
      return;
    }

    setError("");
    saveBtn.disabled = !changed;
  }

  // -------------------------
  // 4) 배지 모달 로직
  // -------------------------
  function openModal() {
    if (!badgeModal) return;

    // 현재 선택값을 pending으로 동기화
    pendingBadgeId = (selectedBadgeInput?.value || "").trim();
    pendingBadgeImg = ""; // 클릭 시 갱신

    // 기존 selected 표시 초기화
    badgeItems.forEach((el) => {
      const id = el.getAttribute("data-id") || "";
      el.classList.toggle("is-selected", pendingBadgeId && id === pendingBadgeId);
    });

    // pending이 이미 존재하면 apply 가능
    if (badgeApplyBtn) badgeApplyBtn.disabled = !pendingBadgeId;

    badgeModal.classList.add("is-open");
    badgeModal.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }

  function closeModal() {
    if (!badgeModal) return;
    badgeModal.classList.remove("is-open");
    badgeModal.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
  }

  function switchTab(tab) {
    badgeTabs.forEach((t) => t.classList.toggle("is-active", (t.getAttribute("data-tab") || "") === tab));
    badgePanes.forEach((p) => p.classList.toggle("is-hidden", (p.getAttribute("data-pane") || "") !== tab));
  }

  // open
  if (badgeOpenBtn) {
    badgeOpenBtn.addEventListener("click", () => {
      markInteracted();
      openModal();
    });
  }

  // close (backdrop/close 버튼)
  if (badgeModal) {
    badgeModal.addEventListener("click", (e) => {
      const target = e.target;
      if (!(target instanceof HTMLElement)) return;
      if (target.getAttribute("data-close") === "1") {
        closeModal();
      }
      if (target.classList.contains("badge-modal__backdrop")) {
        closeModal();
      }
    });
  }

  // esc
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && badgeModal && badgeModal.classList.contains("is-open")) {
      closeModal();
    }
  });

  // tabs
  badgeTabs.forEach((t) => {
    t.addEventListener("click", () => {
      markInteracted();
      const tab = t.getAttribute("data-tab") || "F";
      switchTab(tab);
    });
  });

  // select badge
  badgeItems.forEach((item) => {
    item.addEventListener("click", () => {
      markInteracted();
      const id = item.getAttribute("data-id") || "";
      const img = item.getAttribute("data-img") || "";

      pendingBadgeId = id;
      pendingBadgeImg = img;

      badgeItems.forEach((el) => el.classList.remove("is-selected"));
      item.classList.add("is-selected");

      if (badgeApplyBtn) badgeApplyBtn.disabled = !pendingBadgeId;
    });
  });

  // apply
  if (badgeApplyBtn) {
    badgeApplyBtn.addEventListener("click", () => {
      markInteracted();
      if (!pendingBadgeId) return;

      // hidden 저장
      if (selectedBadgeInput) selectedBadgeInput.value = pendingBadgeId;

      // 상단 프로필 이미지 즉시 반영
      if (profileBadgeImg) {
        if (pendingBadgeImg) {
          profileBadgeImg.src = pendingBadgeImg;
        } else {
          // pendingImg가 없으면 현재 선택 badge_id 기준으로 DOM에서 찾아서 세팅
          const el = badgeItems.find((x) => (x.getAttribute("data-id") || "") === pendingBadgeId);
          if (el) profileBadgeImg.src = el.getAttribute("data-img") || profileBadgeImg.src;
        }
      }

      closeModal();
      updateSaveBtn();
    });
  }

  // -------------------------
  // 5) 기존 입력 이벤트 바인딩
  // -------------------------
  genderBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      markInteracted();

      const value = btn.getAttribute("data-value") || "";
      if (genderEl) genderEl.value = value;

      genderBtns.forEach((b) => {
        const on = (b.getAttribute("data-value") || "") === value;
        b.classList.toggle("is-active", on);
        b.setAttribute("aria-pressed", on ? "true" : "false");
      });

      updateSaveBtn();
    });
  });

  if (birthUIEl && birthDtEl) {
    birthUIEl.addEventListener("change", () => {
      markInteracted();
      birthDtEl.value = yyyymmddFromDateInput(birthUIEl.value);
      updateSaveBtn();
    });
  }

  [nicknameEl, heightEl, weightEl].forEach((el) => {
    if (!el) return;

    el.addEventListener("input", () => {
      markInteracted();
      updateSaveBtn();
    });

    el.addEventListener("change", () => {
      markInteracted();
      updateSaveBtn();
    });
  });

  // -------------------------
  // 6) submit 제어
  // -------------------------
  form.addEventListener("submit", (e) => {
    markInteracted();

    const v = validate();
    if (!v.ok) {
      e.preventDefault();
      setError(v.msg);
      if (saveBtn) saveBtn.disabled = true;
      return;
    }

    if (!isChanged()) {
      e.preventDefault();
      setError("");
      if (saveBtn) saveBtn.disabled = true;
      return;
    }
  });

  // -------------------------
  // 배지 hidden 변경도 저장버튼 갱신 트리거
  // -------------------------
  if (selectedBadgeInput) {
    selectedBadgeInput.addEventListener("input", () => {
      markInteracted();
      updateSaveBtn();
    });

    selectedBadgeInput.addEventListener("change", () => {
      markInteracted();
      updateSaveBtn();
    });
  }


  // 초기 탭(F)
  switchTab("F");
  updateSaveBtn();
})();
