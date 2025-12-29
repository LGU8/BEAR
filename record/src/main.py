from __future__ import annotations

import argparse
from pathlib import Path
import cv2

from src.config import load_config
from src.db.mysql import get_conn
from src.db.repo import save_ocr_result_to_db
from src.utils.timeutil import now_yyyymmdd
from src.utils.io import dump_json
from src.ocr.pipeline import run_ocr_pipeline


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--env", default=None, help=".env path (optional)")
    p.add_argument("--cust_id", required=True)
    p.add_argument("--rgs_dt", default=None, help="YYYYMMDD (default: today)")
    p.add_argument("--seq", type=int, required=True)
    p.add_argument("--image", required=True, help="image file path")
    p.add_argument(
        "--save_json",
        action="store_true",
        help="also save result json file under ARTIFACT_DIR/results",
    )
    p.add_argument("--score_thresh", type=float, default=0.6)
    p.add_argument("--max_side", type=int, default=1600)
    p.add_argument("--no_rotate", action="store_true")
    p.add_argument("--no_full", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    cfg = load_config(args.env)

    rgs_dt = args.rgs_dt or now_yyyymmdd()
    img_path = Path(args.image).resolve()

    img_bgr = cv2.imread(str(img_path))
    if img_bgr is None:
        raise RuntimeError(f"IMAGE_LOAD_FAILED: {img_path}")

    result = run_ocr_pipeline(
        img_bgr,
        score_thresh=args.score_thresh,
        max_side=args.max_side,
        try_rotate_if_low=(not args.no_rotate),
        do_full_fallback=(not args.no_full),
    )

    # S3 없으므로 local 식별자
    image_identifier = f"local://{img_path.as_posix()}"

    conn = get_conn(cfg)
    try:
        ocr_seq, success_yn = save_ocr_result_to_db(
            conn,
            cust_id=args.cust_id,
            rgs_dt=rgs_dt,
            seq=args.seq,
            image_identifier=image_identifier,
            ocr_result={"filename": img_path.name, **result},
            write_failed_json=False,
        )
    finally:
        conn.close()

    print("=" * 80)
    print("[DB SAVE RESULT]")
    print(f"- cust_id: {args.cust_id}")
    print(f"- rgs_dt : {rgs_dt}")
    print(f"- seq    : {args.seq}")
    print(f"- ocr_seq: {ocr_seq}")
    print(f"- success: {success_yn}")
    print(f"- final_source: {result.get('final_source')}")
    print(
        f"- elapsed_sec_total: {(result.get('debug') or {}).get('elapsed_sec_total')}"
    )

    if args.save_json:
        out_dir = cfg.artifact_dir / "results"
        out_path = out_dir / f"{args.cust_id}_{rgs_dt}_{args.seq}_{ocr_seq}.json"
        dump_json(
            out_path,
            {
                "cust_id": args.cust_id,
                "rgs_dt": rgs_dt,
                "seq": args.seq,
                "ocr_seq": ocr_seq,
                "image_identifier": image_identifier,
                "result": {"filename": img_path.name, **result},
            },
        )
        print(f"- saved_json: {out_path}")


if __name__ == "__main__":
    main()
