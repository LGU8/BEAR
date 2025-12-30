# CUS_OCR_TH: OCR 처리 이력
SQL_NEXT_OCR_SEQ = """
SELECT COALESCE(MAX(ocr_seq), 0) + 1 AS next_ocr_seq
FROM CUS_OCR_TH
WHERE cust_id=%s AND rgs_dt=%s AND seq=%s
"""

SQL_UPSERT_OCR_TH = """
INSERT INTO CUS_OCR_TH (
  cust_id, rgs_dt, seq, ocr_seq,
  image_s3_bucket, image_s3_key,
  chosen_source, roi_score, full_score,
  success_yn, error_code,
  created_time, updated_time
) VALUES (
  %s, %s, %s, %s,
  %s, %s,
  %s, %s, %s,
  %s, %s,
  %s, %s
)
ON DUPLICATE KEY UPDATE
  image_s3_bucket = VALUES(image_s3_bucket),
  image_s3_key    = VALUES(image_s3_key),
  chosen_source   = VALUES(chosen_source),
  roi_score       = VALUES(roi_score),
  full_score      = VALUES(full_score),
  success_yn      = VALUES(success_yn),
  error_code      = VALUES(error_code),
  updated_time    = VALUES(updated_time)
"""

# CUS_OCR_NUTR_TS: 최종 영양정보 JSON
SQL_UPSERT_OCR_NUTR = """
INSERT INTO CUS_OCR_NUTR_TS (
  cust_id, rgs_dt, seq, ocr_seq,
  result_json,
  created_time, updated_time
) VALUES (
  %s, %s, %s, %s,
  CAST(%s AS JSON),
  %s, %s
)
ON DUPLICATE KEY UPDATE
  result_json  = VALUES(result_json),
  updated_time = VALUES(updated_time)
"""
