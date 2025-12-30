// static/js/settings/settings_s0.js
(function () {
  const openBtn = document.getElementById("openProfileHint");
  const modal = document.getElementById("profileHintModal");
  const closeBtn = document.getElementById("closeProfileHint");
  const dismissBtn = document.getElementById("dismissProfileHint");

  if (!openBtn || !modal) return;

  function openModal() {
    modal.classList.add("is-open");
    modal.setAttribute("aria-hidden", "false");
    // 접근성: 첫 포커스
    (closeBtn || dismissBtn || modal).focus?.();
  }

  function closeModal() {
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
    openBtn.focus?.();
  }

  openBtn.addEventListener("click", openModal);

  closeBtn?.addEventListener("click", closeModal);
  dismissBtn?.addEventListener("click", closeModal);

  // backdrop 클릭 닫기
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });

  // ESC 닫기
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal.classList.contains("is-open")) {
      closeModal();
    }
  });
})();