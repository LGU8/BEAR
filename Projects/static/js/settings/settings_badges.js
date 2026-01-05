// static/js/settings/settings_badges.js
(() => {
  // -----------------------
  // Responsive PAGE_SIZE
  // - Mobile: 2x2 = 4
  // - Desktop: 6
  // -----------------------
  const MOBILE_BREAKPOINT = 560;

  function getPageSize() {
    return window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT}px)`).matches ? 4 : 6;
  }

  // CTA 이동 URL(프로젝트 라우팅에 맞게 필요 시 수정)
  const S2_URL = "/settings/profile/edit/";
  const MISSION_URL = "/record/";

  function chunk(items, size) {
    const out = [];
    for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
    return out;
  }

  function buildPages(trackEl, pageSize) {
    const items = Array.from(trackEl.querySelectorAll(".badge-item"));
    const pages = chunk(items, pageSize);

    trackEl.innerHTML = "";
    pages.forEach((pageItems) => {
      const page = document.createElement("div");
      page.className = "badge-page";
      pageItems.forEach((it) => page.appendChild(it));
      trackEl.appendChild(page);
    });

    return pages.length;
  }

  function initSlider(sliderRoot, trackKey) {
    const trackEl = sliderRoot.querySelector(`[data-track="${trackKey}"]`);
    const prevBtn = sliderRoot.querySelector(".badge-nav--prev");
    const nextBtn = sliderRoot.querySelector(".badge-nav--next");
    if (!trackEl || !prevBtn || !nextBtn) return;

    // (A) slider state
    let pageSize = getPageSize();
    let pageCount = buildPages(trackEl, pageSize);
    let page = 0;

    // (B) If only 1 page
    function applySinglePageUI() {
      prevBtn.style.display = "none";
      nextBtn.style.display = "none";
      trackEl.style.transform = "translateX(0%)";
    }

    function applyMultiPageUI() {
      prevBtn.style.display = "";
      nextBtn.style.display = "";
    }

    function sync() {
      trackEl.style.transform = `translateX(${-page * 100}%)`;
      prevBtn.disabled = page <= 0;
      nextBtn.disabled = page >= pageCount - 1;
    }

    function rebuild(keepLogicalIndex = true) {
      // 현재 "전체 아이템 기준 인덱스"를 유지하려면
      // page*oldPageSize -> globalIndex를 잡고 새 pageSize로 다시 계산
      const oldPageSize = pageSize;
      const oldPage = page;

      let globalIndex = 0;
      if (keepLogicalIndex) {
        globalIndex = oldPage * oldPageSize;
      }

      pageSize = getPageSize();
      pageCount = buildPages(trackEl, pageSize);

      // 새 page 계산
      page = Math.floor(globalIndex / pageSize);
      page = Math.max(0, Math.min(pageCount - 1, page));

      if (pageCount <= 1) {
        applySinglePageUI();
        return;
      }
      applyMultiPageUI();
      sync();
    }

    // 초기 UI 세팅
    if (pageCount <= 1) {
      applySinglePageUI();
      return;
    }
    applyMultiPageUI();

    prevBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      page = Math.max(0, page - 1);
      sync();
    });

    nextBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      page = Math.min(pageCount - 1, page + 1);
      sync();
    });

    // resize/orientation 대응 (모바일 회전, 주소창 변화 등)
    let resizeTimer = null;
    function onResize() {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => rebuild(true), 120);
    }

    window.addEventListener("resize", onResize, { passive: true });
    window.addEventListener("orientationchange", onResize, { passive: true });

    sync();

    // 외부에서 필요 시 강제 rebuild 가능하도록 저장
    sliderRoot.__badgeRebuild = rebuild;
  }

  // -----------------------
  // Modal refs (도감 전용)
  // -----------------------
  const modal = document.getElementById("badgeModal");
  const modalImg = document.getElementById("badgeModalImg");
  const modalTitle = document.getElementById("badgeModalTitle");
  const modalDesc = document.getElementById("badgeModalDesc");
  const modalHint = document.getElementById("badgeModalHint");
  const modalLockPill = document.getElementById("badgeModalLockPill");
  const modalAcquired = document.getElementById("badgeModalAcquired");
  const modalCloseBtn = modal ? modal.querySelector(".badge-modal__close") : null;
  const modalCta = document.getElementById("badgeModalCta");
  const modalImgWrap = modal ? modal.querySelector(".badge-modal__imgwrap") : null;

  let lastFocused = null;

  function setModalState(locked) {
    if (!modal) return;
    modal.classList.toggle("is-locked", !!locked);
    modal.classList.toggle("is-unlocked", !locked);
  }

  function buildCtaUrl(payload) {
    if (payload.locked) return MISSION_URL;
    return `${S2_URL}?pick_badge=${encodeURIComponent(payload.badgeId || "")}`;
  }

  function openModal(payload) {
    if (!modal) return;

    lastFocused = document.activeElement;

    const locked = !!payload.locked;
    setModalState(locked);

    // img
    if (modalImg) {
      modalImg.src = payload.imgUrl || "";
      modalImg.alt = payload.badgeId || "";
    }

    // title
    if (modalTitle) modalTitle.textContent = payload.title || "";

    // desc/hint
    if (locked) {
      if (modalDesc) modalDesc.textContent = payload.desc || "";
      if (modalHint) modalHint.textContent = payload.hint
        ? `획득 방법: ${payload.hint}`
        : "획득 방법: 조건을 확인할 수 없어요.";
    } else {
      if (modalDesc) modalDesc.textContent = payload.desc || "";
      if (modalHint) modalHint.textContent = payload.hint || "";
    }

    // pill
    if (modalLockPill) {
      modalLockPill.style.display = locked ? "inline-flex" : "none";
    }

    // acquired time
    if (modalAcquired) {
      if (!locked && payload.acquiredTime) {
        const pretty = formatAcquiredTime(payload.acquiredTime);

        modalAcquired.innerHTML = `
          <span class="acq-pill">
            <span class="acq-label">획득일</span>
            <span class="acq-value">${pretty}</span>
          </span>
        `;
        modalAcquired.style.display = "block";
      } else {
        modalAcquired.innerHTML = "";
        modalAcquired.style.display = "none";
      }
    }

    // CTA
    if (modalCta) {
      modalCta.href = buildCtaUrl(payload);
      modalCta.textContent = locked ? "획득하러 가기" : "프로필로 설정";
    }

    modal.classList.add("is-open");
    modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("is-modal-open");

    if (modalCloseBtn) modalCloseBtn.focus();
  }

  function closeModal() {
    if (!modal) return;

    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("is-modal-open");

    modal.classList.remove("is-locked");
    modal.classList.remove("is-unlocked");

    if (lastFocused && typeof lastFocused.focus === "function") {
      lastFocused.focus();
    }
    lastFocused = null;
  }

  function formatAcquiredTime(raw) {
    const s = (raw || "").trim();
    if (!s) return "";

    // 케이스 A) YYYYMMDDHHMMSS (14자리)
    if (/^\d{14}$/.test(s)) {
      const yyyy = s.slice(0, 4);
      const mm = s.slice(4, 6);
      const dd = s.slice(6, 8);
      const HH = s.slice(8, 10);
      const MI = s.slice(10, 12);
      return `${yyyy}.${mm}.${dd} ${HH}:${MI}`;
    }

    // 케이스 B) YYYYMMDD (8자리)
    if (/^\d{8}$/.test(s)) {
      const yyyy = s.slice(0, 4);
      const mm = s.slice(4, 6);
      const dd = s.slice(6, 8);
      return `${yyyy}.${mm}.${dd}`;
    }

    // 케이스 C) ISO 혹은 기타 -> Date 파싱 시도
    const d = new Date(s);
    if (!Number.isNaN(d.getTime())) {
      const yyyy = d.getFullYear();
      const mm = String(d.getMonth() + 1).padStart(2, "0");
      const dd = String(d.getDate()).padStart(2, "0");
      const HH = String(d.getHours()).padStart(2, "0");
      const MI = String(d.getMinutes()).padStart(2, "0");
      return `${yyyy}.${mm}.${dd} ${HH}:${MI}`;
    }

    // fallback
    return s;
  }

  // -----------------------
  // click delegation
  // -----------------------
  document.addEventListener("click", (e) => {
    const target = e.target;
    if (!(target instanceof Element)) return;

    // close modal
    if (target.hasAttribute("data-modal-close")) {
      closeModal();
      return;
    }

    // open modal by badge-item
    const item = target.closest(".badge-item");
    if (item) {
      // badges-page 내부(도감)에서만 동작
      if (!item.closest(".badges-page")) return;

      openModal({
        badgeId: item.dataset.badgeId || "",
        title: item.dataset.title || "",
        desc: item.dataset.desc || "",
        hint: item.dataset.hint || "",
        imgUrl: item.dataset.imgUrl || "",
        locked: item.dataset.locked === "1",
        acquiredTime: item.dataset.acquiredTime || "",
      });
      return;
    }
  });

  // -----------------------
  // keyboard
  // -----------------------
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal && modal.classList.contains("is-open")) {
      closeModal();
      return;
    }

    const el = e.target;
    if (!(el instanceof Element)) return;
    const item = el.closest(".badge-item");
    if (!item) return;

    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      item.click();
    }
  });

  // -----------------------
  // Modal micro-interaction (click bounce)
  // -----------------------
  if (modalImgWrap) {
    modalImgWrap.addEventListener("click", () => {
      modalImgWrap.classList.remove("is-bounce");
      void modalImgWrap.offsetWidth;
      modalImgWrap.classList.add("is-bounce");
    });
  }

  // -----------------------
  // Init sliders
  // -----------------------
  const foodSlider = document.querySelector('.badge-slider[data-slider="food"]');
  const emotionSlider = document.querySelector('.badge-slider[data-slider="emotion"]');

  if (foodSlider) initSlider(foodSlider, "food");
  if (emotionSlider) initSlider(emotionSlider, "emotion");
})();