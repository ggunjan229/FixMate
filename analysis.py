"""Small reproducible data profiles for the admin analytics screen."""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "smart_worker_allocation_20000_v2 (2).csv"
REPORT = ROOT / "evaluation_report.json"


def allocation_dataset_profile() -> dict:
    if not DATA.exists():
        return {"available": False, "note": "Allocation CSV was not found."}
    rows = 0
    bookings, workers = set(), set()
    targets = {"0": 0, "1": 0}
    categories: dict[str, int] = {}
    missing = 0
    columns: list[str] = []
    with DATA.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        columns = reader.fieldnames or []
        for row in reader:
            rows += 1
            bookings.add(row.get("booking_id", ""))
            workers.add(row.get("worker_id", ""))
            target = row.get("successful_completion", "")
            if target in targets:
                targets[target] += 1
            categories[row.get("service_category") or "(missing)"] = categories.get(row.get("service_category") or "(missing)", 0) + 1
            missing += sum(1 for value in row.values() if value is None or not value.strip())
    report = {}
    if REPORT.exists():
        try:
            report = json.loads(REPORT.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            report = {}
    return {"available": True, "rows": rows, "bookings": len(bookings), "workers": len(workers),
            "target_balance": targets, "categories": dict(sorted(categories.items())),
            "missing_cells": missing, "columns": len(columns), "report": report,
            "provenance": "The repository does not currently record where these candidate labels came from."}


def gini(values: list[int | float]) -> float:
    positive = sorted(max(0.0, float(value)) for value in values)
    if not positive or sum(positive) == 0:
        return 0.0
    n = len(positive)
    return round(sum((2 * i - n - 1) * value for i, value in enumerate(positive, 1)) / (n * sum(positive)), 4)

