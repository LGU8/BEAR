# record/views_keywords.py

from django.http import JsonResponse
from django.db import connection
import logging

logger = logging.getLogger(__name__)

def keyword_api(request):
    if request.method != "GET":
        return JsonResponse({"error": "GET only"}, status=405)

    mood = request.GET.get("mood")
    energy = request.GET.get("energy")

    if not mood or not energy:
        return JsonResponse([], safe=False)

    try:
        sql = """
            SELECT word
            FROM COM_FEEL_TM
            WHERE cluster_val IN (
                SELECT cluster_val
                FROM COM_FEEL_CLUSTER_TM
                WHERE mood = %s AND energy = %s
            )
        """
        with connection.cursor() as cursor:
            cursor.execute(sql, [mood, energy])
            rows = cursor.fetchall()

        keywords = [r[0] for r in rows]
        return JsonResponse(keywords, safe=False)

    except Exception:
        logger.exception("[KEYWORD_API] failed mood=%s energy=%s", mood, energy)
        return JsonResponse([], safe=False)
