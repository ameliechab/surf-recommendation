"""Tests hors ligne du scoring : python -m pytest tests"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

import score  # noqa: E402

DEBUTANT = {"swell_height_min": 0.4, "swell_height_ideal_min": 0.4, "swell_height_ideal_max": 0.8,
            "swell_height_max": 1.2, "period_min": 6, "period_ideal_min": 8, "period_ideal_max": 11,
            "period_max": 13, "wind_speed_ideal_max": 10, "wind_speed_max": 20}
LA_TORCHE = {"spot_id": "la_torche", "min_level": "debutant", "spot_orientation_deg": 270,
             "ideal_swell_orientation_min": 225, "ideal_swell_orientation_max": 290,
             "ideal_wind_orientation_min": 45, "ideal_wind_orientation_max": 90,
             "ideal_tide_stage": "mi-maree"}
GOOD_HOUR = {"spot_id": "la_torche", "forecast_datetime": "2026-10-18T10:00:00+00:00",
             "retrieved_at": "2026-10-18T04:02:00+00:00", "swell_height_m": 0.7, "swell_period_s": 10,
             "swell_direction_deg": 270, "wind_speed_kmh": 8, "wind_direction_deg": 60,
             "tide_level_pct": 0.5, "tide_direction": "montante"}


def test_windows_through_north():
    assert score.distance_to_window(10, 330, 30) == 0
    assert score.distance_to_window(40, 330, 30) == 10
    assert score.distance_to_window(300, 330, 30) == 30
    assert score.distance_to_window(359, 270, 360) == 0


def test_default_windows():
    assert score.window(None, None, 270, 0, 30) == (240, 300)
    assert score.window(None, None, 270, 180, 45) == (45, 135)
    assert score.window(0, 90, 270, 180, 45) == (0, 90)  # 0 est une vraie valeur du Sheet


def test_perfect_hour_scores_100():
    row = score.score_hour(GOOD_HOUR, LA_TORCHE, "debutant", DEBUTANT)
    assert row["is_eligible"] and row["ineligibility_reason"] is None
    assert row["global_score"] == 100


def test_ineligibility_reasons():
    assert score.score_hour(GOOD_HOUR, LA_TORCHE | {"min_level": "avance"},
                            "debutant", DEBUTANT)["ineligibility_reason"] == "niveau_spot"
    assert score.score_hour(GOOD_HOUR | {"tide_level_pct": None}, LA_TORCHE,
                            "debutant", DEBUTANT)["ineligibility_reason"] == "donnees_manquantes"
    assert score.score_hour(GOOD_HOUR | {"swell_height_m": 1.5}, LA_TORCHE,
                            "debutant", DEBUTANT)["ineligibility_reason"] == "houle_trop_forte"
    assert score.score_hour(GOOD_HOUR | {"wind_speed_kmh": 25}, LA_TORCHE,
                            "debutant", DEBUTANT)["ineligibility_reason"] == "vent_trop_fort"
    row = score.score_hour(GOOD_HOUR | {"wind_speed_kmh": 25}, LA_TORCHE, "debutant", DEBUTANT)
    assert row["global_score"] is None


def test_swell_from_behind_is_not_too_big():
    # 1,5 m de houle d'est sur une plage ouverte à l'ouest : hauteur effective 0
    row = score.score_hour(GOOD_HOUR | {"swell_height_m": 1.5, "swell_direction_deg": 90},
                           LA_TORCHE, "debutant", DEBUTANT)
    assert row["is_eligible"] and row["swell_direction_score"] == 0 and row["swell_score"] == 0


def test_sub_scores_follow_the_doc():
    assert score.height_score(1.2, DEBUTANT) == 40
    assert score.height_score(0.2, DEBUTANT) == 15
    assert score.period_score(5, DEBUTANT) == 30 and score.period_score(14, DEBUTANT) == 30
    assert score.period_score(12, DEBUTANT) == 75
    assert score.wind_speed_score(15, DEBUTANT) == 65
    assert score.wind_direction_score(0, 30) == 100 and score.wind_direction_score(45, 30) == 70
    assert score.wind_direction_score(90, 30) == 30 and score.wind_direction_score(180, 30) == 0
    assert score.wind_direction_score(180, 4) == 100  # vent quasi nul
    assert score.tide_score(0.5, "descendante", "montante") == 70
    assert score.tide_score(0.9, "montante", "mi-maree") == pytest.approx(60)
    assert score.tide_score(0.2, "montante", None) == 100


def test_night_is_not_eligible():
    row = score.score_hour(GOOD_HOUR | {"is_daylight": False}, LA_TORCHE, "debutant", DEBUTANT)
    assert row["ineligibility_reason"] == "nuit" and row["global_score"] is None
    assert score.score_hour(GOOD_HOUR | {"is_daylight": True}, LA_TORCHE, "debutant", DEBUTANT)["is_eligible"]
