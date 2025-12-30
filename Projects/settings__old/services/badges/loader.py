import json
import os
from typing import Dict, Any, List

def load_badge_meta() -> Dict[str, Any]:
    """
    settings/views.py의 _load_badge_meta()와 동일 경로 규칙 유지
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))  # .../services/badges
    # settings/badges_meta/badge_meta.json (현재 구조 기준)
    meta_path = os.path.join(os.path.dirname(os.path.dirname(base_dir)), "badges_meta", "badge_meta.json")
    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)

def iter_items(meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [x for x in meta.get("items", []) if x.get("badge_id")]