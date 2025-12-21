document.addEventListener("DOMContentLoaded", () => {

  /* =================================================
     1. 상태 변수
     ================================================= */
  let selectedMood = null;      // pos / neu / neg
  let selectedArousal = null;   // low / med / high


  /* =================================================
     2. 더미 키워드 데이터 (감정 × 활성도)
     ================================================= */
  const DUMMY_KEYWORD_MAP = {
    pos_low:  ["편안함", "안정", "여유", "차분함"],
    pos_med:  ["기분좋음", "만족", "집중"],
    pos_high: ["설렘", "기대", "에너지", "활력"],

    neu_low:  ["무난함", "평온", "일상"],
    neu_med:  ["보통", "차분", "집중"],
    neu_high: ["분주함", "바쁨"],

    neg_low:  ["무기력", "지침", "피곤"],
    neg_med:  ["답답함", "걱정"],
    neg_high: ["불안", "초조", "긴장", "스트레스"]
  };


  /* =================================================
     3. DOM 요소
     ================================================= */
  const moodOptions    = document.querySelectorAll(".mood-option");
  const arousalButtons = document.querySelectorAll(".arousal-btn");

  // 활성도 카드 왼쪽 (선택된 감정 표시 영역)
  const selectedMoodWrap  = document.querySelector(".selected-mood");
  const selectedMoodImg   = selectedMoodWrap?.querySelector("img");
  const selectedMoodLabel = selectedMoodWrap?.querySelector(".selected-mood-label");
  const moodPlaceholder   = selectedMoodWrap?.querySelector(".selected-mood-placeholder");

  // 키워드 영역
  const keywordContainer   = document.querySelector(".keyword-container");
  const keywordPlaceholder = keywordContainer?.querySelector(".keyword-placeholder");


  /* =================================================
     4. 초기 상태
     ================================================= */
  // 감정 미선택 상태
  if (selectedMoodImg) {
    selectedMoodImg.style.display = "none";
  }
  if (selectedMoodLabel) {
    selectedMoodLabel.textContent = "";
  }
  if (moodPlaceholder) {
    moodPlaceholder.style.display = "inline";
  }

  // 키워드 placeholder 표시
  showKeywordPlaceholder();


  /* =================================================
     5. 감정 선택 (mood-option)
     ================================================= */
  moodOptions.forEach(option => {
    option.addEventListener("click", () => {

      // 버튼 active 처리
      moodOptions.forEach(o => o.classList.remove("active"));
      option.classList.add("active");

      selectedMood = option.dataset.mood;

      const img  = option.querySelector("img");
      const text = option.querySelector(".mood-label");

      if (img && text && selectedMoodImg && selectedMoodLabel) {
        // 활성도 카드 왼쪽에 감정 반영
        selectedMoodImg.src = img.src;
        selectedMoodImg.alt = img.alt;
        selectedMoodImg.style.display = "block";

        selectedMoodLabel.textContent = text.textContent;
      }

      if (moodPlaceholder) {
        moodPlaceholder.style.display = "none";
      }

      updateKeywords();
    });
  });


  /* =================================================
     6. 활성도 선택 (arousal-btn)
     ================================================= */
  arousalButtons.forEach(btn => {
    btn.addEventListener("click", () => {

      arousalButtons.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");

      selectedArousal = btn.dataset.arousal;

      updateKeywords();
    });
  });


  /* =================================================
     7. 키워드 갱신 로직
     ================================================= */
  function updateKeywords() {
    // 감정 or 활성도 미선택
    if (!selectedMood || !selectedArousal) {
      clearKeywords();
      showKeywordPlaceholder();
      return;
    }

    const key = `${selectedMood}_${selectedArousal}`;
    const keywords = DUMMY_KEYWORD_MAP[key] || [];

    renderKeywordPills(keywords);
  }


  /* =================================================
     8. 키워드 렌더링
     ================================================= */
  function renderKeywordPills(keywordList) {
    if (!keywordContainer) return;

    clearKeywords();

    if (!keywordList || keywordList.length === 0) {
      showKeywordPlaceholder();
      return;
    }

    hideKeywordPlaceholder();

    keywordList.forEach(word => {
      const btn = document.createElement("button");
      btn.className = "keyword-pill";
      btn.textContent = word;

      // 복수 선택 토글
      btn.addEventListener("click", () => {
        btn.classList.toggle("active");
      });

      keywordContainer.appendChild(btn);
    });
  }


  /* =================================================
     9. 키워드 placeholder 제어
     ================================================= */
  function showKeywordPlaceholder() {
    if (keywordPlaceholder) {
      keywordPlaceholder.style.display = "inline";
    }
  }

  function hideKeywordPlaceholder() {
    if (keywordPlaceholder) {
      keywordPlaceholder.style.display = "none";
    }
  }

  function clearKeywords() {
    if (!keywordContainer) return;

    keywordContainer
      .querySelectorAll(".keyword-pill")
      .forEach(el => el.remove());
  }


  /* =================================================
     10. (선택) 외부에서 키워드 가져오기
     ================================================= */
  window.getSelectedKeywords = function () {
    return Array.from(
      document.querySelectorAll(".keyword-pill.active")
    ).map(btn => btn.textContent);
  };

});
