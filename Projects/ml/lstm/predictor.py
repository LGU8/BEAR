# ml/lstm/predictor.py
from __future__ import annotations

import os
import json
import math
import traceback
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from django.db import connection
from django.utils import timezone

# 모델 로딩은 실패해도 서비스가 죽지 않도록 보호한다.
try:
    import torch
except Exception:
    torch = None  # type: ignore

try:
    import joblib
except Exception:
    joblib = None  # type: ignore


# =========================
# Config / Artifacts
# =========================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARTIFACTS_DIR = os.path.join(os.path.dirname(BASE_DIR), "artifacts")

CFG_PATH = os.path.join(ARTIFACTS_DIR, "lstm_config.json")
MODEL_PATH = os.path.join(ARTIFACTS_DIR, "lstm_final.pt")
SCALER_PATH = os.path.join(ARTIFACTS_DIR, "lstm_scaler.pkl")


@dataclass
class PredResult:
    ok: bool
    reason: str
    p_highrisk: float
    # 아래는 UI/디버그용 (없어도 되지만 있으면 좋음)
    p0: float = 0.0
    p2: float = 0.0
    detail: Optional[Dict[str, Any]] = None


# =========================
# Utilities
# =========================

def _ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


def _parse_ymd(s: str) -> date:
    return datetime.strptime(s, "%Y%m%d").date()


def _slot_rank(slot: str) -> int:
    s = (slot or "").upper()
    if s == "D":
        return 3
    if s == "L":
        return 2
    if s == "M":
        return 1
    return 0


def _pick_source_slot_DLM(cust_id: str, rgs_dt: str) -> Optional[Tuple[str, int]]:
    """
    같은 날짜(rgs_dt)에서 source slot 고르기: D > L > M
    + 함께 해당 slot의 seq도 뽑는다(가장 최근 seq로).
    """
    sql = """
        SELECT time_slot, MAX(seq) AS max_seq
        FROM CUS_FEEL_TH
        WHERE cust_id = %s AND rgs_dt = %s
        GROUP BY time_slot
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [cust_id, rgs_dt])
        rows = cursor.fetchall()

    best_slot = None
    best_seq = None
    best_rank = -1
    for time_slot, max_seq in rows:
        if not time_slot:
            continue
        rank = _slot_rank(str(time_slot))
        if rank > best_rank:
            best_rank = rank
            best_slot = str(time_slot).upper()
            best_seq = int(max_seq or 0)

    if best_slot is None or best_seq is None or best_seq <= 0:
        return None
    return best_slot, best_seq


def _target_from_source(source_date_ymd: str, source_slot: str) -> Tuple[str, str]:
    s = (source_slot or "").upper()
    if s == "M":
        return source_date_ymd, "L"
    if s == "L":
        return source_date_ymd, "D"
    # D -> next day M
    d = _parse_ymd(source_date_ymd)
    return _ymd(d + timedelta(days=1)), "M"


# =========================
# Gate: 최근 3일 매일 keyword 1개 이상
# =========================

def gate_has_keywords_3days(cust_id: str, asof_yyyymmdd: str) -> Tuple[bool, Dict[str, Any]]:
    """
    asof_yyyymmdd 포함 최근 3일(D-2, D-1, D) 각각 TS(키워드) 1개 이상 존재해야 True
    """
    d = _parse_ymd(asof_yyyymmdd)
    days = [_ymd(d - timedelta(days=2)), _ymd(d - timedelta(days=1)), _ymd(d)]
    missing = []

    sql = """
        SELECT rgs_dt, COUNT(*) AS cnt
        FROM CUS_FEEL_TS
        WHERE cust_id = %s AND rgs_dt IN (%s, %s, %s)
        GROUP BY rgs_dt
    """
    got = {}
    with connection.cursor() as cursor:
        cursor.execute(sql, [cust_id, days[0], days[1], days[2]])
        for rgs_dt, cnt in cursor.fetchall():
            got[str(rgs_dt)] = int(cnt or 0)

    for day in days:
        if got.get(day, 0) <= 0:
            missing.append(day)

    ok = (len(missing) == 0)
    detail = {
        "type": "gate_3days_keywords",
        "asof": asof_yyyymmdd,
        "days": days,
        "counts": got,
        "missing_days": missing,
    }
    return ok, detail


# =========================
# Feature extraction (간단/보수적)
# =========================
# ※ 너의 LSTM이 실제로 어떤 feature를 쓰는지(7개) 정확히 맞추려면,
#   기존 프로젝트에서 이미 쓰던 로직을 여기 블록에 그대로 붙여야 한다.
#   아래는 "서비스가 안 죽고 예측 저장까지 가게" 만드는 최소 버전이다.

def _fetch_last_n_feels(cust_id: str, end_yyyymmdd: str, n_days: int = 7) -> list[dict]:
    """
    end_yyyymmdd 기준 과거 n_days(포함) 동안의 TH 기록을 일단 모두 가져온다.
    (slot별로 여러개여도 여기서는 단순 집계/대표값으로 처리)
    """
    end_d = _parse_ymd(end_yyyymmdd)
    start_d = end_d - timedelta(days=n_days - 1)

    sql = """
        SELECT rgs_dt, time_slot, mood, energy, cluster_val
        FROM CUS_FEEL_TH
        WHERE cust_id = %s
          AND rgs_dt BETWEEN %s AND %s
        ORDER BY rgs_dt ASC
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [cust_id, _ymd(start_d), _ymd(end_d)])
        rows = cursor.fetchall()

    out = []
    for rgs_dt, time_slot, mood, energy, cluster_val in rows:
        out.append({
            "rgs_dt": str(rgs_dt),
            "time_slot": (str(time_slot).upper() if time_slot else None),
            "mood": str(mood) if mood else None,
            "energy": str(energy) if energy else None,
            "cluster_val": (int(cluster_val) if cluster_val is not None else None),
        })
    return out


def _simple_numeric(mood: Optional[str], energy: Optional[str]) -> Tuple[float, float]:
    """
    임시 매핑(최소 동작):
    - valence: pos=+1, neu=0, neg=-1
    - arousal: hig=+1, med/mid=0, low=-1
    """
    m = (mood or "").lower()
    e = (energy or "").lower()

    val = 0.0
    if m == "pos":
        val = 1.0
    elif m == "neg":
        val = -1.0

    aro = 0.0
    if e == "hig":
        aro = 1.0
    elif e == "low":
        aro = -1.0
    # med/mid -> 0.0
    return val, aro


def build_window_features(cust_id: str, asof_yyyymmdd: str, window: int = 7) -> Tuple[Optional[list[list[float]]], Dict[str, Any]]:
    """
    window=7일 시퀀스 형태로 feature를 만든다.
    여기서는 "하루 대표 slot"을 D>L>M 우선으로 뽑아 대표 valence/arousal로 구성한다.
    """
    feels = _fetch_last_n_feels(cust_id, asof_yyyymmdd, n_days=window)
    asof_d = _parse_ymd(asof_yyyymmdd)
    days = [_ymd(asof_d - timedelta(days=(window - 1 - i))) for i in range(window)]

    # day -> best record (D>L>M)
    day_best = {}
    for rec in feels:
        d = rec["rgs_dt"]
        slot = rec.get("time_slot") or ""
        rank = _slot_rank(slot)
        cur = day_best.get(d)
        if cur is None or rank > cur["rank"]:
            day_best[d] = {"rank": rank, "rec": rec}

    seq = []
    missing_days = []
    prev_val = 0.0
    prev_aro = 0.0

    for i, d in enumerate(days):
        best = day_best.get(d)
        if not best:
            # 결측이면 0으로 채움(모델 품질은 떨어지지만 파이프라인은 이어짐)
            missing_days.append(d)
            val, aro = 0.0, 0.0
            slot = "M"
        else:
            r = best["rec"]
            val, aro = _simple_numeric(r.get("mood"), r.get("energy"))
            slot = (r.get("time_slot") or "M").upper()

        # deltas
        dval = val - prev_val
        daro = aro - prev_aro
        prev_val, prev_aro = val, aro

        # time one-hot (M,L,D) 3개
        is_m = 1.0 if slot == "M" else 0.0
        is_l = 1.0 if slot == "L" else 0.0
        is_d = 1.0 if slot == "D" else 0.0

        # 총 7개 feature: valence, arousal, dval, daro, is_m, is_l, is_d
        seq.append([val, aro, dval, daro, is_m, is_l, is_d])

    detail = {
        "type": "window_features",
        "asof": asof_yyyymmdd,
        "days": days,
        "missing_days": missing_days,
        "window": window,
    }
    return seq, detail


# =========================
# Model inference
# =========================

class _ModelBundle:
    def __init__(self):
        self.loaded = False
        self.cfg = None
        self.model = None
        self.scaler = None

    def load(self):
        if self.loaded:
            return

        # config
        cfg = None
        if os.path.exists(CFG_PATH):
            with open(CFG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        else:
            cfg = {"window": 7}

        self.cfg = cfg

        # scaler
        if joblib is not None and os.path.exists(SCALER_PATH):
            self.scaler = joblib.load(SCALER_PATH)
        else:
            self.scaler = None

        # model
        if torch is not None and os.path.exists(MODEL_PATH):
            # 프로젝트에 따라 torch.load 방식이 다를 수 있음
            self.model = torch.load(MODEL_PATH, map_location="cpu")
            try:
                self.model.eval()
            except Exception:
                pass
        else:
            self.model = None

        self.loaded = True


_BUNDLE = _ModelBundle()


def predict_negative_risk(
    cust_id: str,
    source_date: str,
    source_slot: str,
    source_seq: int,
) -> PredResult:
    """
    source_date/slot/seq를 받아서 다음 target 슬롯의 "HighRisk 확률"을 만든다.
    - 여기선 확률을 0~1로 뽑아 반환.
    - 실제 p0/p2가 있다면 같이 반환.
    """

    try:
        _BUNDLE.load()
    except Exception as e:
        return PredResult(
            ok=False,
            reason=f"model_load_failed: {e}",
            p_highrisk=0.0,
            detail={"trace": traceback.format_exc()},
        )

    window = 7
    try:
        if _BUNDLE.cfg and "window" in _BUNDLE.cfg:
            window = int(_BUNDLE.cfg.get("window") or 7)
    except Exception:
        window = 7

    # Gate: source_date 기준 최근 3일 keyword 존재
    gate_ok, gate_detail = gate_has_keywords_3days(cust_id, asof_yyyymmdd=source_date)
    if not gate_ok:
        return PredResult(
            ok=False,
            reason="gate_failed_no_keywords_3days",
            p_highrisk=0.0,
            detail=gate_detail,
        )

    # build features
    seq, feat_detail = build_window_features(cust_id, asof_yyyymmdd=source_date, window=window)
    if seq is None:
        return PredResult(
            ok=False,
            reason="feature_build_failed",
            p_highrisk=0.0,
            detail=feat_detail,
        )

    # 모델이 없으면 최소한의 fallback(서비스 보존)
    if _BUNDLE.model is None or torch is None:
        # 간단 휴리스틱: neg가 많으면 높게(정확도 목적 X, 파이프라인 검증용)
        neg_cnt = 0
        for row in seq:
            val = row[0]  # valence
            if val < 0:
                neg_cnt += 1
        p = min(0.99, max(0.01, neg_cnt / float(len(seq) or 1)))
        return PredResult(
            ok=True,
            reason="fallback_no_model",
            p_highrisk=float(p),
            p0=float(p) * 0.5,
            p2=float(p) * 0.5,
            detail={"gate": gate_detail, "feat": feat_detail},
        )

    # numpy 형태로 스케일링 -> torch tensor
    try:
        import numpy as np
        arr = np.array(seq, dtype=float)  # (window, 7)

        if _BUNDLE.scaler is not None:
            # scaler가 (N,7) 형태를 기대한다고 가정
            arr = _BUNDLE.scaler.transform(arr)

        x = torch.tensor(arr, dtype=torch.float32).unsqueeze(0)  # (1, window, 7)

        # 모델 출력 형식이 프로젝트마다 다를 수 있어 방어적으로 처리
        with torch.no_grad():
            y = _BUNDLE.model(x)

        # y가 (1,3) logits 라고 가정(0/1/2)
        # HighRisk = p0+p2 (너가 쓰던 기준을 그대로)
        if isinstance(y, (list, tuple)):
            y = y[0]

        # logits -> softmax
        if hasattr(torch, "softmax"):
            probs = torch.softmax(y, dim=-1).cpu().numpy().reshape(-1).tolist()
        else:
            # softmax 구현
            yy = y.cpu().numpy().reshape(-1)
            ex = [math.exp(float(v)) for v in yy]
            s = sum(ex) or 1.0
            probs = [float(v)/s for v in ex]

        # 안전 처리
        while len(probs) < 3:
            probs.append(0.0)

        p0 = float(probs[0])
        p2 = float(probs[2])
        p_high = p0 + p2

        return PredResult(
            ok=True,
            reason="ok",
            p_highrisk=p_high,
            p0=p0,
            p2=p2,
            detail={"gate": gate_detail, "feat": feat_detail, "probs": probs},
        )

    except Exception as e:
        return PredResult(
            ok=False,
            reason=f"infer_failed: {e}",
            p_highrisk=0.0,
            detail={"trace": traceback.format_exc(), "gate": gate_detail, "feat": feat_detail},
        )
