// static/js/settings/settings_badges.js
(() => {
  const PAGE_SIZE = 6;

  function chunkToPages(items, size) {
    const pages = [];
    for (let i = 0; i < items.length; i += size) pages.push(items.slice(i, i + size));
    return pages;
  }

  function buildPages(trackEl) {
    // trackEl 내부의 badge-item들을 6개씩 page로 감싼다.
    const items = Array.from(trackEl.querySelectorAll(".badge-item"));
    const pages = chunkToPages(items, PAGE_SIZE);

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

    const pageCount = buildPages(trackEl);
    let page = 0;

    function sync() {
      trackEl.style.transform = `translateX(${-page * 100}%)`;
      prevBtn.disabled = page <= 0;
      nextBtn.disabled = page >= pageCount - 1;
    }

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

    sync();
  }

  // Modal refs
  const modal = document.getElementById("badgeModal");
  const modalImg = document.getElementById("badgeModalImg");
  const modalTitle = document.getElementById("badgeModalTitle");
  const modalDesc = document.getElementById("badgeModalDesc");
  const modalHint = document.getElementById("badgeModalHint");
  const modalLockPill = document.getElementById("badgeModalLockPill");
  const modalAcquired = document.getElementById("badgeModalAcquired");

  function openModal(payload) {
    modalImg.src = payload.imgUrl;
    modalImg.alt = payload.badgeId;

    modalTitle.textContent = payload.title;
    modalDesc.textContent = payload.desc;
    modalHint.textContent = payload.hint;

    // 잠김 pill
    modalLockPill.style.display = payload.locked ? "inline-flex" : "none";

    // 획득일: 획득 + 값 있을 때만
    if (!payload.locked && payload.acquiredTime) {
      modalAcquired.textContent = `획득일: ${payload.acquiredTime}`;
      modalAcquired.style.display = "block";
    } else {
      modalAcquired.textContent = "";
      modalAcquired.style.display = "none";
    }

    modal.classList.add("is-open");
    modal.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }

  function closeModal() {
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
  }

  // badge item click -> open modal
  document.addEventListener("click", (e) => {
    const item = e.target.closest(".badge-item");
    if (item) {
      openModal({
        badgeId: item.dataset.badgeId,
        title: item.dataset.title || "",
        desc: item.dataset.desc || "",
        hint: item.dataset.hint || "",
        imgUrl: item.dataset.imgUrl || "",
        locked: item.dataset.locked === "1",
        acquiredTime: item.dataset.acquiredTime || "",
      });
      return;
    }

    // modal close
    if (e.target && e.target.hasAttribute("data-modal-close")) closeModal();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal.classList.contains("is-open")) closeModal();
  });

  // Init sliders
  const foodSlider = document.querySelector('.badge-slider[data-slider="food"]');
  const emotionSlider = document.querySelector('.badge-slider[data-slider="emotion"]');
  if (foodSlider) initSlider(foodSlider, "food");
  if (emotionSlider) initSlider(emotionSlider, "emotion");
})();
