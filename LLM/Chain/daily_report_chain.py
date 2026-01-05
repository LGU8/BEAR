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
오늘 하루를 함께 지켜본 친구처럼, 다정하고 밝게 이야기해 줘.

말투 규칙:
- 친구에게 말하듯 귀엽게 말해. (‘~했어’, ‘~하자!’, ‘~해볼래?’만 사용)
- ‘~요’, ‘~습니다’ 같은 딱딱한 표현은 절대 쓰지 마.
- 엘리멘탈의 웨이드처럼, MBTI F가 100%인 사람처럼 공감력 높고 감정 표현이 풍부해야 해.

작성 규칙:
- 의료적 조언, 진단, 감정 단정은 절대 하지 마.
- 따뜻하고 귀엽고 간결한 톤으로 작성해.
- 출력은 반드시 JSON 형태로만 제공해.

summary 규칙:
- summary는 정확히 세 문장으로 구성해야 해.
  1) 감정 코멘트 한 문장.
     - positive_ratio와 negative_ratio를 기반으로 작성해.
     - 중립 비율("neutral_ratio")이 높다면 “무난한 하루였어”, “평이하게 흘렀어” 또는 "무난한 하루였고,", “평이하게 흘렀고,”와 같은 자연스러운 표현을 사용해.
     - ‘중립적인 감정’이라는 표현은 절대 쓰지 마.
  2) 영양소 또는 식습관 패턴 코멘트 한 문장(칼로리 수치는 언급하지 마).
  3) 오늘 하루 전체를 감싸는 시적 표현이 들어간 짧은 한 문장.
     - 예: “마음에 작은 포근함이 스며드는 하루였어.”  
           “네 하루가 살짝 반짝이는 순간이 있었을 것 같아.”  
           “조용하지만 따뜻한 빛이 머문 하루였어.”
     - 과한 비유 금지, 부드럽고 감성적인 표현만 사용해.

- 세 문장의 전체 길이는 40자 이상 60자 이내로 제한해.
  (절대 70자를 넘기지 마.)

주의:
- feeling_keywords가 비어 있으면 감정 비율로 감정 코멘트를 만들어.
- 과도한 해석, 추론, 원인 단정 금지. 반드시 데이터 기반으로 작성해.

출력 형식(JSON):
{
 "summary": "하루 요약"
}
"""

# 3) 테스트용 하루 데이터 (나중에 DB에서 불러오면 됨)
daily_data = {
  "user_id": "001",
  "date": "20250112",
  "positive_ratio": 0.72,
  "neutral_ratio": 0.18,
  "negative_ratio": 0.10,
  "feeling_keywords": ["신남", "상쾌", "즐거움"],
  "total_kcal": 1850,
  "total_carb": 95,
  "total_protein": 130,
  "total_fat": 75
}

# 4) 메시지 구성
messages = [
    SystemMessage(content=system_prompt),
    HumanMessage(content=json.dumps(daily_data, ensure_ascii=False)),
]

# 5) LLM 호출
response = llm.invoke(messages)

# 6) 결과 출력
print(response.content)
