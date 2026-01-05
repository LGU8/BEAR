# ml/management/commands/run_8pm_batch_prediction.py
from __future__ import annotations

from django.core.management.base import BaseCommand

from ml.lstm.batch import run_8pm_batch_prediction


class Command(BaseCommand):
    help = "Run 20:00 backup batch: create next-slot negative emotion prediction for users with today's TS."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run even if before 20:00 (debug).",
        )

    def handle(self, *args, **options):
        force = bool(options.get("force"))
        result = run_8pm_batch_prediction(force=force)
        self.stdout.write(self.style.SUCCESS(str(result)))
