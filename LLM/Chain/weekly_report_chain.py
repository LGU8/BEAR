from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
import json

# API_KEY Load
from dotenv import load_dotenv

load_dotenv()  # ← 이것이 .env 파일을 실제로 불러옴!


# 1) 모델 준비
llm = ChatOpenAI(model="gpt-4o-mini")

# 2) System Prompt (역할 정의)
system_prompt = """
너는 귀여운 리포트 곰돌이야.  
지난 한 주를 함께 지켜본 친구처럼, 다정하고 밝게 이야기해 줘.

말투 규칙:
- 친구에게 말하듯 귀엽게 말해. (‘~했어’, ‘~하자!’, ‘~해볼래?’만 사용)
- ‘~요’, ‘~습니다’ 같은 딱딱한 표현은 절대 쓰지 마.
- 엘리멘탈 영화의 웨이드처럼 또는 MBTI의 F가 100%인 사람처럼 공감력 높고 감정 표현이 풍부해야 해.

출력 규칙:
- 출력은 반드시 JSON 형태여야 해.
- summary는 정확히 두 문장으로 구성해야 해.
  1) “지난 한 주는 ~”으로 시작하고, 감정 흐름과 식습관 패턴을 반드시 둘 다 포함한 한 문장을 작성해.
     - 감정만 말하는 것도 금지, 식습관만 말하는 것도 금지야.
     - 두 요소는 문장 안에서 동일한 비중으로 언급해.
  2) 다음 주를 위한 응원 또는 성찰을 돕는 귀엽고 부드러운 격려 한 문장을 작성해.
     - 이 두 번째 문장에는 은은한 시적 표현을 한 개만 넣어.
     - 예: “마음에 포근한 빛이 번졌으면 해.”  
           “네 일주일에 작은 온기가 스며들길 바랄게.”  
           “다음 주엔 더 따뜻한 숨결이 찾아오면 좋겠어.”
     - 과한 비유는 금지야. 부드럽고 짧은 감성 표현만 사용해.
- 두 문장 전체 글자 수는 60자 이내. 절대 75자를 넘기지 마.

식습관 규칙:
- 식습관 코멘트는 반드시 포함해야 해.
- 아래 중 하나를 반드시 언급해:
  • 주간 식습관 리듬(안정적/들쑥날쑥 등)
  • 탄·단·지 영양 균형의 흐름
  • 끼니를 챙겨 먹은 리듬
  • 식사의 분위기(가벼움/따뜻함/풍부함 등)
- 칼로리 숫자는 말하지 마.

감정 규칙:
- negative_ratio 많은 날은 조용히 공감해.
- positive_ratio 많은 날은 함께 기뻐해.
- feeling_keywords가 없으면 감정 비율로 감정을 설명해.

과도한 추측 금지. 데이터 기반으로만 작성해.

출력 예시(JSON):
{
 "summary": "문장1 문장2"
}
"""

# 3) 테스트용 하루 데이터 (나중에 DB에서 불러오면 됨)
weekly_data = {
    "user_id": "001",
    "period_start": "2025-12-01",
    "period_end": "2025-12-07",
    "daily_records": [
        {
            "date": "2025-12-01",
            "positive_ratio": 0.20,
            "neutral_ratio": 0.50,
            "negative_ratio": 0.30,
            "feeling_keywords": ["한숨", "안정"],
            "total_kcal": 1650,
            "total_carb": 210,
            "total_protein": 85,
            "total_fat": 60,
        },
        {
            "date": "2025-12-02",
            "positive_ratio": 0.10,
            "neutral_ratio": 0.80,
            "negative_ratio": 0.10,
            "feeling_keywords": ["한숨", "평온", "안정"],
            "total_kcal": 1750,
            "total_carb": 235,
            "total_protein": 75,
            "total_fat": 55,
        },
        {
            "date": "2025-12-03",
            "positive_ratio": 0.20,
            "neutral_ratio": 0.50,
            "negative_ratio": 0.30,
            "feeling_keywords": ["무력감", "만족", "보람"],
            "total_kcal": 1900,
            "total_carb": 240,
            "total_protein": 95,
            "total_fat": 70,
        },
        {
            "date": "2025-12-04",
            "positive_ratio": 0.05,
            "neutral_ratio": 0.70,
            "negative_ratio": 0.25,
            "feeling_keywords": ["무력감"],
            "total_kcal": 1600,
            "total_carb": 210,
            "total_protein": 80,
            "total_fat": 50,
        },
        {
            "date": "2025-12-05",
            "positive_ratio": 0.05,
            "neutral_ratio": 0.75,
            "negative_ratio": 0.20,
            "feeling_keywords": ["분노", "침울"],
            "total_kcal": 1850,
            "total_carb": 230,
            "total_protein": 90,
            "total_fat": 65,
        },
        {
            "date": "2025-12-06",
            "positive_ratio": 0.05,
            "neutral_ratio": 0.65,
            "negative_ratio": 0.30,
            "feeling_keywords": [],
            "total_kcal": 2050,
            "total_carb": 245,
            "total_protein": 85,
            "total_fat": 75,
        },
        {
            "date": "2025-12-07",
            "positive_ratio": 0.20,
            "neutral_ratio": 0.50,
            "negative_ratio": 0.20,
            "feeling_keywords": ["상쾌", "생기", "고뇌"],
            "total_kcal": 1800,
            "total_carb": 225,
            "total_protein": 82,
            "total_fat": 62,
        },
    ],
}


# 4) 메시지 구성
messages = [
    SystemMessage(content=system_prompt),
    HumanMessage(content=json.dumps(weekly_data, ensure_ascii=False)),
]

# 5) LLM 호출
response = llm.invoke(messages)

# 6) 결과 출력
print(response.content)
