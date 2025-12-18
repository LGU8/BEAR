# record/views_api.py
import uuid
import tempfile
from pathlib import Path
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt

from .services.barcode.total import run_barcode_pipeline


def _normalize_candidate(raw: dict) -> dict:
    # TODO: mapping_code.py 결과 구조에 맞춰 키 매핑만 맞추면 됨
    return {
        "candidate_id": raw.get("candidate_id") or raw.get("id") or str(uuid.uuid4()),
        "name": raw.get("name") or raw.get("product_name") or "",
        "brand": raw.get("brand") or raw.get("company") or "",
        "flavor": raw.get("flavor") or raw.get("taste") or raw.get("variant") or "",
        # 필요하면 추후 영양정보 필드도 같이 넣을 수 있음
        "raw": raw,  # commit 단계에서 상세가 필요하면 유지(너무 크면 제거)
    }


import tempfile
from pathlib import Path


@csrf_exempt
@require_POST
def api_barcode_scan(request):

    # ✅ 1) mode를 가장 먼저 읽는다
    mode = request.POST.get("mode", "barcode")  # "barcode" | "nutrition"
    print("[SCAN] mode =", mode)

    image = request.FILES.get("image")
    date = request.POST.get("date", "").strip()
    meal = request.POST.get("meal", "").strip()

    if not image:
        return JsonResponse({"ok": False, "error": "image is required"}, status=400)

    # ✅ UploadedFile → 임시 파일로 저장
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        for chunk in image.chunks():
            tmp.write(chunk)
        tmp_path = tmp.name  # 👈 이게 str 경로

    try:
        barcode, raw_candidates = run_barcode_pipeline(tmp_path)

        # ✅ (추가 1) barcode 타입 정규화: list/tuple -> str
        if isinstance(barcode, (list, tuple)):
            barcode = barcode[0] if barcode else ""
        barcode = str(barcode).strip()

        if not barcode:
            return JsonResponse(
                {
                    "ok": False,
                    "reason": "SCAN_FAIL",
                    "barcode": "",
                    "message": "바코드를 인식하지 못했어요. 바코드를 네모칸 안에 맞추고 다시 시도해 주세요.",
                },
                status=400,
            )

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)

    finally:
        # ✅ 임시 파일 정리
        Path(tmp_path).unlink(missing_ok=True)

    # 후보 정규화 (기존 로직 유지)
    candidates = [_normalize_candidate(x) for x in (raw_candidates or [])]

    if not candidates:
        return JsonResponse(
            {
                "ok": False,
                "reason": "NO_MATCH",
                "barcode": barcode,
                "message": "해당 바코드로 조회되는 제품이 없습니다. 검색으로 추가해 주세요.",
            },
            status=404,
        )

    draft_id = uuid.uuid4().hex
    request.session[f"barcode_draft:{draft_id}"] = {
        "date": date,
        "meal": meal,
        "barcode": barcode,
        "candidates": candidates,
    }
    request.session.modified = True

    return JsonResponse({"ok": True, "draft_id": draft_id, "barcode": barcode})


@require_GET
def api_barcode_draft(request):
    draft_id = request.GET.get("draft_id", "").strip()
    data = request.session.get(f"barcode_draft:{draft_id}")
    if not data:
        return JsonResponse({"ok": False, "error": "draft not found"}, status=404)

    # UI에 필요한 필드만 내려주기(요구사항: 제품명/브랜드/맛)
    slim = [
        {
            "candidate_id": c["candidate_id"],
            "name": c.get("name", ""),
            "brand": c.get("brand", ""),
            "flavor": c.get("flavor", ""),
        }
        for c in data.get("candidates", [])
    ]

    return JsonResponse(
        {
            "ok": True,
            "date": data.get("date"),
            "meal": data.get("meal"),
            "barcode": data.get("barcode"),
            "candidates": slim,
        }
    )


@csrf_exempt
@require_POST
def api_barcode_commit(request):
    draft_id = request.POST.get("draft_id", "").strip()
    candidate_id = request.POST.get("candidate_id", "").strip()

    data = request.session.get(f"barcode_draft:{draft_id}")
    if not data:
        return JsonResponse({"ok": False, "error": "draft not found"}, status=404)

    candidates = data.get("candidates", [])
    picked = next((c for c in candidates if c["candidate_id"] == candidate_id), None)
    if not picked:
        return JsonResponse({"ok": False, "error": "candidate not found"}, status=400)

    # draft 제거(선택 UX는 1회성)
    request.session.pop(f"barcode_draft:{draft_id}", None)
    request.session.modified = True

    # 프론트가 localStorage/카드 저장에 쓸 최소 payload
    return JsonResponse(
        {
            "ok": True,
            "date": data.get("date"),
            "meal": data.get("meal"),
            "barcode": data.get("barcode"),
            "picked": {
                "name": picked.get("name", ""),
                "brand": picked.get("brand", ""),
                "flavor": picked.get("flavor", ""),
                # 추후 영양정보도 여기 포함 가능
            },
        }
    )
