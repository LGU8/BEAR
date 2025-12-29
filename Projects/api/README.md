메뉴 추천 API 사용 가이드

1️⃣ API로 무엇을 할 수 있나요?
	•	사용자의 감정(mood), 활력도(energy), 날짜, 끼니(아침/점심/저녁) 정보를 주면
	•	시스템이 자동으로:
	1.	사용자 상태에 맞는 메뉴 3개(P/H/E)를 추천하고
	2.	DB에 저장한 뒤
	3.	바로 화면에 쓸 수 있는 JSON으로 반환합니다.

👉 UI에서는 API만 호출해서 결과 끝

⸻

2️⃣ 추천 결과 기준

추천은 항상 3가지 타입으로 나옵니다.

코드	의미	설명
P	Preference	사용자가 좋아할 확률이 높은 메뉴
H	Health	영양 균형이 좋은 메뉴
E	Exploration	새로운 메뉴

화면에는
“오늘의 추천”, “건강 추천”, “새로운 메뉴”
처럼 자유롭게 이름 붙여서 사용

⸻

3️⃣ API

POST /api/menu/recommend

	•	홈 화면 진입 시
	•	감정 선택 후 “추천 보기” 버튼 클릭 시
	•	오늘의 점심/저녁 추천이 필요할 때

⸻

Request (보내는 값)

{
  "cust_id": "0000000001",
  "mood": "pos",
  "energy": "med",
  "rgs_dt": "20251228",
  "rec_time_slot": "L"
}

필드 설명

필드	값	설명
cust_id	string	사용자 ID
mood	pos / neu / neg	감정 (긍정/중립/부정)
energy	low / med / hig	에너지 수준
rgs_dt	YYYYMMDD	날짜
rec_time_slot	M / L / D	아침/점심/저녁


⸻

Response (받는 값)

{
  "ok": true,
  "cust_id": "0000000001",
  "rgs_dt": "20251228",
  "rec_time_slot": "L",
  "items": [
    {
      "rec_type": "E",
      "food_id": "213280",
      "food_name": "봉우재꽃게된장찌개",
      "updated_time": "20251227173638"
    },
    {
      "rec_type": "H",
      "food_id": "80911",
      "food_name": "유자찰빵",
      "updated_time": "20251227173638"
    },
    {
      "rec_type": "P",
      "food_id": "182640",
      "food_name": "숯불향 오븐치킨 매콤양념",
      "updated_time": "20251227173638"
    }
  ]
}


⸻

4️⃣ UI(권장 패턴)

Step 1. 추천 생성

POST /api/menu/recommend

	•	버튼 클릭 시 1번만 호출
	•	내부에서 DB 저장까지 자동 처리됨

⸻

Step 2. 화면 렌더링

items.map(item => {
  // item.rec_type
  // item.food_name
})

예시 UI 매핑:
	•	P → “오늘의 취향 추천”
	•	H → “건강 추천”
	•	E → “새로운 메뉴 도전”

⸻

5️⃣ 이미 저장된 추천을 다시 가져오고 싶다면 GET /api/menu/recommend

GET /api/menu/recommend?cust_id=0000000001&rgs_dt=20251228&rec_time_slot=L

	•	새로 추천을 만들 필요 없이
	•	DB에 저장된 추천 결과만 조회할 때 사용

⸻

7️⃣ QA

Q. 추천이 매번 바뀌나요?
	•	같은 조건으로 다시 호출하면 업데이트됩니다.
	•	(정책 변경 가능하지만, 기본은 최신 추천 유지)

Q. food_name은 바로 써도 되나요?
	•	네. 이미 DB 조인된 표시용 이름입니다.

Q. 추천이 없을 수도 있나요?
	•	정상 상황에서는 항상 3개(P/H/E)가 내려옵니다.

⸻