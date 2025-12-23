document.addEventListener("DOMContentLoaded", () => {

  /* =================================================
     1. 상태 변수
     ================================================= */
  let selectedMood = null;      // pos / neu / neg
  let selectedArousal = null;   // low / med / high

  /* =================================================
     2. DB에서 키워드 가져오기
     ================================================= */
  function fetchKeywordsFromServer(mood, energy) {
    fetch(`api/keywords/?mood=${mood}&energy=${energy}`)
    .then(response => {
      if (!response.ok) {
        throw new Error("키워드 조회 실패");
      }
      return response.json();
    })
    .then(keywordList => {
      // 서버에서 받은 키워드로 렌더링
      renderKeywordPills(keywordList);
    })
    .catch(error => {
      console.error(error);
      clearKeywords();
      showKeywordPlaceholder();
    });
  }


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
      document.getElementById("mood-input").value = selectedMood;

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
      document.getElementById("energy-input").value = selectedArousal;

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

    fetchKeywordsFromServer(selectedMood, selectedArousal);
  }

  /* =================================================
     7-2. 키워드 저장 로직
     ================================================= */

  function updateKeywordInput() {
    const selectedKeywords = Array.from(
    document.querySelectorAll(".keyword-pill.active")
    ).map(btn => btn.textContent);

    document.getElementById("keyword-input").value =
    selectedKeywords.join(",");
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
      btn.type = "button"
      btn.className = "keyword-pill";
      btn.textContent = word;

      // 복수 선택 토글
      btn.addEventListener("click", () => {
        btn.classList.toggle("active");
        updateKeywordInput();
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



});
