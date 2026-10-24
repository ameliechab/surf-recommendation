"""Tests hors ligne des explications : python -m pytest tests"""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

import explain  # noqa: E402
import score  # noqa: E402
from tests.test_score import DEBUTANT, GOOD_HOUR, LA_TORCHE  # noqa: E402

COND = GOOD_HOUR | {"tide_stage": "mi-maree", "water_temp_c": 15.8}


def scored(**changes):
    """Heure scorée par score.py, pour tester sur de vrais sous-scores."""
    fc = COND | changes
    return score.score_hour(fc, LA_TORCHE, "debutant", DEBUTANT), fc


def test_french_labels():
    assert explain.fr_number(0.84) == "0,8" and explain.fr_number(1.0) == "1"
    assert explain.fr_number(11.1, 0) == "11"
    assert explain.from_direction(355) == "du nord" and explain.from_direction(276) == "d’ouest"
    assert explain.from_direction(214) == "de sud-ouest"
    assert explain.tide_label("mi-maree", "montante") == "mi-marée montante"
    assert explain.tide_label("basse", "descendante") == "marée basse, descendante"
    assert explain.fr_date(dt.date(2026, 10, 20)) == "mardi 20 octobre"
    assert explain.fr_short_date(dt.date(2026, 10, 21)) == "Mer. 21"
    assert explain.fr_datetime(dt.datetime(2026, 10, 20, 13, 2)) == "20 oct. à 13 h 02"


def test_conditions_list():
    items = dict(explain.conditions_list(COND))
    assert items == {"Houle": "0,7 m, 10 s d’ouest", "Vent": "8 km/h de nord-est",
                     "Marée": "mi-marée montante", "Eau": "16 °C"}
    calm = dict(explain.conditions_list(COND | {"wind_speed_kmh": 3, "water_temp_c": None}))
    assert calm["Vent"] == "3 km/h" and "Eau" not in calm


def test_contributions_add_up_to_global_score():
    # Le détail affiché doit retomber sur le score global, vent de mer compris
    for changes in [{}, {"wind_speed_kmh": 18, "wind_direction_deg": 250}, {"swell_period_s": 7},
                    {"tide_level_pct": 0.95, "wind_speed_kmh": 14, "wind_direction_deg": 200}]:
        row, fc = scored(**changes)
        result = explain.explain(row, fc, DEBUTANT)
        total = sum(p["points"] for p in result["contributions"]) - result["onshore_points"]
        assert total == pytest.approx(row["global_score"], abs=0.3)


def test_summary_cites_the_two_biggest_contributions():
    row, fc = scored()
    result = explain.explain(row, fc, DEBUTANT)
    # houle (40 points) puis vent (25 points)
    assert result["summary"] == ("Houle idéale pour ton niveau (0,7 m d’ouest) et "
                                 "vent de terre léger (8 km/h de nord-est).")
    assert result["warnings"] == []


def test_short_period_is_a_warning():
    row, fc = scored(swell_period_s=7)
    assert row["period_score"] < 50
    warnings = explain.explain(row, fc, DEBUTANT)["warnings"]
    assert warnings == ["Période courte (7 s) : vagues molles et rapprochées."]


def test_onshore_wind_is_mentioned_once():
    row, fc = scored(wind_speed_kmh=18, wind_direction_deg=250)  # 90 -> 59 (test_score)
    result = explain.explain(row, fc, DEBUTANT)
    assert result["onshore_factor"] < explain.ONSHORE_MENTION
    assert result["warnings"][0].startswith("Vent de mer à 18 km/h : les vagues seront moins propres (−")
    # le sous-score de vent est bas, mais on ne répète pas « vent mal orienté »
    assert not any("mal orienté" in w for w in result["warnings"])


def test_tide_and_swell_warnings():
    row, fc = scored(tide_level_pct=0.98)
    assert "Marée peu favorable pour ce spot (mi-marée montante)." in explain.explain(row, fc)["warnings"]
    scores = row | {"swell_score": 40, "swell_direction_score": 100}
    small = explain.explain(scores, fc | {"swell_height_m": 0.42},
                            DEBUTANT | {"swell_height_ideal_min": 0.6})["warnings"]
    assert "Houle petite pour ton niveau (0,4 m sur le spot, idéal à partir de 0,6 m)." in small
    turned = explain.explain(scores | {"swell_direction_score": 60}, fc)["warnings"]
    assert "Houle mal orientée pour ce spot (0,7 m d’ouest)." in turned


def test_wind_speed_score_zero_is_a_warning():
    # wind_speed_score = 0 au maximum du niveau : 0 ne doit pas être pris pour « absent »
    row, fc = scored(wind_speed_kmh=20)
    assert row["wind_speed_score"] == 0 and row["wind_score"] == 50  # 50 : pas encore un point de vigilance
    assert explain.explain(row, fc, DEBUTANT)["warnings"] == []
    warnings = explain.explain(row | {"wind_score": 40}, fc, DEBUTANT)["warnings"]
    assert "Vent soutenu pour ton niveau (20 km/h)." in warnings


def test_misaligned_swell_shows_the_useful_height():
    # Le Petit Minou (fenêtre 225–270), 2,1 m de nord-ouest (315°) : 45° hors fenêtre,
    # facteur 0,4 -> 0,84 m utiles, sous le max intermédiaire de 1,8 m : le créneau reste éligible
    fc = COND | {"swell_height_m": 2.1, "swell_direction_deg": 315, "swell_period_s": 9}
    spot = LA_TORCHE | {"ideal_swell_orientation_min": 225, "ideal_swell_orientation_max": 270}
    row = score.score_hour(fc, spot, "debutant", DEBUTANT | {"swell_height_max": 1.8})
    assert row["is_eligible"] and row["swell_direction_score"] == pytest.approx(40)
    items = dict(explain.conditions_list(fc, row))
    assert items["Houle au large"] == "2,1 m, 9 s de nord-ouest"
    assert items["Houle sur le spot"] == "0,8 m, mal orientée"
    summary = explain.explain(row, fc, DEBUTANT)["summary"]
    assert "environ 0,8 m utiles : 2,1 m au large de nord-ouest" in summary
    # bien orientée : les deux lignes restent affichées, avec la même hauteur
    items = dict(explain.conditions_list(COND, {"swell_direction_score": 100}))
    assert items["Houle au large"] == "0,7 m, 10 s d’ouest" and items["Houle sur le spot"] == "0,7 m, bien orientée"


def test_fair_swell_says_why():
    # Le Loc'h dimanche : 1,6 m bien orientée, au-dessus de l'idéal intermédiaire (1,2 m) -> 56
    inter = DEBUTANT | {"swell_height_ideal_max": 1.2, "swell_height_max": 1.8}
    fc = COND | {"swell_height_m": 1.6}
    row = score.score_hour(fc, LA_TORCHE, "debutant", inter)
    assert 50 <= row["swell_score"] < 70
    summary = explain.explain(row, fc, inter)["summary"]
    assert "houle correcte, un peu grosse pour ton niveau (1,6 m d’ouest)" in summary


def test_remarks_between_50_and_70():
    # Vent de 14 km/h à 60° de la fenêtre offshore : sous-score vent ~58, hors des 2 critères cités
    row, fc = scored(wind_speed_kmh=14, wind_direction_deg=150)
    assert 50 <= row["wind_score"] < 70
    result = explain.explain(row, fc, DEBUTANT)
    assert "vent" not in result["summary"].lower()
    assert result["remarks"] == ["Vent un peu soutenu pour ton niveau (14 km/h)."]
    # un critère noté 70 ou plus, ou déjà cité dans la phrase principale, n'a pas de remarque
    good, fc = scored()
    assert explain.explain(good, fc, DEBUTANT)["remarks"] == []
    fair_swell = good | {"swell_score": 60}
    assert not any("Houle" in r for r in explain.explain(fair_swell, fc, DEBUTANT)["remarks"])


def test_remark_for_side_wind_direction():
    scores = {"swell_score": 100, "period_score": 100, "wind_score": 60, "tide_score": 100,
              "wind_speed_score": 100, "wind_direction_score": 66, "swell_direction_score": 100}
    fc = COND | {"wind_speed_kmh": 9, "wind_direction_deg": 270}
    result = explain.explain(scores, fc, DEBUTANT)
    assert result["remarks"] == ["Vent de travers (9 km/h d’ouest) : vagues un peu moins propres."]


def test_weak_criterion_is_not_praised():
    # Houle à 40 : elle ne fait pas partie de la phrase principale, elle passe en vigilance
    row, fc = scored(swell_height_m=1.15)
    scores = row | {"swell_score": 40}
    result = explain.explain(scores, fc, DEBUTANT)
    assert "houle" not in result["summary"].lower()
    assert "Houle grosse pour ton niveau (1,1 m sur le spot, idéal jusqu’à 0,8 m)." in result["warnings"]


def test_ideal_swell_near_a_bound_is_qualified():
    # Pro, idéal 1,2 à 2,5 m : 1,2 m est dans l'idéal (sous-score 100) mais tout en bas
    pro = DEBUTANT | {"swell_height_min": 0.6, "swell_height_ideal_min": 1.2, "swell_height_ideal_max": 2.5,
                      "swell_height_max": 5.0}
    fc = COND | {"swell_height_m": 1.2}
    row = score.score_hour(fc, LA_TORCHE, "debutant", pro)
    assert row["swell_score"] == 100
    summary = explain.explain(row, fc, pro)["summary"]
    assert ("Houle dans la fourchette idéale pour ton niveau, mais en bas de fourchette "
            "(1,2 m sur le spot, idéal de 1,2 à 2,5 m)") in summary
    high = explain.explain(row, fc | {"swell_height_m": 2.4}, pro)["summary"]
    assert "en haut de fourchette (2,4 m sur le spot" in high
    middle = explain.explain(row, fc | {"swell_height_m": 1.8}, pro)["summary"]
    assert middle.startswith("Houle idéale pour ton niveau (1,8 m d’ouest)")
