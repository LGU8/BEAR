# ml/lstm/predictor.py
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn.functional as F
import joblib

from django.db import connection
from django.utils import timezone

from .model import LSTMClassifier


# =========================
# 정책(Policy)
# =========================
HIGH_RISK_SET = {0, 2}
THRESHOLD = 0.30  # p0+p2 >= 0.30 이면 위험
WINDOW = 7  # 최근 7개 record
GATE_DAYS = 3  # 직전 3일 고정


# =========================
# Artifacts
# =========================
@dataclass(frozen=True)
class Artifacts:
    cfg: dict
    scaler: Any
    model: LSTMClassifier
    device: torch.device
    cluster_mean: Dict[
        str, Tuple[float, float]
    ]  # cluster_val -> (mean_valence, mean_arousal)


def _time_onehot(time_slot: str) -> Tuple[float, float, float]:
    """
    CUS_FEEL_TH.time_slot: M/L/D -> time_morning/time_afternoon/time_evening
    """
    return (
        1.0 if time_slot == "M" else 0.0,
        1.0 if time_slot == "L" else 0.0,
        1.0 if time_slot == "D" else 0.0,
    )


def _slot_order(time_slot: str) -> int:
    return {"M": 0, "L": 1, "D": 2}.get(time_slot, 9)


def _fetchall_dict(sql: str, params: Tuple = ()) -> List[Dict[str, Any]]:
    with connection.cursor() as cur:
        cur.execute(sql, params)
        cols = [c[0] for c in cur.description]
        rows = cur.fetchall()
    out = []
    for r in rows:
        out.append({cols[i]: r[i] for i in range(len(cols))})
    return out


def _fetchone_dict(sql: str, params: Tuple = ()) -> Optional[Dict[str, Any]]:
    rows = _fetchall_dict(sql, params)
    return rows[0] if rows else None


def _to_float(x) -> Optional[float]:
    if x is None:
        return None
    return float(x)


def _yyyymmdd(dt) -> str:
    return dt.strftime("%Y%m%d")


def _prev_days(D_yyyymmdd: str) -> Tuple[str, str, str]:
    """
    D 기준 직전 3일: (D-3, D-2, D-1)
    """
    from datetime import datetime, timedelta

    D = datetime.strptime(D_yyyymmdd, "%Y%m%d").date()
    d1 = D - timedelta(days=1)
    d2 = D - timedelta(days=2)
    d3 = D - timedelta(days=3)
    return (_yyyymmdd(d3), _yyyymmdd(d2), _yyyymmdd(d1))


@lru_cache(maxsize=1)
def load_artifacts() -> Artifacts:
    """
    서버에서 최초 1회 로딩 후 캐시.
    """
    base_dir = Path(__file__).resolve().parent
    art_dir = base_dir / "artifacts"

    cfg_path = art_dir / "lstm_config.json"
    pt_path = art_dir / "lstm_final.pt"
    scaler_path = art_dir / "lstm_scaler.pkl"

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    scaler = joblib.load(scaler_path)

    device = torch.device("cpu")

    model = LSTMClassifier(
        input_dim=cfg["input_dim"],
        hidden_dim=cfg["hidden_dim"],
        num_classes=cfg["num_classes"],
    ).to(device)

    # state_dict 로드
    state = torch.load(pt_path, map_location=device)
    model.load_state_dict(state)
    model.eval()

    # cluster_val별 평균 valence/arousal 미리 계산
    # (COM_FEEL_TM: cluster_val, valence, arousal)
    sql = """
        SELECT cluster_val,
               AVG(valence) AS mean_valence,
               AVG(arousal) AS mean_arousal
        FROM COM_FEEL_TM
        GROUP BY cluster_val
    """
    rows = _fetchall_dict(sql)
    cluster_mean: Dict[str, Tuple[float, float]] = {}
    for r in rows:
        cv = r["cluster_val"]
        mv = _to_float(r["mean_valence"])
        ma = _to_float(r["mean_arousal"])
        if cv is None or mv is None or ma is None:
            continue
        cluster_mean[str(cv)] = (mv, ma)

    return Artifacts(
        cfg=cfg, scaler=scaler, model=model, device=device, cluster_mean=cluster_mean
    )


# =========================
# Gate
# =========================
def gate_keyword_3days(cust_id: str, D_yyyymmdd: str) -> Tuple[bool, List[str]]:
    """
    직전 3일(D-3~D-1) 각각 CUS_FEEL_TS에 keyword 1건 이상 존재해야 통과.
    """
    d3, d2, d1 = _prev_days(D_yyyymmdd)
    missing: List[str] = []

    sql_exists = """
        SELECT 1
        FROM CUS_FEEL_TS
        WHERE cust_id = %s AND rgs_dt = %s
        LIMIT 1
    """

    for day in [d3, d2, d1]:
        row = _fetchone_dict(sql_exists, (cust_id, day))
        if row is None:
            missing.append(day)

    return (len(missing) == 0, missing)


# =========================
# Window records
# =========================
def fetch_window_records(cust_id: str, D_yyyymmdd: str) -> List[Dict[str, Any]]:
    """
    D-3~D-1 범위의 CUS_FEEL_TH record를 모아
    (rgs_dt asc, time_slot asc, seq asc) 정렬 후 마지막 7개 반환.

    record key: cust_id, rgs_dt, seq
    필요값: time_slot, cluster_val
    """
    d3, d2, d1 = _prev_days(D_yyyymmdd)

    sql = """
        SELECT cust_id, rgs_dt, seq, time_slot, cluster_val
        FROM CUS_FEEL_TH
        WHERE cust_id = %s
          AND rgs_dt IN (%s, %s, %s)
    """
    rows = _fetchall_dict(sql, (cust_id, d3, d2, d1))

    # 정렬
    rows.sort(key=lambda r: (r["rgs_dt"], _slot_order(r["time_slot"]), int(r["seq"])))

    if len(rows) < WINDOW:
        return []

    return rows[-WINDOW:]


# =========================
# Feature building
# =========================
def valence_arousal_for_record(
    art: Artifacts,
    cust_id: str,
    rgs_dt: str,
    seq: int,
    cluster_val: Optional[str],
) -> Tuple[float, float, str]:
    """
    반환: (valence, arousal, source)
    source:
      - "keyword_mean" : CUS_FEEL_TS feel_id 기반 평균
      - "cluster_fallback" : cluster_val 기반 평균
    """
    # 1) keyword 존재 여부
    sql_ts = """
        SELECT feel_id
        FROM CUS_FEEL_TS
        WHERE cust_id = %s AND rgs_dt = %s AND seq = %s
    """
    ts_rows = _fetchall_dict(sql_ts, (cust_id, rgs_dt, seq))
    feel_ids = [r["feel_id"] for r in ts_rows if r["feel_id"] is not None]

    if feel_ids:
        # feel_id들로 COM_FEEL_TM 평균
        # IN 절 파라미터 안전 구성
        placeholders = ",".join(["%s"] * len(feel_ids))
        sql_agg = f"""
            SELECT AVG(valence) AS mean_valence,
                   AVG(arousal) AS mean_arousal
            FROM COM_FEEL_TM
            WHERE feel_id IN ({placeholders})
        """
        agg = _fetchone_dict(sql_agg, tuple(feel_ids))
        mv = _to_float(agg["mean_valence"]) if agg else None
        ma = _to_float(agg["mean_arousal"]) if agg else None
        if mv is None or ma is None:
            raise ValueError(f"COM_FEEL_TM 평균 실패: feel_ids={feel_ids}")
        return mv, ma, "keyword_mean"

    # 2) keyword 없음 -> cluster fallback
    if cluster_val is None:
        raise ValueError(f"키워드 없음 + cluster_val 없음: {cust_id=} {rgs_dt=} {seq=}")

    cv = str(cluster_val)
    if cv not in art.cluster_mean:
        raise ValueError(f"cluster 평균 없음: cluster_val={cv}")

    mv, ma = art.cluster_mean[cv]
    return mv, ma, "cluster_fallback"


def build_feature_matrix(
    art: Artifacts,
    records: List[Dict[str, Any]],
) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    """
    records(7개) -> X(7,7) 생성 + meta 반환
    feature 순서(고정):
      [valence, arousal, valence_delta, arousal_delta, time_morning, time_afternoon, time_evening]
    """
    feats: List[List[float]] = []
    meta: List[Dict[str, Any]] = []

    for r in records:
        rgs_dt = str(r["rgs_dt"])
        seq = int(r["seq"])
        time_slot = str(r["time_slot"])
        cluster_val = r.get("cluster_val", None)

        v, a, src = valence_arousal_for_record(
            art=art,
            cust_id=str(r["cust_id"]),
            rgs_dt=rgs_dt,
            seq=seq,
            cluster_val=cluster_val,
        )

        tm, ta, te = _time_onehot(time_slot)

        # delta는 뒤에서 채움
        feats.append([v, a, 0.0, 0.0, tm, ta, te])

        meta.append(
            {
                "rgs_dt": rgs_dt,
                "seq": seq,
                "time_slot": time_slot,
                "cluster_val": None if cluster_val is None else str(cluster_val),
                "valence": v,
                "arousal": a,
                "source": src,  # keyword_mean / cluster_fallback
            }
        )

    X = np.array(feats, dtype=np.float32)  # (7,7)

    # delta 채우기
    for i in range(1, X.shape[0]):
        X[i, 2] = X[i, 0] - X[i - 1, 0]
        X[i, 3] = X[i, 1] - X[i - 1, 1]

    return X, meta


# =========================
# Main predictor
# =========================
def predict_negative_risk(
    cust_id: str,
    D_yyyymmdd: Optional[str] = None,
) -> Dict[str, Any]:
    """
    타임라인 "부정감정 예측" 결과 반환.
    - gate 실패 or window 부족 -> eligible False
    - 성공 -> p_highrisk, is_risky, probs 등 반환
    """
    art = load_artifacts()

    if D_yyyymmdd is None:
        D_yyyymmdd = _yyyymmdd(timezone.localdate())

    # 1) Gate
    ok, missing_days = gate_keyword_3days(cust_id, D_yyyymmdd)
    if not ok:
        return {
            "eligible": False,
            "reason": "데이터가 부족합니다",
            "detail": {
                "type": "gate_keyword_3days",
                "rule": "직전 3일(D-3~D-1) 매일 키워드 1회 이상 필요",
                "asof": D_yyyymmdd,
                "missing_days": missing_days,
            },
        }

    # 2) Window records
    records = fetch_window_records(cust_id, D_yyyymmdd)
    if len(records) < WINDOW:
        return {
            "eligible": False,
            "reason": "데이터가 부족합니다",
            "detail": {
                "type": "window_insufficient",
                "rule": "직전 3일 범위에서 최소 7개의 기록(M/L/D)이 필요",
                "asof": D_yyyymmdd,
                "need": WINDOW,
                "have": len(records),
                "days": list(_prev_days(D_yyyymmdd)),
            },
        }

    # 3) Feature matrix
    try:
        X, meta = build_feature_matrix(art, records)
    except Exception as e:
        return {
            "eligible": False,
            "reason": "예측을 위한 값 생성에 실패했습니다",
            "detail": {
                "type": "feature_build_failed",
                "asof": D_yyyymmdd,
                "error": str(e),
            },
        }

    # 4) Scaler transform
    try:
        Xs = art.scaler.transform(X)  # (7,7)
    except Exception as e:
        return {
            "eligible": False,
            "reason": "스케일 변환에 실패했습니다",
            "detail": {
                "type": "scaler_failed",
                "asof": D_yyyymmdd,
                "error": str(e),
            },
        }

    # 5) LSTM inference
    x_t = torch.tensor(Xs, dtype=torch.float32, device=art.device).unsqueeze(
        0
    )  # (1,7,7)

    with torch.no_grad():
        logits = art.model(x_t)  # (1,6)
        probs = F.softmax(logits, dim=1).cpu().numpy()  # (1,6)
        probs = probs.reshape(-1)  # (6,)
    p0 = float(probs[0])
    p2 = float(probs[2])
    p1 = float(probs[1])
    p3 = float(probs[3])
    p5 = float(probs[5])
    p4 = float(probs[4])
    p_highrisk = p0 + p2 

    # p_highrisk = float(probs[0] + probs[2])
    is_risky = bool(p_highrisk >= THRESHOLD)
    pred_class = int(np.argmax(probs))

    return {
        "eligible": True,
        "asof": D_yyyymmdd,
        "high_risk_set": sorted(list(HIGH_RISK_SET)),
        "threshold": THRESHOLD,
        "p_highrisk": p_highrisk,
        "p0": p0,
        "p2": p2,
        "p1": p1,
        "p3": p3,
        "p4": p4,
        "p5": p5,
        "is_risky": is_risky,
        "pred_class": pred_class,
        "probs": [float(x) for x in probs.tolist()],
        "window_records": meta,  # 7개 기록 + source(keyword_mean/cluster_fallback)
    }
