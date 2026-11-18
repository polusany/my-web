"""Create a reproducible held-out evaluation report for the comparable-listings model."""
import csv
import json
import random
import statistics
from pathlib import Path

import app

ROOT = Path(__file__).resolve().parent
RANDOM_SEED = 42
HOLDOUT_FRACTION = 0.2
MAX_EVALUATION_ROWS = 1000


def median_absolute_error(pairs):
    return statistics.median(abs(actual - predicted) for actual, predicted in pairs)


def median_absolute_percentage_error(pairs):
    return statistics.median(abs(actual - predicted) / actual * 100 for actual, predicted in pairs if actual > 0)


def baseline_prediction(row, training):
    for match in (
        lambda item: item["state"] == row["state"] and item["town"] == row["town"] and item["title"] == row["title"],
        lambda item: item["state"] == row["state"] and item["title"] == row["title"],
        lambda item: item["state"] == row["state"],
    ):
        prices = [item["price"] for item in training if match(item)]
        if len(prices) >= 5:
            return statistics.median(prices)
    return statistics.median(item["price"] for item in training if item["state"] == row["state"])


def main():
    records = list(app.LISTINGS)
    random.Random(RANDOM_SEED).shuffle(records)
    split = int(len(records) * (1 - HOLDOUT_FRACTION))
    training, held_out = records[:split], records[split:]
    if len(held_out) > MAX_EVALUATION_ROWS:
        held_out = random.Random(RANDOM_SEED).sample(held_out, MAX_EVALUATION_ROWS)

    model_pairs, baseline_pairs = [], []
    for row in held_out:
        query = {key: row[key] for key in ("state", "town", "title", *app.NUMERIC_FIELDS)}
        result = app.predict(query, source=training)
        model_pairs.append((row["price"], result["estimate"]))
        baseline_pairs.append((row["price"], baseline_prediction(row, training)))

    raw_state_counts = {state: 0 for state in app.ALLOWED_STATES}
    with app.DATA_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            raw_state = (raw.get("state") or "").strip()
            state = app.STATE_ALIASES.get(raw_state.casefold(), app.STATE_LOOKUP.get(raw_state.casefold(), raw_state))
            if state in raw_state_counts:
                raw_state_counts[state] += 1
    clean_state_counts = {state: sum(row["state"] == state for row in records) for state in app.ALLOWED_STATES}
    metrics_by_state = {}
    for state in app.ALLOWED_STATES:
        state_model = [pair for row, pair in zip(held_out, model_pairs) if row["state"] == state]
        state_baseline = [pair for row, pair in zip(held_out, baseline_pairs) if row["state"] == state]
        if state_model:
            metrics_by_state[state] = {
                "held_out_rows": len(state_model),
                "model_median_absolute_error_ngn": round(median_absolute_error(state_model)),
                "model_median_absolute_percentage_error": round(median_absolute_percentage_error(state_model), 1),
                "baseline_median_absolute_error_ngn": round(median_absolute_error(state_baseline)),
                "baseline_median_absolute_percentage_error": round(median_absolute_percentage_error(state_baseline), 1),
            }

    report = {
        "dataset": "Nigerian House Price Dataset (Kaggle)",
        "source_rows": 24326,
        "raw_rows_in_supported_states": raw_state_counts,
        "cleaned_unique_rows_by_state": clean_state_counts,
        "exact_duplicates_and_invalid_rows_removed": sum(raw_state_counts.values()) - len(records),
        "cleaned_unique_lagos_abuja_rows": len(records),
        "training_rows": len(training),
        "held_out_rows_scored": len(held_out),
        "split": "random 80/20 split; seed 42; evaluation capped at 1,000 randomly selected held-out rows",
        "model": "distance-weighted comparable-listings median",
        "metrics_ngn": {
            "model_median_absolute_error": round(median_absolute_error(model_pairs)),
            "baseline_median_absolute_error": round(median_absolute_error(baseline_pairs)),
        },
        "metrics_percent": {
            "model_median_absolute_percentage_error": round(median_absolute_percentage_error(model_pairs), 1),
            "baseline_median_absolute_percentage_error": round(median_absolute_percentage_error(baseline_pairs), 1),
        },
        "metrics_by_state": metrics_by_state,
        "minimum_listings_per_supported_state": app.MIN_STATE_LISTINGS,
        "note": "Evaluation is against held-out advertised asking prices, not verified sale prices. Only states with at least the minimum number of usable listings are included. A random split can place similar repeated listings in both groups; interpret results cautiously.",
    }
    (ROOT / "model_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
