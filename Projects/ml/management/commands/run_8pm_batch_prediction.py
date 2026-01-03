# ml/management/commands/run_8pm_batch_prediction.py
from __future__ import annotations

from django.core.management.base import BaseCommand

from ml.lstm.batch import run_batch_predict_next_morning_if_needed


class Command(BaseCommand):
    help = "Run 20:00 batch: create next-morning negative emotion prediction for users with today's TS."

    def handle(self, *args, **options):
        res = run_batch_predict_next_morning_if_needed()
        self.stdout.write(self.style.SUCCESS(str(res)))
