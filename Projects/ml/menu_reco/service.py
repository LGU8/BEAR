# ml/menu_reco/service.py
from __future__ import annotations

from functools import lru_cache
from typing import Dict, Any, Optional, List, Tuple

import json
import uuid
import traceback
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from django.conf import settings
from django.db import connection

from ml.menu_reco.common.config import AppConfig, Phase1Config, Phase3Config
from ml.menu_reco.common.ssot import macro_ratio_from_grams_to_kcal, normalize_macro
from ml.menu_reco.domain.phase1.rule_based import recommend_phase1_2plus1

from ml.menu_reco.domain.phase2.clustering import attach_cluster_info
from ml.menu_reco.domain.phase3.reranker import (
    build_stable_food_ctx_from_logs,
    compute_p_stable_cluster,
    attach_p_stable_cluster,
    combine_score_phase3,
)

from ml.menu_reco import db_repo


# -----------------------------
# Robust I/O (service.py 내부)
# -----------------------------
def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _read_parquet_robust(path: Path) -> pd.DataFrame:
    """
    Parquet 로딩이 pyarrow에서 깨지는 케이스(OSError: Repetition level histogram size mismatch)를
    최대한 우회하기 위한 robust loader.

    시도 순서:
    1) pandas.read_parquet(engine="pyarrow")
    2) pyarrow.parquet.read_table -> to_pandas
    3) pandas.read_parquet(engine="fastparquet") (설치돼 있으면)
    """
    try:
        return pd.read_parquet(path, engine="pyarrow")
    except Exception as e1:
        try:
            import pyarrow.parquet as pq

            table = pq.read_table(str(path), use_threads=False)
            return table.to_pandas()
        except Exception as e2:
            try:
                return pd.read_parquet(path, engine="fastparquet")
            except Exception as e3:
                raise OSError(
                    f"[ARTIFACT_READ_FAIL]\n"
                    f"- path: {path}\n"
                    f"- pyarrow read_parquet failed: {type(e1).__name__}: {e1}\n"
                    f"- pyarrow read_table failed: {type(e2).__name__}: {e2}\n"
                    f"- fastparquet fallback failed: {type(e3).__name__}: {e3}\n\n"
                    f"해결 가이드:\n"
                    f"1) fastparquet 설치 후 재시도: pip install fastparquet\n"
                    f"2) pyarrow 버전 교체(업/다운그레이드) 또는\n"
                    f"3) artifacts(phase1/phase2) parquet 재생성\n"
                )


def _load_phase1_artifacts_robust(artifacts_dir: Path) -> Dict[str, Any]:
    base = artifacts_dir / "phase1"
    return {
        "food_stats": _read_parquet_robust(base / "food_stats.parquet"),
        "user_pref": _read_parquet_robust(base / "user_pref.parquet"),
        "ctx_food_all": _read_parquet_robust(base / "ctx_food_all.parquet"),
        "unobserved_pool": _read_parquet_robust(base / "unobserved_pool.parquet"),
        # NOTE: rule_based.py에서는 artifacts["bad_foods_set"] 키를 기대하므로 이름 고정
        "bad_foods_set": set(_load_json(base / "bad_foods.json")),
        "config": _load_json(base / "config.json"),
    }


def _load_phase2_artifacts_robust(artifacts_dir: Path) -> Dict[str, Any]:
    base = artifacts_dir / "phase2"
    return {
        "clustered": _read_parquet_robust(base / "clustered.parquet"),
        "cluster_meta": _read_parquet_robust(base / "cluster_meta.parquet"),
    }


def _try_load_phase3_logs(artifacts_dir: Path) -> Optional[pd.DataFrame]:
    """
    Phase3는 원래 logs(DataFrame)가 필요함.
    있으면 artifacts/phase3/logs.parquet에서 읽고,
    없으면 None 반환.
    """
    p = artifacts_dir / "phase3" / "logs.parquet"
    if p.exists():
        return _read_parquet_robust(p)
    return None


# -----------------------------
# Artifacts cache (fingerprint 기반)
# -----------------------------
def _artifacts_fingerprint(artifacts_dir: Path) -> str:
    """
    artifacts 폴더 내 주요 파일들의 최신 수정시각을 fingerprint로 만든다.
    - 파일이 바뀌면 fingerprint가 바뀌고, 캐시가 자동 무효화됨.
    """
    targets = [
        artifacts_dir / "phase1" / "food_stats.parquet",
        artifacts_dir / "phase1" / "user_pref.parquet",
        artifacts_dir / "phase1" / "ctx_food_all.parquet",
        artifacts_dir / "phase1" / "unobserved_pool.parquet",
        artifacts_dir / "phase1" / "bad_foods.json",
        artifacts_dir / "phase1" / "config.json",
        artifacts_dir / "phase2" / "clustered.parquet",
        artifacts_dir / "phase2" / "cluster_meta.parquet",
        artifacts_dir / "phase3" / "logs.parquet",
    ]
    mtimes: List[str] = []
    for p in targets:
        try:
            mtimes.append(str(int(p.stat().st_mtime)) if p.exists() else "0")
        except Exception:
            mtimes.append("0")
    return "|".join(mtimes)


@lru_cache(maxsize=4)
def _load_artifacts_cached_by_fp(
    fp: str,
) -> Tuple[Dict[str, Any], Dict[str, Any], Optional[pd.DataFrame]]:
    """
    fp(=fingerprint)가 바뀌면 자동으로 artifacts를 다시 로드한다.
    """
    cfg = AppConfig()
    base_dir = Path(settings.BASE_DIR)
    artifacts_dir = cfg.resolve_artifacts_dir(base_dir)

    phase1 = _load_phase1_artifacts_robust(artifacts_dir)
    phase2 = _load_phase2_artifacts_robust(artifacts_dir)
    logs = _try_load_phase3_logs(artifacts_dir)

    phase1, phase2, logs = _normalize_artifacts_labels_inplace(phase1, phase2, logs)
    return phase1, phase2, logs


def _load_artifacts_cached() -> Tuple[Dict[str, Any], Dict[str, Any], Optional[pd.DataFrame]]:
    """
    ✅ 외부 호출부는 그대로(_load_artifacts_cached()) 유지
    내부적으로 fingerprint 기반 캐시로 교체
    """
    cfg = AppConfig()
    base_dir = Path(settings.BASE_DIR)
    artifacts_dir = cfg.resolve_artifacts_dir(base_dir)

    fp = _artifacts_fingerprint(artifacts_dir)
    return _load_artifacts_cached_by_fp(fp)


# -----------------------------
# DB advisory lock (MySQL GET_LOCK)
# -----------------------------
def _acquire_mysql_lock(lock_name: str, timeout_sec: int = 2) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT GET_LOCK(%s, %s)", [lock_name, int(timeout_sec)])
        row = cursor.fetchone()
    return bool(row and row[0] == 1)


def _release_mysql_lock(lock_name: str):
    with connection.cursor() as cursor:
        cursor.execute("SELECT RELEASE_LOCK(%s)", [lock_name])


# -----------------------------
# Small helpers
# -----------------------------
def _remaining_meals(rec_time_slot: str) -> int:
    slot = str(rec_time_slot).upper()
    return {"M": 3, "L": 2, "D": 1}.get(slot, 3)


def _map_phase1_cfg(phase1_artifacts: Dict[str, Any]) -> Phase1Config:
    cfg_dict = phase1_artifacts.get("config")
    if isinstance(cfg_dict, dict):
        return Phase1Config(**cfg_dict)
    return Phase1Config()


def _normalize_ctx_labels(mood: str, energy: str) -> Tuple[str, str]:
    """
    입력(pos/neu/neg, low/med/hig 등) -> artifacts 라벨(Pos/Neu/Neg, Low/Med/High)로 정규화
    """
    m = str(mood).strip().lower()
    e = str(energy).strip().lower()

    mood_map = {
        "pos": "Pos",
        "positive": "Pos",
        "neu": "Neu",
        "neutral": "Neu",
        "neg": "Neg",
        "negative": "Neg",
    }

    energy_map = {
        "low": "Low",
        "med": "Med",
        "mid": "Med",
        "high": "High",
        "hig": "High",
    }

    return mood_map.get(m, mood), energy_map.get(e, energy)


def _norm_mood_val(x: Any) -> str:
    s = str(x).strip().lower()
    if s in ("pos", "positive"):
        return "pos"
    if s in ("neu", "neutral"):
        return "neu"
    if s in ("neg", "negative"):
        return "neg"
    return s


def _norm_energy_val(x: Any) -> str:
    s = str(x).strip().lower()
    if s in ("low",):
        return "low"
    if s in ("med", "mid"):
        return "med"
    if s in ("high", "hig"):
        return "hig"
    return s


def _normalize_artifacts_labels_inplace(
    phase1: Dict[str, Any],
    phase2: Dict[str, Any],
    logs: Optional[pd.DataFrame],
) -> Tuple[Dict[str, Any], Dict[str, Any], Optional[pd.DataFrame]]:
    # phase1 ctx_food_all
    ctx = phase1.get("ctx_food_all")
    if isinstance(ctx, pd.DataFrame) and not ctx.empty:
        if "Mood" in ctx.columns:
            ctx["Mood"] = ctx["Mood"].map(_norm_mood_val)
        if "Energy" in ctx.columns:
            ctx["Energy"] = ctx["Energy"].map(_norm_energy_val)
        phase1["ctx_food_all"] = ctx

    # phase2 clustered / cluster_meta
    clustered = phase2.get("clustered")
    if isinstance(clustered, pd.DataFrame) and not clustered.empty:
        if "Mood" in clustered.columns:
            clustered["Mood"] = clustered["Mood"].map(_norm_mood_val)
        if "Energy" in clustered.columns:
            clustered["Energy"] = clustered["Energy"].map(_norm_energy_val)
        phase2["clustered"] = clustered

    meta = phase2.get("cluster_meta")
    if isinstance(meta, pd.DataFrame) and not meta.empty:
        if "Mood" in meta.columns:
            meta["Mood"] = meta["Mood"].map(_norm_mood_val)
        if "Energy" in meta.columns:
            meta["Energy"] = meta["Energy"].map(_norm_energy_val)
        phase2["cluster_meta"] = meta

    # phase3 logs
    if isinstance(logs, pd.DataFrame) and not logs.empty:
        if "Mood" in logs.columns:
            logs["Mood"] = logs["Mood"].map(_norm_mood_val)
        if "Energy" in logs.columns:
            logs["Energy"] = logs["Energy"].map(_norm_energy_val)
        return phase1, phase2, logs

    return phase1, phase2, logs


def _build_user_vec_from_db(
    *,
    profile: Dict[str, Any],
    recent_macro: Dict[str, float],
    phase1_cfg: Phase1Config,
) -> np.ndarray:
    # 1) 프로필 Ratio_* 우선
    rc = profile.get("Ratio_carb")
    rp = profile.get("Ratio_protein")
    rf = profile.get("Ratio_fat")

    if rc is not None and rp is not None and rf is not None:
        vec = normalize_macro(float(rc), float(rp), float(rf))
        return np.array(vec, dtype=float)

    # 2) 최근 섭취 grams → kcal ratio
    c_g = float(recent_macro.get("sum_carb_g", 0) or 0)
    p_g = float(recent_macro.get("sum_protein_g", 0) or 0)
    f_g = float(recent_macro.get("sum_fat_g", 0) or 0)
    vec = macro_ratio_from_grams_to_kcal(c_g, p_g, f_g)

    # 3) 모두 0이면 HEALTH_532 fallback
    if np.allclose(vec, np.array([1 / 3, 1 / 3, 1 / 3], dtype=float), atol=1e-6):
        vec = np.array(phase1_cfg.HEALTH_532, dtype=float)

    return np.array(vec, dtype=float)


def _to_rec_code(rt: str) -> str:
    s = str(rt)
    if "선호" in s or "Preference" in s:
        return "P"
    if "건강" in s or "Health" in s:
        return "H"
    if "탐색" in s or "Exploration" in s:
        return "E"
    return "P"


def _fallback_logs_from_ctx(ctx_food_all: pd.DataFrame) -> pd.DataFrame:
    """
    phase3 logs.parquet이 없을 때 임시 logs를 만들기 위한 fallback.
    - 엄밀한 y_final 로그가 아니므로 p_stable은 "근사"임.
    """
    df = ctx_food_all[["Mood", "Energy", "Food", "mean_y_ctx"]].copy()
    df["y_final"] = (df["mean_y_ctx"].fillna(0) > 0).astype(int)
    return df[["Mood", "Energy", "Food", "y_final"]]


def _ensure_phase1_debug_cols(
    rec_df: pd.DataFrame,
    *,
    mood_req: str,
    energy_req: str,
) -> pd.DataFrame:
    """
    Phase1이 ERROR로 떨어져도(컬럼 최소 구성) 후속 단계/디버그가 터지지 않도록 컬럼을 보강
    """
    out = rec_df.copy()

    if "Mood_req" not in out.columns:
        out["Mood_req"] = mood_req
    if "Energy_req" not in out.columns:
        out["Energy_req"] = energy_req
    if "Pool_used" not in out.columns:
        out["Pool_used"] = "N/A"
    if "Explanation" not in out.columns:
        out["Explanation"] = ""

    if "Food" not in out.columns:
        out["Food"] = "N/A"
    if "rec_type" not in out.columns:
        out["rec_type"] = "ERROR"

    return out


# -----------------------------
# Main service
# -----------------------------
def recommend_and_commit(
    *,
    cust_id: str,
    mood: str,          # pos/neu/neg
    energy: str,        # low/med/hig
    rgs_dt: str,        # YYYYMMDD
    rec_time_slot: str, # M/L/D
    current_food: Optional[str] = None,
    recent_foods: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    (1) DB 기반 입력(cust_id, mood/energy, 날짜/끼니)을 받아
    (2) Phase1 추천(+override) 후
    (3) Phase2 cluster attach + Phase3 rerank까지 수행하고
    (4) 추천 결과(P/H/E)를 MENU_RECOM_TH에 upsert
    (5) DataFrame 반환
    """
    run_id = uuid.uuid4().hex
    lock_name = f"reco:{cust_id}:{rgs_dt}:{str(rec_time_slot).upper()}"

    print(
        "[RECO][START]",
        "run_id=", run_id,
        "cust_id=", cust_id,
        "rgs_dt=", rgs_dt,
        "slot=", str(rec_time_slot).upper(),
        "mood=", mood,
        "energy=", energy,
        flush=True,
    )

    got_lock = False
    try:
        got_lock = _acquire_mysql_lock(lock_name, timeout_sec=2)
        if not got_lock:
            print(
                "[RECO][SKIP_LOCK_TIMEOUT]",
                "run_id=", run_id,
                "lock=", lock_name,
                flush=True,
            )
            return pd.DataFrame()

        phase1_artifacts, phase2_artifacts, logs_df = _load_artifacts_cached()
        phase1_cfg = _map_phase1_cfg(phase1_artifacts)

        mood_key = _norm_mood_val(mood)      # pos/neu/neg
        energy_key = _norm_energy_val(energy)  # low/med/hig

        # 1) profile
        profile = db_repo.get_profile(cust_id)
        if not profile:
            raise ValueError(f"CUS_PROFILE_TS not found for cust_id={cust_id}")

        # 2) eaten today + remaining
        eaten = db_repo.get_day_eaten_sum(cust_id, rgs_dt)
        recommended = float(profile.get("Recommended_calories") or 0)
        eaten_kcal = float(eaten.get("sum_kcal") or 0)
        remaining = max(0.0, recommended - eaten_kcal)

        # 3) per_meal_target
        rm = _remaining_meals(rec_time_slot)
        per_meal_target = remaining / float(rm) if rm > 0 else remaining

        # 4) purpose mapping (DB 1/2/3 -> model 0/1/2)
        purpose_db = int(profile.get("purpose") or 2)  # default Main(2)
        purpose_model = max(0, min(2, purpose_db - 1))

        # 5) user_vec
        recent_macro = db_repo.get_recent_macro_sum(cust_id, days=7)
        user_vec = _build_user_vec_from_db(
            profile=profile, recent_macro=recent_macro, phase1_cfg=phase1_cfg
        )

        # 6) Phase1 추천 (override)
        exclude = [current_food] if current_food else None
        rec_df = recommend_phase1_2plus1(
            artifacts=phase1_artifacts,
            product_name=str(cust_id),   # override 모드에서는 lookup 안 함
            mood=mood_key,
            energy=energy_key,
            cfg=phase1_cfg,
            exclude_foods=exclude,
            history_foods=recent_foods,
            user_vec_override=user_vec,
            per_meal_target_override=per_meal_target,
            purpose_override=purpose_model,
        )

        if rec_df is None or rec_df.empty:
            print("[RECO][EMPTY_PHASE1]", "run_id=", run_id, flush=True)
            return rec_df if rec_df is not None else pd.DataFrame()

        # Phase1 결과 컬럼 보강
        rec_df = _ensure_phase1_debug_cols(rec_df, mood_req=mood_key, energy_req=energy_key)

        # 7) Phase2 attach cluster info
        clustered = phase2_artifacts.get("clustered")
        cluster_meta = phase2_artifacts.get("cluster_meta")
        rec_df = attach_cluster_info(rec_df, clustered=clustered, cluster_meta=cluster_meta)

        # 8) Phase3 rerank
        if logs_df is None or logs_df.empty:
            logs_df = _fallback_logs_from_ctx(phase1_artifacts["ctx_food_all"])
            rec_df["phase3_logs_source"] = "FALLBACK_FROM_CTX"
        else:
            rec_df["phase3_logs_source"] = "ARTIFACT_LOGS"

        stable_food_ctx = build_stable_food_ctx_from_logs(logs_df)

        if clustered is None or clustered.empty:
            rec_df["p_stable_cluster"] = 0.5
        else:
            clustered_rows = clustered[["Mood", "Energy", "Food", "cluster_id"]].drop_duplicates()
            phase3_cfg = Phase3Config()
            p_stable_df = compute_p_stable_cluster(
                stable_food_ctx, clustered_rows, alpha=phase3_cfg.alpha
            )
            rec_df = attach_p_stable_cluster(rec_df, p_stable_df, default_p=0.5)

        # score_phase1 컬럼 통일
        if "score_phase1" in rec_df.columns:
            s_phase1 = pd.to_numeric(rec_df["score_phase1"], errors="coerce")
        else:
            s_phase1 = pd.Series([np.nan] * len(rec_df), index=rec_df.index, dtype="float64")
        rec_df["score_phase1"] = s_phase1.fillna(-9999.0)

        # rec_type별 phase3 weight map 적용
        def _map_rt(rt: str) -> str:
            s = str(rt)
            if "선호형" in s or s.lower().startswith("pref"):
                return "pref_cluster"
            if "건강형" in s or "health" in s.lower():
                return "healthy_532"
            if "탐색형" in s or "explore" in s.lower():
                return "explore_new"
            return "pref_cluster"

        phase3_cfg = Phase3Config()
        rec_df["rec_type_phase3"] = rec_df["rec_type"].apply(_map_rt)
        rec_df["score_phase3"] = rec_df.apply(
            lambda r: combine_score_phase3(
                base_score=r["score_phase1"],
                p_stable_cluster=r.get("p_stable_cluster", 0.5),
                rec_type_phase3=r.get("rec_type_phase3", "pref_cluster"),
                cfg=phase3_cfg,
            ),
            axis=1,
        )
        rec_df = rec_df.sort_values("score_phase3", ascending=False).reset_index(drop=True)

        # 9) Food -> food_id 매핑
        foods = rec_df["Food"].astype(str).tolist() if "Food" in rec_df.columns else []
        mapping = db_repo.map_food_names_to_ids(foods)

        # 10) MENU_RECOM_TH upsert (P/H/E)
        rows_to_save: List[Tuple[str, str]] = []
        for _, r in rec_df.iterrows():
            food_name = str(r.get("Food"))
            food_id = mapping.get(food_name)
            if not food_id:
                continue
            rows_to_save.append((_to_rec_code(r.get("rec_type")), str(food_id)))

        uniq: Dict[str, str] = {}
        for rt, fid in rows_to_save:
            if rt not in uniq:
                uniq[rt] = fid

        final_rows = [(k, v) for k, v in uniq.items()]

        # ✅ 저장 직전 로그(의미 있는 BEFORE_SAVE)
        print(
            "[RECO][BEFORE_SAVE]",
            "run_id=", run_id,
            "final_rows_len=", len(final_rows),
            "final_rows=", final_rows,
            flush=True,
        )

        if final_rows:
            db_repo.upsert_menu_recom_rows(
                cust_id=str(cust_id),
                rgs_dt=str(rgs_dt),
                rec_time_slot=str(rec_time_slot).upper(),
                rows=final_rows,
            )

        print(
            "[RECO][SUCCESS]",
            "run_id=", run_id,
            "saved=", bool(final_rows),
            flush=True,
        )

        # 11) 응답 DF 디버그 컬럼 부착
        rec_df["food_id"] = rec_df["Food"].astype(str).map(mapping)
        rec_df["rgs_dt"] = str(rgs_dt)
        rec_df["rec_time_slot"] = str(rec_time_slot).upper()
        rec_df["per_meal_target"] = float(per_meal_target)
        rec_df["remaining_calories"] = float(remaining)
        rec_df["purpose_db"] = int(purpose_db)
        rec_df["purpose_model"] = int(purpose_model)
        rec_df["reco_run_id"] = run_id

        return rec_df

    except Exception as e:
        print(
            "[RECO][FAIL]",
            "run_id=", run_id,
            "cust_id=", cust_id,
            "rgs_dt=", rgs_dt,
            "slot=", str(rec_time_slot).upper(),
            "err=", repr(e),
            flush=True,
        )
        traceback.print_exc()
        return pd.DataFrame()

    finally:
        if got_lock:
            _release_mysql_lock(lock_name)