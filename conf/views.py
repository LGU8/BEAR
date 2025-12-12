from django.shortcuts import render


def index(request):
    return render(request, "base.html")


def timeline(request):
    context = {
        "active_tab": "timeline",
        # 아래는 지금은 임시값(더미). 나중에 DB/ML/LLM 붙이면 됨
        "week_start": "2026.01.10",
        "week_end": "2026.01.16",
        "risk_label": "위험해요ㅠㅠ",
        "risk_score": 0.78,
        "llm_ment": "오늘은 기분이 좋지 않았네요. 달리기/걷기/음악듣기 중 하나를 해보는 건 어때요?",
    }
    return render(request, "timeline.html", context)
