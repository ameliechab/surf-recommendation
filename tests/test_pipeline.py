"""Tests hors ligne : python -m pytest tests"""
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collect import build_rows  # noqa: E402
from sync_sheets import clean_table  # noqa: E402
from tide import compute_tide  # noqa: E402


def tide_curve(hours=216, period=12.42, amplitude=2.5):
    return [round(amplitude * math.sin(2 * math.pi * h / period), 3) for h in range(hours)]


def test_tide_rising_and_falling():
    levels = tide_curve()
    pct, direction, stage = compute_tide(levels)
    filled = [i for i, p in enumerate(pct) if p is not None]
    # seules quelques heures au début et à la fin restent sans marée
    assert filled[0] <= 7 and filled[-1] >= len(levels) - 8
    for i in filled[1:]:
        if direction[i] == direction[i - 1] == "montante":
            assert pct[i] >= pct[i - 1]
        if direction[i] == direction[i - 1] == "descendante":
            assert pct[i] <= pct[i - 1]
    assert {"basse", "mi-maree", "pleine"} <= set(stage)


def test_tide_plateau_and_gaps():
    levels = [1, 0, 0, 1, 2, 2, 1, None, 0, 1]
    pct, direction, _ = compute_tide(levels)
    assert pct[1] == 0 and direction[1] == "montante"
    assert pct[7] is None


def test_sheet_dates_are_rejected():
    df = pd.DataFrame([{
        "surf_level": "Débutant", "swell_height_min": "0,4", "swell_height_ideal_min": "0.4",
        "swell_height_ideal_max": "0.8", "swell_height_max": pd.Timestamp("2026-02-01"),
        "period_min (sec)": 8, "period_ideal_min (sec)": 8, "period_ideal_max": 11,
        "period_max (sec)": 13, "wind_speed_ideal_max": 10, "wind_speed_max": 20,
    }])
    rows, errors = clean_table("surf_level_conditions_reference", df)
    assert rows[0]["surf_level"] == "debutant" and rows[0]["swell_height_min"] == 0.4
    assert len(errors) == 1 and "date" in errors[0]


def test_build_rows():
    times = pd.date_range("2026-10-17", periods=216, freq="h", tz="UTC")
    marine = pd.DataFrame({"forecast_datetime": times, "swell_height_m": 1.2,
                           "sea_level_height_m": tide_curve()})
    weather = pd.DataFrame({"forecast_datetime": times, "wind_speed_kmh": 12.0})
    rows = build_rows("la_torche", marine, weather, "2026-10-17T04:02:00+00:00")
    assert len(rows) == 216
    assert rows[0]["forecast_datetime"] == "2026-10-17T00:00:00+00:00"
    assert rows[0]["tide_stage"] is None and rows[50]["tide_stage"] is not None
