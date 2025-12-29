from django.core.management.base import BaseCommand
from django.db import connection
from settings.services.badges.engine import award_badges

class Command(BaseCommand):
    help = "Backfill badges for all users (re-evaluate badge rules and insert missing CUS_BADGE_TM rows)."

    def add_arguments(self, parser):
        parser.add_argument("--cust_id", type=str, default="")

    def handle(self, *args, **options):
        only = (options.get("cust_id") or "").strip()

        cust_ids = []
        with connection.cursor() as cur:
            if only:
                cust_ids = [only]
            else:
                cur.execute("SELECT cust_id FROM CUST_TM")
                cust_ids = [str(r[0]) for r in cur.fetchall()]

        total_granted = 0
        for cid in cust_ids:
            granted = award_badges(cid, trigger_event="BACKFILL")
            total_granted += len(granted)
            self.stdout.write(f"[{cid}] granted={len(granted)} {granted}")

        self.stdout.write(self.style.SUCCESS(f"Done. total_granted={total_granted}"))