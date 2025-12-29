from __future__ import annotations
from typing import Dict, Any, Optional, List, Tuple, Union
import numpy as np
import pandas as pd

from ml.menu_reco.common.config import Phase1Config, Phase3Config
from ml.menu_reco.domain.phase1.rule_based import recommend_phase1_2plus1
from ml.menu_reco.domain.phase2.clustering import attach_cluster_info

def _map_phase1_rec_type_to_phase3(rec_type: str) -> str:
    rt = str(rec_type)
    if "선호형" in rt or rt.lower().startswith("pref"):
        return "pref_cluster"
    if "건강형" in rt or "health" in rt.lower():
        return "healthy_532"
    if "탐색형" in rt or "explore" in rt.lower():
        return "explore_new"
    return "pref_cluster"

def build_stable_food_ctx_from_logs(logs: pd.DataFrame) -> pd.DataFrame:
    need_cols = ["Mood","Energy","Food","y_final"]
    miss = [c for c in need_cols if c not in logs.columns]
    if miss:
        raise ValueError(f"logs missing columns: {miss}")

    stable_food_ctx = (
        logs[need_cols]
        .groupby(["Mood","Energy","Food"], as_index=False)["y_final"]
        .max()
        .rename(columns={"y_final":"y_final"})
    )
    stable_food_ctx["y_final"] = stable_food_ctx["y_final"].fillna(0).astype(int)
    return stable_food_ctx

def compute_p_stable_cluster(
    stable_food_ctx: pd.DataFrame,
    clustered_rows: pd.DataFrame,
    alpha: float = 1.0
) -> pd.DataFrame:
    # clustered_rows: (Mood, Energy, Food, cluster_id)
    if stable_food_ctx.empty or clustered_rows.empty:
        return pd.DataFrame(columns=["Mood","Energy","cluster_id","n_rows","n_stable","p_stable_cluster"])

    join = clustered_rows.merge(stable_food_ctx, on=["Mood","Energy","Food"], how="left")
    join["y_final"] = join["y_final"].fillna(0).astype(int)

    g = join.groupby(["Mood","Energy","cluster_id"], as_index=False).agg(
        n_rows=("Food","count"),
        n_stable=("y_final","sum")
    )
    g["p_stable_cluster"] = (g["n_stable"] + float(alpha)) / (g["n_rows"] + 2.0*float(alpha))
    return g

def attach_p_stable_cluster(rec_df: pd.DataFrame, p_stable_df: pd.DataFrame, default_p: float = 0.5) -> pd.DataFrame:
    out = rec_df.copy()
    if p_stable_df is None or p_stable_df.empty:
        out["p_stable_cluster"] = default_p
        return out

    tmp = p_stable_df.rename(columns={"Mood":"Mood_used","Energy":"Energy_used"})
    out = out.merge(
        tmp[["Mood_used","Energy_used","cluster_id","p_stable_cluster"]],
        on=["Mood_used","Energy_used","cluster_id"],
        how="left"
    )
    out["p_stable_cluster"] = out["p_stable_cluster"].fillna(default_p)
    return out

def combine_score_phase3(base_score: float, p_stable_cluster: float, rec_type_phase3: str, cfg: Phase3Config) -> float:
    w = cfg.w_map.get(str(rec_type_phase3), 0.5)
    return float(base_score) + float(w) * (float(p_stable_cluster) - 0.5)

def _resolve_phase1_cfg(
    phase1_cfg: Optional[Phase1Config],
    phase1_artifacts: Dict[str, Any],
) -> Phase1Config:
    """
    Option B(장기 운영형): cfg를 외부 주입하지 않으면 artifacts의 config.json(SSOT)로부터 복원
    """
    if phase1_cfg is not None:
        return phase1_cfg

    cfg_dict = phase1_artifacts.get("config")
    if not isinstance(cfg_dict, dict):
        raise ValueError("[ERROR] phase1_cfg is None and phase1_artifacts['config'] is missing or not dict")

    # Phase1Config의 필드명과 config.json 키가 일치해야 함
    return Phase1Config(**cfg_dict)

def recommend_phase3_v1(
    phase1_artifacts: Dict[str, Any],
    phase2_artifacts: Dict[str, Any],
    logs: pd.DataFrame,
    product_name: str,
    mood: str,
    energy: str,
    phase1_cfg: Optional[Phase1Config] = None,
    phase3_cfg: Optional[Phase3Config] = None,
    current_food: Optional[str] = None,
    recent_foods: Optional[List[str]] = None,
    return_debug: bool = False,

    # ✅ (Option A) Django/DB 운영용 override 추가
    user_vec_override: Optional[np.ndarray] = None,
    per_meal_target_override: Optional[float] = None,
    purpose_override: Optional[int] = None,
) -> Union[pd.DataFrame, Tuple[pd.DataFrame, pd.DataFrame]]:
    phase3_cfg = phase3_cfg or Phase3Config()

    # Phase1 cfg 확정(SSOT)
    phase1_cfg = _resolve_phase1_cfg(phase1_cfg, phase1_artifacts)

    exclude = [current_food] if current_food else None

    # 1) Phase1 (✅ override 전달)
    rec_df = recommend_phase1_2plus1(
        artifacts=phase1_artifacts,
        product_name=product_name,
        mood=mood,
        energy=energy,
        cfg=phase1_cfg,
        exclude_foods=exclude,
        history_foods=recent_foods,

        user_vec_override=user_vec_override,
        per_meal_target_override=per_meal_target_override,
        purpose_override=purpose_override,
    )
    if rec_df.empty:
        return (rec_df, pd.DataFrame()) if return_debug else rec_df

    # --- 이하 Phase3 로직은 그대로 ---
    clustered = phase2_artifacts["clustered"]
    cluster_meta = phase2_artifacts["cluster_meta"]
    rec_df = attach_cluster_info(rec_df, clustered=clustered, cluster_meta=cluster_meta)

    stable_food_ctx = build_stable_food_ctx_from_logs(logs)
    clustered_rows = clustered[["Mood","Energy","Food","cluster_id"]].drop_duplicates()
    p_stable_df = compute_p_stable_cluster(stable_food_ctx, clustered_rows, alpha=phase3_cfg.alpha)

    rec_df = attach_p_stable_cluster(rec_df, p_stable_df, default_p=0.5)

    rec_df["rec_type_phase3"] = rec_df["rec_type"].apply(_map_phase1_rec_type_to_phase3)

    rec_df["score_phase1"] = pd.to_numeric(rec_df.get("score_phase1", np.nan), errors="coerce").fillna(-9999.0)

    rec_df["score_phase3"] = rec_df.apply(
        lambda r: combine_score_phase3(
            base_score=r["score_phase1"],
            p_stable_cluster=r["p_stable_cluster"],
            rec_type_phase3=r["rec_type_phase3"],
            cfg=phase3_cfg,
        ),
        axis=1
    )

    rec_df["final_message"] = rec_df.apply(
        lambda r: (
            f"{r.get('Explanation','')} | "
            f"cluster={r.get('cluster_label','N/A')} | "
            f"p_stable={float(r.get('p_stable_cluster',0.5)):.3f}"
        ),
        axis=1
    )

    rec_df = rec_df.sort_values("score_phase3", ascending=False).reset_index(drop=True)

    return (rec_df, p_stable_df) if return_debug else rec_df