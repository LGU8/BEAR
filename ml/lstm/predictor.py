# ml/lstm/predictor.py
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set

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
WINDOW = 7        # 최근 7개 record(가변 N일)
# ✅ GATE_DAYS는 더 이상 "고정 3일"에 쓰지 않음 (원하는 로직이 가변 N일이므로)


# =========================
# Artifacts
# =========================
@dataclass(frozen=True)
class Artifacts:
    cfg: dict
    scaler: Any
    model: LSTMClassifier
    device: torch.device
    cluster_mean: Dict[str, Tuple[float, float]]  # cluster_val -> (mean_valence, mean_arousal)


def _time_onehot(time_slot: str) -> Tuple[float, float, float]:
    """
    CUS_FEEL_TH.time_slot: M/L/D -> time_morning/time_afternoon/time_evening
    """
    ts = (time_slot or "").upper()
    return (
        1.0 if ts == "M" else 0.0,
        1.0 if ts == "L" else 0.0,
        1.0 if ts == "D" else 0.0,
    )


def _slot_order(time_slot: str) -> int:
    return {"M": 0, "L": 1, "D": 2}.get((time_slot or "").upper(), 9)


def _fetchall_dict(sql: str, params: Tuple = ()) -> List[Dict[str, Any]]:
    with connection.cursor() as cur:
        cur.execute(sql, params)
        cols = [c[0] for c in cur.description]
        rows = cur.fetchall()
    out: List[Dict[str, Any]] = []
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

    state = torch.load(pt_path, map_location=device)
    model.load_state_dict(state)
    model.eval()

    # cluster_val별 평균 valence/arousal
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
        cfg=cfg,
        scaler=scaler,
        model=model,
        device=device,
        cluster_mean=cluster_mean,
    )


# =========================================================
# ✅ NEW: 최근 WINDOW=7개 기록(가변 N일) 가져오기
# =========================================================
def fetch_last_window_records(
    cust_id: str,
    asof_yyyymmdd: str,
) -> List[Dict[str, Any]]:
    """
    ✅ asof_yyyymmdd(포함)까지의 CUS_FEEL_TH 중
    최신 기록 7개를 가져온다. (날짜 범위는 가변)

    정렬 기준:
      - rgs_dt DESC
      - time_slot DESC (D > L > M)
      - seq DESC
    """
    sql = """
        SELECT cust_id, rgs_dt, seq, time_slot, cluster_val
        FROM CUS_FEEL_TH
        WHERE cust_id = %s
          AND rgs_dt <= %s
        ORDER BY
          rgs_dt DESC,
          CASE time_slot
            WHEN 'D' THEN 3
            WHEN 'L' THEN 2
            WHEN 'M' THEN 1
            ELSE 0
          END DESC,
          seq DESC
        LIMIT %s
    """
    rows = _fetchall_dict(sql, (cust_id, asof_yyyymmdd, WINDOW))

    # rows는 최신순(내림차순) → feature build는 시간순(오름차순) 필요
    rows.reverse()
    return rows


# =========================================================
# ✅ NEW: Gate = "Window에 포함된 N일" 모두 키워드 1건 이상
# =========================================================
def gate_keyword_every_day_in_range(
    cust_id: str,
    days: List[str],
) -> Tuple[bool, List[str]]:
    """
    ✅ days에 포함된 각 날짜별로 CUS_FEEL_TS가 최소 1건 있어야 통과.
    반환: (ok, missing_days)
    """
    uniq_days = sorted({str(d) for d in (days or []) if d})
    if not uniq_days:
        return (False, [])

    placeholders = ",".join(["%s"] * len(uniq_days))
    sql = f"""
        SELECT DISTINCT rgs_dt
        FROM CUS_FEEL_TS
        WHERE cust_id = %s
          AND rgs_dt IN ({placeholders})
    """
    with connection.cursor() as cur:
        cur.execute(sql, [cust_id, *uniq_days])
        have = {str(r[0]) for r in cur.fetchall() if r and r[0]}

    missing = [d for d in uniq_days if d not in have]
    return (len(missing) == 0, missing)


# =========================================================
# Feature building (기존 유지)
# =========================================================
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
    sql_ts = """
        SELECT feel_id
        FROM CUS_FEEL_TS
        WHERE cust_id = %s AND rgs_dt = %s AND seq = %s
    """
    ts_rows = _fetchall_dict(sql_ts, (cust_id, rgs_dt, seq))
    feel_ids = [r["feel_id"] for r in ts_rows if r["feel_id"] is not None]

    if feel_ids:
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


# =========================================================
# ✅ NEW: readiness 진단(가변 N일 Gate 기준)
# =========================================================
def diagnose_negative_risk_readiness(
    cust_id: str,
    asof_yyyymmdd: Optional[str] = None,
) -> Dict[str, Any]:
    """
    ✅ LSTM inference 없이 "예측 가능 여부"만 진단
    - Window(최근 7개 기록) 확보 여부
    - Gate(그 7개가 포함하는 N일 모두 키워드 1회 이상) 여부
    """
    if asof_yyyymmdd is None:
        asof_yyyymmdd = _yyyymmdd(timezone.localdate())

    records = fetch_last_window_records(cust_id, asof_yyyymmdd)

    if len(records) < WINDOW:
        return {
            "ready": False,
            "reason": "데이터가 부족합니다",
            "detail": {
                "type": "window_insufficient",
                "rule": "최근 기록 7개(M/L/D 합) 확보 필요",
                "asof": asof_yyyymmdd,
                "need": WINDOW,
                "have": len(records),
            },
        }

    days = sorted({str(r["rgs_dt"]) for r in records if r.get("rgs_dt")})
    ok, missing_days = gate_keyword_every_day_in_range(cust_id, days)
    if not ok:
        return {
            "ready": False,
            "reason": "데이터가 부족합니다",
            "detail": {
                "type": "gate_keyword_every_day",
                "rule": "최근 7개 기록이 포함하는 모든 날짜에 키워드 1회 이상 필요",
                "asof": asof_yyyymmdd,
                "days": days,
                "missing_days": missing_days,
            },
        }

    return {
        "ready": True,
        "detail": {
            "type": "ready",
            "asof": asof_yyyymmdd,
            "days": days,
            "missing_days": [],
        },
    }


# =========================================================
# Main predictor (가변 N일 Gate + 최근 7개 Window)
# =========================================================
def predict_negative_risk(
    cust_id: str,
    D_yyyymmdd: Optional[str] = None,
) -> Dict[str, Any]:
    """
    ✅ 타임라인 "부정감정 예측" 결과 반환.
    - Window: asof까지 최근 7개 기록 확보
    - Gate: 그 7개 기록이 포함하는 N일 모두 TS(키워드) 1회 이상
    - 성공 -> p_highrisk, probs 등 반환
    """
    art = load_artifacts()

    if D_yyyymmdd is None:
        D_yyyymmdd = _yyyymmdd(timezone.localdate())

    # 1) Window: 최근 7개 기록 확보
    records = fetch_last_window_records(cust_id, D_yyyymmdd)
    if len(records) < WINDOW:
        return {
            "eligible": False,
            "reason": "데이터가 부족합니다",
            "detail": {
                "type": "window_insufficient",
                "rule": "최근 기록 7개(M/L/D 합) 확보 필요",
                "asof": D_yyyymmdd,
                "need": WINDOW,
                "have": len(records),
                "missing_days": [],  # template 안정성
            },
        }

    # 2) Gate: Window가 포함하는 N일 모두 키워드 1회 이상
    days = sorted({str(r["rgs_dt"]) for r in records if r.get("rgs_dt")})
    ok, missing_days = gate_keyword_every_day_in_range(cust_id, days)
    if not ok:
        return {
            "eligible": False,
            "reason": "데이터가 부족합니다",
            "detail": {
                "type": "gate_keyword_every_day",
                "rule": "최근 7개 기록이 포함하는 모든 날짜에 키워드 1회 이상 필요",
                "asof": D_yyyymmdd,
                "days": days,
                "missing_days": missing_days,
            },
            "missing_days": missing_days,  # top-level도 같이
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
                "missing_days": [],  # template 안정성
            },
            "missing_days": [],
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
                "missing_days": [],
            },
            "missing_days": [],
        }

    # 5) LSTM inference
    x_t = torch.tensor(Xs, dtype=torch.float32, device=art.device).unsqueeze(0)  # (1,7,7)
    with torch.no_grad():
        logits = art.model(x_t)  # (1,6)
        probs = F.softmax(logits, dim=1).cpu().numpy().reshape(-1)  # (6,)

    p0, p1, p2, p3, p4, p5 = [float(x) for x in probs.tolist()]
    p_highrisk = p0 + p2
    is_risky = bool(p_highrisk >= THRESHOLD)
    pred_class = int(np.argmax(probs))

    return {
        "eligible": True,
        "asof": D_yyyymmdd,
        "days": days,  # ✅ 이번 Window가 걸친 N일
        "missing_days": [],  # ✅ template 안정성
        "high_risk_set": sorted(list(HIGH_RISK_SET)),
        "threshold": THRESHOLD,
        "p_highrisk": p_highrisk,
        "p0": p0,
        "p1": p1,
        "p2": p2,
        "p3": p3,
        "p4": p4,
        "p5": p5,
        "is_risky": is_risky,
        "pred_class": pred_class,
        "probs": [float(x) for x in probs.tolist()],
        "window_records": meta,  # 7개 기록 + source
    }
