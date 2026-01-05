from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
import json
import pandas as pd
import os

# API_KEY Load
from dotenv import load_dotenv

load_dotenv()  # ← 이것이 .env 파일을 실제로 불러옴!

# 1) 자료 준비
# 1-1) csv 파일
action_data = pd.read_csv("../RAG/behavior_numeric.csv")
action_data['final_score'] = (0.5*action_data['rule_score']) + (0.5*action_data['cf_score'])
top5_action = action_data.sort_values('final_score', ascending=False).head(3)["activity"].tolist()

# 1-2) 벡터 DB
load_dotenv("../Chain/.env")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
persist_directory = "./chroma_store"

embeddings = OpenAIEmbeddings(model="text-embedding-3-large", api_key=OPENAI_API_KEY)
vectorstore = Chroma(embedding_function=embeddings, persist_directory=persist_directory)
retriever = vectorstore.as_retriever(k=3)

query = "부정적인 감정일 때, 기분 개선에 효과적인 추천 행동은 뭐야?"
docs = retriever.invoke(query)

retrieved_text = "\n\n".join([doc.page_content for doc in docs])

# 2) 모델 준비
llm = ChatOpenAI(model="gpt-4o-mini")

# 3) System Prompt (역할 정의)
system_prompt_level0 = """
오늘 하루를 시작하며, 가볍게 힘이 되는 응원 메시지를 전해줘.

말투 규칙:
- 친구에게 말하듯 귀엽게 말해. (‘~했어’, ‘~하자!’, ‘~해볼래?’만 사용)
- 상대를 직접 부르는 호칭(예: 친구야, 너는 등)은 사용하지 마.
- ‘~요’, ‘~습니다’ 같은 딱딱한 표현은 절대 쓰지 마.
- 엘리멘탈의 웨이드처럼, MBTI F가 100%인 사람처럼 공감력 높고 감정 표현이 풍부해야 해.

참고 자료:
- risk_score: 50 이하면 부정감정을 느낄 확률이 낮음. 즉, 부정감정 위험도가 0이야.

작성 규칙:
- 오늘의 기분이나 하루를 단정하지 마.
- “오늘은 이런 하루가 될 수 있어”처럼 가능성의 톤으로 말해.
- 의료적 조언, 진단은 절대 하지 마.
- 시적인 표현이 자연스럽게 들어간 문장으로 작성해.
- 출력은 반드시 JSON 형태로만 제공해.
- 전체 길이는 40자 이상 70자 이내 (80자 초과 금지)


출력 형식(JSON):
{
 "message": "오늘의 메세지"
}
"""

system_prompt_level1 = """
너의 역할은 부정 감정을 느낄 위험도가 높으면, 기분을 완화시킬 수 있는 행동을 추천해주는 거야.

말투 규칙:
- 친구에게 말하듯 귀엽게 말해. (‘~했어’, ‘~하자!’, ‘~해볼래?’만 사용)
- ‘~요’, ‘~습니다’ 같은 딱딱한 표현은 절대 쓰지 마.
- 엘리멘탈의 웨이드처럼, MBTI F가 100%인 사람처럼 공감력 높고 감정 표현이 풍부해야 해.

참고 자료:
- top5_action
- docs
- negative_ratio

참고 규칙:
- feeling_data는 오늘 위험도와 최근 일주일 감정 흐름을 담고 있어.
- 이를 바탕으로 행동 추천의 “강도”만 조절해.
- 수치나 비율은 직접 언급하지 마.

작성 규칙:
- 의료적 조언, 진단, 감정 단정은 절대 하지 마.
- 따뜻하고 귀엽고 간결한 톤으로 작성해.
- 출력은 반드시 JSON 형태로만 제공해.
- 세 문장의 전체 길이는 40자 이상 70자 이내로 제한해.
  (절대 80자를 넘기지 마.)


출력 형식(JSON):
{
 "message": "오늘의 메세지"
}
"""

# 4) 테스트용 데이터 (나중에 DB에서 불러오면 됨)
# feeling_data = {
#   "user_id": "001",
#   "date": "2025-01-10",
#   "period_start": "2025-01-04",
#   "period_end": "2025-01-10",
#   "today_risk": {
#     "risk_score": 72,
#     "risk_level": 1
#   },
#   "weekly_emotions": [
#     {
#       "date": "2025-01-04",
#       "positive_ratio": 0.10,
#       "neutral_ratio": 0.30,
#       "negative_ratio": 0.60,
#       "feeling_keywords": ["무력감", "우울"]
#     },
#     {
#       "date": "2025-01-05",
#       "positive_ratio": 0.15,
#       "neutral_ratio": 0.25,
#       "negative_ratio": 0.60,
#       "feeling_keywords": ["좌절감", "무력감"]
#     },
#     {
#       "date": "2025-01-06",
#       "positive_ratio": 0.10,
#       "neutral_ratio": 0.35,
#       "negative_ratio": 0.55,
#       "feeling_keywords": ["침울"]
#     },
#     {
#       "date": "2025-01-07",
#       "positive_ratio": 0.12,
#       "neutral_ratio": 0.28,
#       "negative_ratio": 0.60,
#       "feeling_keywords": ["소외감"]
#     },
#     {
#       "date": "2025-01-08",
#       "positive_ratio": 0.08,
#       "neutral_ratio": 0.32,
#       "negative_ratio": 0.60,
#       "feeling_keywords": ["우울"]
#     },
#     {
#       "date": "2025-01-09",
#       "positive_ratio": 0.15,
#       "neutral_ratio": 0.30,
#       "negative_ratio": 0.55,
#       "feeling_keywords": ["불쾌감"]
#     },
#     {
#       "date": "2025-01-10",
#       "positive_ratio": 0.12,
#       "neutral_ratio": 0.33,
#       "negative_ratio": 0.55,
#       "feeling_keywords": ["침울"]
#     }
#   ]
# }

feeling_data = {
  "user_id": "002",
  "date": "2025-01-10",
  "period_start": "2025-01-04",
  "period_end": "2025-01-10",
  "today_risk": {
    "risk_score": 28,
    "risk_level": 0
  },
  "weekly_emotions": [
    {
      "date": "2025-01-04",
      "positive_ratio": 0.55,
      "neutral_ratio": 0.30,
      "negative_ratio": 0.15,
      "feeling_keywords": ["만족"]
    },
    {
      "date": "2025-01-05",
      "positive_ratio": 0.50,
      "neutral_ratio": 0.35,
      "negative_ratio": 0.15,
      "feeling_keywords": ["안정"]
    },
    {
      "date": "2025-01-06",
      "positive_ratio": 0.48,
      "neutral_ratio": 0.32,
      "negative_ratio": 0.20,
      "feeling_keywords": ["차분"]
    },
    {
      "date": "2025-01-07",
      "positive_ratio": 0.25,
      "neutral_ratio": 0.35,
      "negative_ratio": 0.40,
      "feeling_keywords": ["피곤함"]
    },
    {
      "date": "2025-01-08",
      "positive_ratio": 0.20,
      "neutral_ratio": 0.30,
      "negative_ratio": 0.50,
      "feeling_keywords": ["긴장"]
    },
    {
      "date": "2025-01-09",
      "positive_ratio": 0.18,
      "neutral_ratio": 0.28,
      "negative_ratio": 0.54,
      "feeling_keywords": ["불안"]
    },
    {
      "date": "2025-01-10",
      "positive_ratio": 0.20,
      "neutral_ratio": 0.30,
      "negative_ratio": 0.50,
      "feeling_keywords": ["지침"]
    }
  ]
}

# feeling_data = {
#   "user_id": "003",
#   "date": "2025-01-10",
#   "period_start": "2025-01-04",
#   "period_end": "2025-01-10",
#   "today_risk": {
#     "risk_score": 22,
#     "risk_level": 0
#   },
#   "weekly_emotions": [
#     {
#       "date": "2025-01-04",
#       "positive_ratio": 0.45,
#       "neutral_ratio": 0.45,
#       "negative_ratio": 0.10,
#       "feeling_keywords": ["편안"]
#     },
#     {
#       "date": "2025-01-05",
#       "positive_ratio": 0.50,
#       "neutral_ratio": 0.40,
#       "negative_ratio": 0.10,
#       "feeling_keywords": ["만족"]
#     },
#     {
#       "date": "2025-01-06",
#       "positive_ratio": 0.48,
#       "neutral_ratio": 0.42,
#       "negative_ratio": 0.10,
#       "feeling_keywords": ["차분"]
#     },
#     {
#       "date": "2025-01-07",
#       "positive_ratio": 0.52,
#       "neutral_ratio": 0.38,
#       "negative_ratio": 0.10,
#       "feeling_keywords": ["기분좋음"]
#     },
#     {
#       "date": "2025-01-08",
#       "positive_ratio": 0.50,
#       "neutral_ratio": 0.40,
#       "negative_ratio": 0.10,
#       "feeling_keywords": ["안정"]
#     },
#     {
#       "date": "2025-01-09",
#       "positive_ratio": 0.55,
#       "neutral_ratio": 0.35,
#       "negative_ratio": 0.10,
#       "feeling_keywords": ["여유"]
#     },
#     {
#       "date": "2025-01-10",
#       "positive_ratio": 0.50,
#       "neutral_ratio": 0.40,
#       "negative_ratio": 0.10,
#       "feeling_keywords": ["평온"]
#     }
#   ]
# }


# 5) 메시지 구성
if feeling_data['today_risk']['risk_level'] == 0:
    messages = [
        SystemMessage(content=system_prompt_level0),
        HumanMessage(content=json.dumps(feeling_data, ensure_ascii=False)),
    ]
else:
    human_payload = {
    "feeling_data": feeling_data,
    "top5_action": top5_action,
    "reference_docs": retrieved_text
    }
    messages = [
        SystemMessage(content=system_prompt_level1),
        HumanMessage(content=json.dumps(human_payload, ensure_ascii=False)),
    ]

# 6) LLM 호출
response = llm.invoke(messages)

# 7) 결과 출력
print(response.content)
