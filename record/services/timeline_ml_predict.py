def predict_negative_risk(user, weekly_summary: dict):
    # TODO: 모델 로드 + feature 생성 + predict
    risk_score = 0.78

    if risk_score >= 0.7:
        risk_label = "위험해요ㅠㅠ"
    elif risk_score >= 0.4:
        risk_label = "주의해요"
    else:
        risk_label = "안정적이에요"

    return {"risk_score": risk_score, "risk_label": risk_label}


