"""Tests hors ligne de l'habillage : python -m pytest tests"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ui  # noqa: E402


def test_lagon_scale():
    assert ui.score_colors(96) == ("#1F7A80", "#FFFFFF")
    assert ui.score_colors(90)[0] == "#1F7A80" and ui.score_colors(89.9)[0] == "#4FA3A3"
    assert ui.score_colors(60)[0] == "#8CC7BF" and ui.score_colors(50)[0] == "#C6E4DE"
    assert ui.score_colors(None)[0] == ui.OFF and ui.score_colors(float("nan"))[0] == ui.OFF
    assert ui.hex_to_rgb("#1F7A80") == [31, 122, 128]


def test_legend_and_escaping():
    legend = ui.legend_html()
    for label in ["Excellent (90+)", "Bon (75–89)", "Correct (60–74)", "Moyen (50–59)"]:
        assert label in legend
    rec = {"rank": 1, "spot_name": "Le Loc'h <b>", "department": "Morbihan", "distance_km": 11,
           "slot": "9 h – 11 h", "score": 96}
    head = ui.card_header_html(rec)
    assert "Le Loc&#x27;h &lt;b&gt;" in head and "Morbihan, 11 km" in head


def test_strip_marks_the_recommended_slot():
    rec = {"hourly": {8: None, 9: 96, 10: 94, 11: 80}, "start_hour": 9, "end_hour": 11}
    strip = ui.strip_html(rec)
    assert strip.count("fyw-cell best") == 2 and strip.count('class="fyw-cell"') == 2


def test_map_zoom_fits_the_radius():
    assert ui.map_zoom(10) == 10.0 and ui.map_zoom(300) == 5.5
    assert 6.5 < ui.map_zoom(100) < 7.5  # le cercle de 100 km tient dans ~640 px


def test_detail_shows_remarks_and_warnings():
    rec = {"hourly": {9: 80}, "start_hour": 9, "end_hour": 10}
    explanation = {"summary": "Houle idéale.", "remarks": ["Vent de travers."], "warnings": ["Marée peu favorable."],
                   "contributions": [], "onshore_points": 0}
    html = ui.detail_html(rec, [("Houle au large", "1 m")], explanation)
    assert '<p class="fyw-remark">Vent de travers.</p>' in html and '<p class="fyw-warn">Marée peu favorable.</p>' in html
