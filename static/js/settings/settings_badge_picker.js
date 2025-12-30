// static/js/settings/settings_badge_picker.js
// S2: 프로필 배지 선택 모달 (open/close/tab/select/apply)

(function () {
  const openBtn = document.getElementById("badgeOpenBtn");
  const modal = document.getElementById("badgePickerModal");

  const backdrop = modal ? modal.querySelector(".badge-picker-modal__backdrop") : null;
  const closeBtns = modal ? Array.from(modal.querySelectorAll("[data-close='1']")) : [];

  const tabs = modal ? Array.from(modal.querySelectorAll(".badge-picker-tab")) : [];
  const panes = modal ? Array.from(modal.querySelectorAll(".badge-picker-grid")) : [];

  const applyBtn = document.getElementById("badgeApplyBtn");
  const hiddenBadgeId = document.getElementById("selected_badge_id");
  const profileBadgeImg = document.getElementById("profileBadgeImg");

  // 선택 상태
  let selected = { id: "", img: "" };

  function openModal() {
    if (!modal) return;
    modal.classList.add("is-open");
    modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("is-modal-open");
  }

  function closeModal() {
    if (!modal) return;
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("is-modal-open");
  }

  function setActiveTab(tabKey) {
    tabs.forEach((t) => t.classList.toggle("is-active", t.dataset.tab === tabKey));
    panes.forEach((p) => {
      const show = p.dataset.pane === tabKey;
      p.classList.toggle("is-hidden", !show);
    });
  }

  function clearSelectedUI() {
    if (!modal) return;
    modal
      .querySelectorAll(".badge-picker-item.is-selected")
      .forEach((el) => el.classList.remove("is-selected"));
  }

  function setSelectedUI(id) {
    if (!modal) return;
    clearSelectedUI();

    // ✅ picker 네이밍으로 수정
    const btn = modal.querySelector(`.badge-picker-item[data-id="${CSS.escape(id)}"]`);
    if (btn) btn.classList.add("is-selected");
  }

  function enableApply(enable) {
    if (!applyBtn) return;
    applyBtn.disabled = !enable;
  }

  // ---- events ----
  if (openBtn) {
    openBtn.addEventListener("click", openModal);
  }

  // close: backdrop / close btn
  if (backdrop) backdrop.addEventListener("click", closeModal);
  closeBtns.forEach((btn) => btn.addEventListener("click", closeModal));

  // ESC close
  document.addEventListener("keydown", (e) => {
    if (!modal || !modal.classList.contains("is-open")) return;
    if (e.key === "Escape") closeModal();
  });

  // tab click
  tabs.forEach((t) => {
    t.addEventListener("click", () => setActiveTab(t.dataset.tab || "F"));
  });

  // badge select (delegate)
  if (modal) {
    modal.addEventListener("click", (e) => {
      const target = e.target;
      if (!(target instanceof Element)) return;

      const item = target.closest(".badge-picker-item");
      if (!item) return;

      // locked/disabled
      if (item.classList.contains("is-locked") || item.hasAttribute("disabled")) return;

      const id = item.getAttribute("data-id") || "";
      const img = item.getAttribute("data-img") || "";
      if (!id || !img) return;

      selected = { id, img };
      setSelectedUI(id);
      enableApply(true);
    });
  }

  // apply selection
  if (applyBtn) {
    applyBtn.addEventListener("click", () => {
      if (!selected.id) return;

      if (hiddenBadgeId) hiddenBadgeId.value = selected.id;
      if (profileBadgeImg) profileBadgeImg.src = selected.img;

      // 저장 버튼 활성화 트리거
      if (hiddenBadgeId) {
        hiddenBadgeId.dispatchEvent(new Event("input", { bubbles: true }));
        hiddenBadgeId.dispatchEvent(new Event("change", { bubbles: true }));
      }

      closeModal();
    });
  }

  // 초기 탭
  setActiveTab("F");

  // 초기 선택값 서버 반영
  const initId = hiddenBadgeId ? (hiddenBadgeId.value || "").trim() : "";
  if (initId && modal) {
    // ✅ initId로 수정
    const initBtn = modal.querySelector(`.badge-picker-item[data-id="${CSS.escape(initId)}"]`);
    if (initBtn && !initBtn.classList.contains("is-locked") && !initBtn.hasAttribute("disabled")) {
      selected = { id: initId, img: initBtn.getAttribute("data-img") || "" };
      setSelectedUI(initId);
      enableApply(true);
    }
  }
})();
