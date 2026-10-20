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


def test_swell_from_behind_is_flat():
    # 1,5 m de houle d'est sur une plage ouverte à l'ouest : hauteur effective 0, pas trop forte mais plate
    row = score.score_hour(GOOD_HOUR | {"swell_height_m": 1.5, "swell_direction_deg": 90},
                           LA_TORCHE, "debutant", DEBUTANT)
    assert row["ineligibility_reason"] == "houle_trop_faible" and row["global_score"] is None


def test_flat_sea_is_not_eligible():
    # Sainte-Barbe lundi 19/10 9 h : 0,18 m, période, vent et marée bons -> 60 à 62 en v0
    flat = GOOD_HOUR | {"swell_height_m": 0.18, "swell_period_s": 10.2}
    for level in score.LEVELS:
        row = score.score_hour(flat, LA_TORCHE, level, DEBUTANT)
        assert row["ineligibility_reason"] == "houle_trop_faible" and row["global_score"] is None
    # Au minimum du niveau, le créneau reste éligible
    assert score.score_hour(GOOD_HOUR | {"swell_height_m": 0.4}, LA_TORCHE, "debutant", DEBUTANT)["is_eligible"]


def test_onshore_wind_lowers_global_score():
    assert score.onshore_factor(100, 40) == 1  # offshore : pas de pénalité
    assert score.onshore_factor(0, 8) == 1  # vent de mer faible : pas de pénalité
    assert score.onshore_factor(0, 30) == pytest.approx(0.5)  # plein onshore et fort : -50 %
    assert score.onshore_factor(30, 17.5) == pytest.approx(1 - 0.5 * 0.7 * 0.5)
    # Même créneau, vent de 18 km/h offshore (90) puis onshore (59)
    offshore = score.score_hour(GOOD_HOUR | {"wind_speed_kmh": 18}, LA_TORCHE, "debutant", DEBUTANT)
    onshore = score.score_hour(GOOD_HOUR | {"wind_speed_kmh": 18, "wind_direction_deg": 250},
                               LA_TORCHE, "debutant", DEBUTANT)
    assert offshore["global_score"] == 90 and onshore["global_score"] == pytest.approx(59.3)


def test_sub_scores_follow_the_doc():
    assert score.height_score(1.2, DEBUTANT) == 40
    assert score.height_score(0.2, DEBUTANT) == 15
    assert score.period_score(5, DEBUTANT) == 0 and score.period_score(14, DEBUTANT) == 0
    assert score.period_score(12, DEBUTANT) == 75
    assert score.wind_speed_score(15, DEBUTANT) == 50 and score.wind_speed_score(20, DEBUTANT) == 0
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
