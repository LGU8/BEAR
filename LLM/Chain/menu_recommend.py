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

# 1) 자료 준비(벡터 DB)
load_dotenv("./Chain/.env")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
persist_directory = "./Chain/menu_chroma_store"

embeddings = OpenAIEmbeddings(model="text-embedding-3-large", api_key=OPENAI_API_KEY)
vectorstore = Chroma(embedding_function=embeddings, persist_directory=persist_directory)
retriever = vectorstore.as_retriever(k=3)

query = "기분이 과도하게 들뜨거나 가라앉지 않도록 혈당 변동을 완만하게 하고 기분 안정에 도움을 주는 음식은 뭐야?"
docs = retriever.invoke(query)

retrieved_text = "\n\n".join([doc.page_content for doc in docs])

# 2) 모델 준비
llm = ChatOpenAI(model="gpt-4o-mini")

# 3) System Prompt (역할 정의)
system_prompt = """
너는 식단과 감정 데이터를 바탕으로
다음 식사에 가장 적합한 메뉴를 하나 선택하는 추천 엔진이야.

너에게는 다음 정보가 주어진다:

1. 사용자의 권장 섭취 영양소 정보 (recommend_info)
   - "carbohydrate", "protein", "fat"은 하루 동안 섭취해야 할 영양소의 목표량이며, 단위는 모두 g(그램)이다.
   - 이 값들은 절대적인 하루 목표량이자, 세 영양소 간의 상대적 비중은 사용자가 선호하는 영양소 비율을 의미한다.
   - 이 영양소들은 하루 동안 두 번 또는 세 번의 식사를 통해 나누어 보충되어야 하며, 한 끼에 모두 충족할 필요는 없다.
2. 가장 최근에 발생한 6번의 식사 기록
   - 각 기록은 날짜(rgs_dt)와 끼니(time_slot)를 기준으로 한 실제 식사이다.
   - 각 기록에는 섭취한 음식, 영양소 섭취량, 감정 상태(mood)와 에너지 수준(energy)이 포함되어 있다.
3. 기분 안정과 음식의 관계에 대한 참고 문서(reference_docs)
   - 음식, 영양소, 감정 간의 관계를 설명하는 참고 자료이다.

판단 원칙:
- 최근 6번의 식사 기록을 시간 순서대로 고려하여,
  최근에 반복적으로 나타나는 감정(mood)과 에너지(energy)의 경향을 파악한다.
- 식사 기록을 통해, 현재까지 섭취한 영양소와 하루 목표 영양소(g 기준) 간의 차이를 우선적으로 판단한다.
- 사용자가 선호하는 영양소 비중을 고려하되, 기분을 과도하게 자극하지 않고 현재 상태를 안정적으로 유지하는 방향을 가장 중요한 기준으로 삼는다.
- reference_docs는 메뉴 선택 시 중요한 참고 근거로 최대한 활용한다.
- reference_docs에 직접 등장하지 않는 음식이라도, 영양 균형과 기분 안정에 부합한다면 선택할 수 있다.
  단, 실제로 존재하는 음식이어야 한다.
- 특정 음식이나 식품군이 반복적으로 추천되지 않도록, 식품의 다양성을 함께 고려한다.
- 여러 후보 중, 현재 사용자 상태에 가장 적합한 메뉴 하나만 최종 선택한다.

출력 규칙:
- 설명을 덧붙이지 않는다.
- 주어와 서술어 없이 메뉴 이름만 출력한다.
- 반드시 하나의 메뉴만 선택한다.
- JSON 형식으로만 출력한다.

출력 형식(JSON):
{
  "message": "메뉴명"
}
"""

"""
사용한 쿼리문
SELECT Recommended_calories, 
	round((Recommended_calories*(Ratio_carb/10))/4) AS Recom_carb, 
    round((Recommended_calories*(Ratio_protein/10))/4) AS Recom_pro,
    round((Recommended_calories*(Ratio_fat/10))/4) AS Recom_fat,
    h.rgs_dt,
    GROUP_CONCAT(name SEPARATOR ', ') AS NAME,
	h.time_slot, h.kcal, h.carb_g, h.protein_g, h.fat_g,
    f.mood, f.energy
FROM bear.CUS_FOOD_TH h
JOIN (SELECT * FROM bear.CUS_PROFILE_TS) p
ON h.cust_id = p.cust_id
JOIN (SELECT * FROM bear.CUS_FOOD_TS) s
ON h.cust_id = s.cust_id AND h.rgs_dt = s.rgs_dt AND h.seq = s.seq
JOIN (SELECT name, food_id FROM bear.FOOD_TB) b
ON s.food_id = b.food_id
JOIN bear.CUS_FEEL_TH f
ON  h.cust_id = f.cust_id AND h.rgs_dt = f.rgs_dt
WHERE h.cust_id = 0000000011
GROUP BY time_slot, rgs_dt
ORDER BY rgs_dt 
LIMIT 6;
"""

# data = {
#   "user_id": "002",
#   "recommend_info": {"kcal": 1522.39,	"carbohydrate":114,	"protein": 152,	"fat": 114},
#   "meal_for_3days": [
#       {"rgs_dt": "20260102",
#         "time_slot": "D",
#         "foods": ["The미식 떡만둣국"],
#         "nutrition": {
#             "kcal": 440,
#             "carb_g": 48,
#             "protein_g": 40,
#             "fat_g": 30
#             },
#         "mood": "pos",
#         "energy": "low"
#         },
#       {
#         "rgs_dt": "20260102",
#         "time_slot": "L",
#         "foods": ["육회비빔밥"],
#         "nutrition": {
#             "kcal": 115,
#             "carb_g": 17,
#             "protein_g": 3,
#             "fat_g": 2
#             },
#         "mood": "pos",
#         "energy": "low"
#         },
#       {
#         "rgs_dt": "20260103",
#         "time_slot": "D",
#         "foods": ["BIG 김치볶음밥"],
#         "nutrition": {
#             "kcal": 483,
#             "carb_g": 74,
#             "protein_g": 7,
#             "fat_g": 9
#             },
#         "mood": "pos",
#         "energy": "med"
#         },
#       {
#         "rgs_dt": "20260103",
#         "time_slot": "L",
#         "foods": ["햇반", "1인부대찌개 의정부찌"],
#         "nutrition": {
#             "kcal": 330,
#             "carb_g": 49,
#             "protein_g": 13,
#             "fat_g": 8
#             },
#         "mood": "pos",
#         "energy": "med"
#         },
#       {
#         "rgs_dt": "20260104",
#         "time_slot": "L",
#         "foods": ["녹차라떼", "리얼딸기케이크"],
#         "nutrition": {
#             "kcal": 695,
#             "carb_g": 97,
#             "protein_g": 7,
#             "fat_g": 29
#           },
#         "mood": "pos",
#         "energy": "low"
#       }
#   ]
# }

data = {
  "user_id": "0000000011",	
  "recommend_info": {"kcal": 2019.61,	"carbohydrate": 151,	"protein":202 ,	"fat":151 },
  "meal_data": [
    {
        "rgs_dt": "20251120",
        "time_slot": "L",
        "foods": ["모짜렐라토마토파스타"],
        "nutrition": {
            "kcal": 635,
            "carb_g": 55,
            "protein_g": 21,
            "fat_g": 28
        },
        "mood": "neg",
        "energy": "low"
    },
    {
        "rgs_dt": "20251120",
        "time_slot": "D",
        "foods": ["방어(야드)회"],
        "nutrition": {
            "kcal": 108,
            "carb_g": 0,
            "protein_g": 22,
            "fat_g": 2
        },
        "mood": "neg",
        "energy": "low"
    },
    {
        "rgs_dt": "20251124",
        "time_slot": "D",
        "foods": ["햇반", "1인부대찌개 의정부찌"],
        "nutrition": {
            "kcal": 330,
            "carb_g": 49,
            "protein_g": 13,
            "fat_g": 8
            },
        "mood": "pos",
        "energy": "med"
    },
    {
        "rgs_dt": "20251124",
        "time_slot": "L",
        "foods": ["불낙전골"],
        "nutrition": {
            "kcal": 63,
            "carb_g": 5,
            "protein_g": 6,
            "fat_g": 1
        },
        "mood": "pos",
        "energy": "med"
    },
    {
        "rgs_dt": "20251126",
        "time_slot": "D",
        "foods": ["핫도그"],
        "nutrition": {
            "kcal": 258,
            "carb_g": 28,
            "protein_g": 10,
            "fat_g": 11
        },
        "mood": "pos",
        "energy": "hig"
    },
    {
        "rgs_dt": "20251126",
        "time_slot": "L",
        "foods": ["명란크림파스타"],
        "nutrition": {
            "kcal": 635,
            "carb_g": 55,
            "protein_g": 21,
            "fat_g": 28
        },
        "mood": "neg",
        "energy": "hig"
    }
  ]
}


# 5) 메시지 구성
human_payload = {
"data": data,
"reference_docs": retrieved_text
}
messages = [
    SystemMessage(content=system_prompt),
    HumanMessage(content=json.dumps(human_payload, ensure_ascii=False)),
]

# 6) LLM 호출
response = llm.invoke(messages)

# 7) 결과 출력
print(response.content)
