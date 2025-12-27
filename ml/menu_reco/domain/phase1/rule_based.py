from __future__ import annotations
from typing import Dict, Tuple, Optional, Iterable, Set, Any  # ✅ Any 추가
import numpy as np
import pandas as pd

from ml.menu_reco.common.config import Phase1Config
from ml.menu_reco.common.constants import STABLE_CONTEXTS, UNSTABLE_CONTEXTS, RECOVERY_CONTEXTS
from ml.menu_reco.common.ssot import (
    to_numeric_safe, normalize_macro, macro_ratio_from_grams_to_kcal,
    l1_distance_batch, compute_calorie_penalty, compute_purpose_delta_penalty,
    apply_guardrails, diversity_unique_food
)

# ----------------------------
# Build artifacts (pure)
# ----------------------------
def build_food_stats(foods_raw: pd.DataFrame, logs: pd.DataFrame) -> pd.DataFrame:
    nut = (
        foods_raw.groupby("Food", as_index=False)
        .agg(
            Calories=("Calories", "mean"),
            food_carb_g=("Carbohydrates", "mean"),
            food_prot_g=("Protein", "mean"),
            food_fat_g=("Fat", "mean"),
        )
    )
    emo = (
        logs.groupby("Food", as_index=False)
        .agg(emotion_score=("y_final", "mean"), n_logs_total=("y_final", "size"))
    )
    fs = nut.merge(emo, on="Food", how="left")
    fs["emotion_score"] = fs["emotion_score"].fillna(0.0)
    fs["n_logs_total"] = fs["n_logs_total"].fillna(0).astype(int)

    ratios = fs.apply(
        lambda r: macro_ratio_from_grams_to_kcal(r["food_carb_g"], r["food_prot_g"], r["food_fat_g"]),
        axis=1, result_type="expand"
    )
    fs["macro_ratio_c"] = ratios[0]
    fs["macro_ratio_p"] = ratios[1]
    fs["macro_ratio_f"] = ratios[2]
    return fs

def build_user_pref(users_raw: pd.DataFrame, logs: pd.DataFrame, cfg: Phase1Config) -> pd.DataFrame:
    user_profile = users_raw[[
        "Product_Name","Gender","Height","Weight","Age","Activity_level","Purpose",
        "BMR","Calories_burned","Recommended_calories","offset",
        "Carbohydrates","Protein","Fat",
    ]].drop_duplicates("Product_Name").copy()

    user_profile = user_profile.rename(columns={
        "Carbohydrates": "slider_carb",
        "Protein":       "slider_protein",
        "Fat":           "slider_fat",
    })

    ulog = (
        logs.groupby("Product_Name", as_index=False)
        .agg(log_sum_c=("Carbohydrates","sum"), log_sum_p=("Protein","sum"), log_sum_f=("Fat","sum"))
    )

    up = user_profile.merge(ulog, on="Product_Name", how="inner")

    h_m = up["Height"] / 100.0
    up["BMI"] = up["Weight"] / (h_m**2 + 1e-9)

    pref = up.apply(lambda r: normalize_macro(r["log_sum_c"], r["log_sum_p"], r["log_sum_f"]),
                    axis=1, result_type="expand")
    up["pref_ratio_c"] = pref[0]
    up["pref_ratio_p"] = pref[1]
    up["pref_ratio_f"] = pref[2]

    srat = up.apply(lambda r: normalize_macro(r["slider_carb"], r["slider_protein"], r["slider_fat"]),
                    axis=1, result_type="expand")
    up["slider_ratio_c"] = srat[0]
    up["slider_ratio_p"] = srat[1]
    up["slider_ratio_f"] = srat[2]

    a = float(cfg.ALPHA_SLIDER)
    up["hybrid_ratio_c"] = a*up["slider_ratio_c"] + (1-a)*up["pref_ratio_c"]
    up["hybrid_ratio_p"] = a*up["slider_ratio_p"] + (1-a)*up["pref_ratio_p"]
    up["hybrid_ratio_f"] = a*up["slider_ratio_f"] + (1-a)*up["pref_ratio_f"]
    return up

def build_ctx_food_all(logs: pd.DataFrame, food_stats: pd.DataFrame) -> pd.DataFrame:
    agg = (
        logs.groupby(["Mood","Energy","Food"], as_index=False)
        .agg(n_logs_ctx=("y_final","size"), mean_y_ctx=("y_final","mean"))
    )
    df = agg.merge(food_stats, on="Food", how="left")
    return df

def split_bad_foods(ctx_food_all: pd.DataFrame) -> Set[str]:
    unstable_only = ctx_food_all[ctx_food_all.apply(lambda r: (r["Mood"], r["Energy"]) in UNSTABLE_CONTEXTS, axis=1)].copy()
    return set(unstable_only["Food"].dropna().astype(str).unique().tolist())

def build_unobserved_food_pool(foods_raw: pd.DataFrame, logs: pd.DataFrame) -> pd.DataFrame:
    foods_in_logs = set(logs["Food"].dropna().astype(str).unique().tolist())
    df = foods_raw.copy()
    df = df[~df["Food"].astype(str).isin(foods_in_logs)].copy()

    df = to_numeric_safe(df, ["Calories","Carbohydrates","Protein","Fat"])
    ratios = df.apply(
        lambda r: macro_ratio_from_grams_to_kcal(r["Carbohydrates"], r["Protein"], r["Fat"]),
        axis=1, result_type="expand"
    )
    df["macro_ratio_c"] = ratios[0]
    df["macro_ratio_p"] = ratios[1]
    df["macro_ratio_f"] = ratios[2]
    return df[["Food","Calories","macro_ratio_c","macro_ratio_p","macro_ratio_f"]].copy()

def build_phase1_artifacts(foods: pd.DataFrame, users: pd.DataFrame, logs: pd.DataFrame, cfg: Phase1Config) -> Dict[str, Any]:
    foods = to_numeric_safe(foods, ["Calories", "Carbohydrates", "Protein", "Fat"])
    users = to_numeric_safe(users, [
        "Height","Weight","Age","Activity_level","Purpose","BMR","Calories_burned",
        "Recommended_calories","offset","Carbohydrates","Protein","Fat"
    ])
    logs = to_numeric_safe(logs, ["Carbohydrates","Protein","Fat","y_final","Recommended_calories","offset"])

    food_stats = build_food_stats(foods, logs)
    user_pref  = build_user_pref(users, logs, cfg)
    ctx_food_all = build_ctx_food_all(logs, food_stats)
    bad_foods_set = split_bad_foods(ctx_food_all)
    unobserved_pool = build_unobserved_food_pool(foods, logs)

    return {
        "food_stats": food_stats,
        "user_pref": user_pref,
        "ctx_food_all": ctx_food_all,
        "bad_foods_set": bad_foods_set,
        "unobserved_pool": unobserved_pool,
    }

# ----------------------------
# Recommend (pure)
# ----------------------------
def _get_candidate_pool(mood: str, energy: str, ctx_food_all: pd.DataFrame) -> Tuple[pd.DataFrame, Tuple[str, str]]:
    key = (str(mood), str(energy))
    if key in STABLE_CONTEXTS:
        pool = ctx_food_all[(ctx_food_all["Mood"]==key[0]) & (ctx_food_all["Energy"]==key[1])].copy()
        return pool, key

    rec_parts = []
    for rm, re in RECOVERY_CONTEXTS:
        sub = ctx_food_all[(ctx_food_all["Mood"]==rm) & (ctx_food_all["Energy"]==re)].copy()
        rec_parts.append(sub)
    pool = pd.concat(rec_parts, ignore_index=True) if rec_parts else ctx_food_all.head(0).copy()
    return pool, ("RECOVERY", "POOL")

def _score_foods(pool: pd.DataFrame, user_vec_pref: np.ndarray, health_vec: np.ndarray, purpose: int, per_meal_target: float, cfg: Phase1Config,
                 w_pref: float, w_health: float) -> pd.DataFrame:
    df = pool.copy()
    macro_mat = df[["macro_ratio_c","macro_ratio_p","macro_ratio_f"]].to_numpy()
    d_pref = l1_distance_batch(macro_mat, user_vec_pref)
    d_health = l1_distance_batch(macro_mat, health_vec)

    base = -(w_pref*d_pref + w_health*d_health)
    ctx_bonus = cfg.W_CTX * df["mean_y_ctx"].fillna(0).to_numpy()
    global_bonus = cfg.W_GLOBAL * df["emotion_score"].fillna(0).to_numpy()

    cal_pen = df["Calories"].fillna(0).apply(
        lambda c: compute_calorie_penalty(c, per_meal_target, cfg.LAMBDA_CAL, cfg.CAL_SOFT_CLIP)
    ).to_numpy()
    pur_pen = df["Calories"].fillna(0).apply(
        lambda c: compute_purpose_delta_penalty(c, per_meal_target, purpose, cfg.DELTA, cfg.LAMBDA_PURPOSE)
    ).to_numpy()

    df["score_base"] = base
    df["score_final"] = base + ctx_bonus + global_bonus + cal_pen + pur_pen
    return df

def recommend_phase1_2plus1(
    artifacts: Dict[str, Any],
    product_name: str,
    mood: str,
    energy: str,
    cfg: Phase1Config,
    exclude_foods: Optional[Iterable[str]] = None,
    history_foods: Optional[Iterable[str]] = None,
    explore_weight_pref: float = 0.6,
    explore_weight_health: float = 0.4,

    # ✅ DB 주입용 override
    user_vec_override: Optional[np.ndarray] = None,          # shape (3,)
    per_meal_target_override: Optional[float] = None,        # remaining/remaining_meals
    purpose_override: Optional[int] = None,                  # 0/1/2
) -> pd.DataFrame:
    user_pref: pd.DataFrame = artifacts["user_pref"]
    ctx_food_all: pd.DataFrame = artifacts["ctx_food_all"]
    bad_foods: Set[str] = artifacts["bad_foods_set"]
    unobserved_pool: pd.DataFrame = artifacts["unobserved_pool"]

    pool, pool_used = _get_candidate_pool(mood, energy, ctx_food_all)

    # ✅ override가 있으면 user_pref lookup 없이 진행
    if user_vec_override is not None and per_meal_target_override is not None and purpose_override is not None:
        user_vec = np.array(user_vec_override, dtype=float)
        per_meal_target = float(per_meal_target_override)
        purpose = int(purpose_override)
    else:
        urow = user_pref[user_pref["Product_Name"] == product_name]
        if urow.empty:
            raise ValueError(f"Product_Name='{product_name}' not found.")
        urow = urow.iloc[0]

        user_vec = np.array([urow["hybrid_ratio_c"], urow["hybrid_ratio_p"], urow["hybrid_ratio_f"]], dtype=float)

        purpose = int(urow.get("Purpose", 1))
        rec_cal = urow.get("Recommended_calories", np.nan)
        per_meal_target = float(rec_cal)/3.0 if not pd.isna(rec_cal) else np.nan

    healthy_vec = np.array(cfg.HEALTH_532, dtype=float)

    exclude_set = set(map(str, exclude_foods)) if exclude_foods else set()
    hist_set = set(map(str, history_foods)) if history_foods else set()

    if "Food" in pool.columns:
        pool = pool[~pool["Food"].astype(str).isin(bad_foods)].copy()
        if exclude_set:
            pool = pool[~pool["Food"].astype(str).isin(exclude_set)].copy()
        if hist_set:
            pool = pool[~pool["Food"].astype(str).isin(hist_set)].copy()

    pool = apply_guardrails(
        pool,
        fat_ratio_cap=cfg.FAT_RATIO_CAP,
        protein_min_g=cfg.PROTEIN_MIN_G,
        use_keyword_blacklist=cfg.USE_KEYWORD_BLACKLIST,
        keyword_blacklist=cfg.KEYWORD_BLACKLIST
    )

    if pool.empty:
        return pd.DataFrame([{
            "rec_type": "ERROR",
            "Food": "N/A",
            "Explanation": f"No candidates. pool_used={pool_used}"
        }])

    # pref/health scoring
    scored_pref = _score_foods(pool, user_vec, healthy_vec, purpose, per_meal_target, cfg, w_pref=cfg.W_PREF, w_health=0.0)\
        .sort_values("score_final", ascending=False)

    scored_health = _score_foods(pool, user_vec, healthy_vec, purpose, per_meal_target, cfg, w_pref=0.0, w_health=cfg.W_HEALTH)\
        .sort_values("score_final", ascending=False)

    used_foods: Set[str] = set()
    top_pref = diversity_unique_food(scored_pref, k=1, used=used_foods)
    used_foods.update(top_pref["Food"].astype(str).tolist())

    scored_health2 = scored_health[~scored_health["Food"].astype(str).isin(used_foods)].copy()
    top_health = diversity_unique_food(scored_health2, k=1, used=used_foods)
    used_foods.update(top_health["Food"].astype(str).tolist())

    # exploration
    explore_row = None
    ex = unobserved_pool.copy()
    if "Food" in ex.columns:
        ex = ex[~ex["Food"].astype(str).isin(used_foods | exclude_set | hist_set)].copy()

    wp, wh = float(explore_weight_pref), float(explore_weight_health)
    s = (wp + wh) if (wp + wh) > 1e-12 else 1.0
    wp, wh = wp/s, wh/s
    target_vec = wp*user_vec + wh*healthy_vec

    if not ex.empty:
        mat = ex[["macro_ratio_c","macro_ratio_p","macro_ratio_f"]].to_numpy()
        d = l1_distance_batch(mat, target_vec)
        base = -d
        cal_pen = ex["Calories"].fillna(0).apply(lambda c: compute_calorie_penalty(c, per_meal_target, cfg.LAMBDA_CAL, cfg.CAL_SOFT_CLIP)).to_numpy()
        pur_pen = ex["Calories"].fillna(0).apply(lambda c: compute_purpose_delta_penalty(c, per_meal_target, purpose, cfg.DELTA, cfg.LAMBDA_PURPOSE)).to_numpy()
        ex["score_final"] = base + cal_pen + pur_pen
        ex = ex.sort_values("score_final", ascending=False)
        explore_row = ex.iloc[0].to_dict()

    def _pack(df_one: pd.DataFrame, rec_type: str, explanation: str) -> Dict:
        if df_one is None or df_one.empty:
            return {"rec_type": rec_type, "Food": "N/A", "Explanation": explanation}
        r = df_one.iloc[0].to_dict()
        r["rec_type"] = rec_type
        r["Explanation"] = explanation
        r["Mood_req"] = str(mood)
        r["Energy_req"] = str(energy)
        r["Pool_used"] = f"{pool_used}"
        r["score_phase1"] = r.get("score_final", np.nan)
        return r

    recs = [
        _pack(top_pref, "선호형 (Preference)", "hybrid 선호 중심 + 칼로리/목표(Purpose δ) + Guardrail"),
        _pack(top_health, "건강형 (Health 5:3:2)", "5:3:2 근접 중심 + 칼로리/목표(Purpose δ) + Guardrail"),
    ]

    if explore_row is not None:
        explore_row["rec_type"] = "탐색형 (Exploration)"
        explore_row["Mood_req"] = str(mood)
        explore_row["Energy_req"] = str(energy)
        explore_row["Pool_used"] = "UNOBSERVED_POOL"
        explore_row["Explanation"] = f"미관측 풀에서 target_vec={wp:.2f}*pref + {wh:.2f}*healthy"
        explore_row["score_phase1"] = explore_row.get("score_final", np.nan)
        recs.append(explore_row)
    else:
        recs.append({
            "rec_type": "탐색형 (Exploration)",
            "Food": "N/A",
            "Calories": 0,
            "Explanation": "미관측 풀 부족/중복 제외로 후보 없음",
            "Mood_req": str(mood),
            "Energy_req": str(energy),
            "Pool_used": "UNOBSERVED_POOL",
            "score_phase1": np.nan,
        })

    return pd.DataFrame(recs)