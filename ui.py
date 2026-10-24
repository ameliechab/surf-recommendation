"""Habillage de l'interface (maquette C v2) : couleurs, CSS et blocs HTML.

Python pur, sans Streamlit : app.py injecte ces morceaux avec st.markdown / st.html.
Échelle des scores « Lagon » ; tons coucher de soleil réservés au bandeau.
"""
import html
import math

from explain import fr_number

OCEAN = "#1546A0"
INK = "#13203F"
MUTED = "#5B6482"
PAGE = "#ECEFF6"
FIELD = "#F1F2F7"
LINE = "#DCDFEA"
WARNING = "#E77B95"

# Échelle « Lagon » : (score minimal, libellé, fond, texte)
SCALE = [
    (90, "Excellent", "#1F7A80", "#FFFFFF"),
    (75, "Bon", "#4FA3A3", INK),
    (60, "Correct", "#8CC7BF", INK),
    (50, "Moyen", "#C6E4DE", INK),
]
OFF = "#E6E8F0"  # non surfable, nuit ou sous le seuil
SUNSET = ["#9A88B8", "#E77B95", "#EC6A3C", "#F3B73F"]  # mauve, rose, orange, doré


def score_colors(score: float | None) -> tuple[str, str]:
    """(fond, texte) d'un score."""
    if score is not None and not (isinstance(score, float) and math.isnan(score)):
        for floor, _, background, text in SCALE:
            if score >= floor:
                return background, text
    return OFF, INK


def hex_to_rgb(color: str) -> list[int]:
    return [int(color[i:i + 2], 16) for i in (1, 3, 5)]


def esc(text) -> str:
    return html.escape(str(text), quote=True)


# ---------------------------------------------------------------------------
# CSS global
# ---------------------------------------------------------------------------
CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap');
.stApp, .stApp *:not([data-testid="stIconMaterial"]):not(.material-symbols-rounded) {{
  font-family: 'Montserrat', sans-serif;
}}
.stApp {{ background: {PAGE}; }}
.block-container {{ padding-top: 2rem; padding-bottom: 3rem; }}

/* Formulaire et cartes : blocs blancs sans bordure */
[data-testid="stForm"] {{ background: #fff; border: none; border-radius: 12px; padding: 20px; }}
[class*="st-key-fyw-card"] {{ background: #fff; border-radius: 12px; padding: 14px 18px 4px; gap: 0; }}
[class*="st-key-fyw-card"] [data-testid="stExpander"] details {{ border: none; border-top: 1px solid {LINE};
  border-radius: 0; }}
[class*="st-key-fyw-card"] [data-testid="stExpander"] summary {{ padding-left: 0; padding-right: 0; }}
[class*="st-key-fyw-card"] [data-testid="stExpanderDetails"] {{ padding-left: 0; padding-right: 0; }}
.stTabs [data-baseweb="tab"] p {{ font-weight: 600; }}

/* Bandeau */
.fyw-hero {{ position: relative; overflow: hidden; border-radius: 16px; padding: 30px 32px;
  background: linear-gradient(180deg, {OCEAN} 0%, #0E2D6B 100%); color: #fff; min-height: 200px; }}
.fyw-hero .fyw-brand {{ font-weight: 800; font-size: 20px; letter-spacing: -0.3px; }}
.fyw-hero .fyw-question {{ font-weight: 800; font-size: 34px; line-height: 1.15; letter-spacing: -0.6px;
  margin: 18px 0 8px; max-width: 60%; position: relative; z-index: 1; }}
.fyw-hero .fyw-tagline {{ font-size: 14px; color: #C9D6F2; max-width: 55%; position: relative; z-index: 1; }}
.fyw-streak {{ position: absolute; right: -40px; left: 42%; border-radius: 99px; filter: blur(3px); }}
@media (max-width: 640px) {{
  .fyw-hero {{ padding: 22px 22px 70px; min-height: 0; }}
  .fyw-hero .fyw-question {{ font-size: 26px; max-width: 100%; margin-top: 12px; }}
  .fyw-hero .fyw-tagline {{ display: none; }}
  .fyw-streak {{ left: 18%; }}
}}

/* En-tête d'un résultat */
.fyw-head {{ display: flex; align-items: center; gap: 14px; padding: 4px 0 12px; }}
.fyw-rank {{ font-weight: 700; color: {MUTED}; width: 16px; }}
.fyw-title {{ flex: 1; min-width: 0; }}
.fyw-name {{ font-weight: 700; font-size: 19px; color: {INK}; letter-spacing: -0.2px; }}
.fyw-sub {{ font-size: 13px; color: {MUTED}; margin-top: 2px; }}
.fyw-sub b {{ color: {INK}; font-weight: 700; }}
.fyw-badge {{ min-width: 48px; height: 40px; border-radius: 8px; display: flex; align-items: center;
  justify-content: center; font-weight: 800; font-size: 18px; padding: 0 10px; }}

/* Détail */
.fyw-strip {{ display: flex; gap: 3px; }}
.fyw-cell {{ flex: 1; height: 22px; border-radius: 3px; }}
.fyw-cell.best {{ box-shadow: inset 0 0 0 2px {INK}; }}
.fyw-hours {{ display: flex; gap: 3px; margin-top: 4px; }}
.fyw-hours span {{ flex: 1; font-size: 10px; color: {MUTED}; }}
.fyw-conds {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px 24px;
  margin: 16px 0 12px; }}
.fyw-k {{ font-size: 12px; color: {MUTED}; }}
.fyw-v {{ font-size: 14px; font-weight: 600; color: {INK}; }}
.fyw-expl {{ font-size: 14px; line-height: 1.55; color: {INK}; margin: 0 0 8px; }}
.fyw-remark {{ font-size: 14px; line-height: 1.5; color: {MUTED}; margin: 6px 0; padding-left: 10px;
  border-left: 3px solid {LINE}; }}
.fyw-warn {{ font-size: 14px; line-height: 1.5; color: {INK}; margin: 6px 0; padding-left: 10px;
  border-left: 3px solid {WARNING}; }}
.fyw-score details {{ margin: 10px 0 6px; }}
.fyw-score summary {{ cursor: pointer; font-size: 14px; font-weight: 600; color: {INK}; }}
.fyw-bar-row {{ display: flex; align-items: center; gap: 12px; margin-top: 10px; font-size: 13px; color: {INK}; }}
.fyw-bar-row .lbl {{ width: 64px; }}
.fyw-bar {{ flex: 1; height: 6px; background: {FIELD}; border-radius: 3px; overflow: hidden; }}
.fyw-bar div {{ height: 6px; background: {OCEAN}; }}
.fyw-bar-row .val {{ width: 30px; text-align: right; color: {MUTED}; }}
.fyw-bar-row .pts {{ width: 40px; text-align: right; font-weight: 700; }}
.fyw-note {{ font-size: 12px; color: {MUTED}; margin-top: 10px; line-height: 1.5; }}

/* Messages, carte, pied de page */
.fyw-empty {{ background: #fff; border-radius: 12px; padding: 18px 20px; font-size: 15px; color: {INK};
  border-left: 4px solid {SCALE[1][2]}; }}
.fyw-section {{ font-weight: 700; font-size: 18px; color: {INK}; margin: 24px 0 2px; }}
.fyw-caption {{ font-size: 13px; color: {MUTED}; margin-bottom: 8px; }}
.fyw-legend {{ display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 12px; color: {INK}; margin-top: 8px; }}
.fyw-legend i {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 5px; }}
.fyw-fresh {{ font-size: 12px; color: {MUTED}; }}
.fyw-stale {{ font-size: 13px; color: {INK}; background: #fff; border-left: 4px solid {WARNING};
  border-radius: 8px; padding: 10px 14px; margin-top: 8px; }}
</style>
"""

STREAKS = [(0.34, 8, SUNSET[0]), (0.44, 4, SUNSET[1]), (0.52, 16, SUNSET[2]), (0.63, 6, SUNSET[3]),
           (0.71, 12, SUNSET[2]), (0.80, 4, SUNSET[3]), (0.87, 9, SUNSET[1])]


def hero_html() -> str:
    """Bandeau d'en-tête : dégradé océan et traînées de coucher de soleil (pose longue)."""
    streaks = "".join(
        f'<div class="fyw-streak" style="top:{top * 100:.0f}%;height:{height}px;'
        f'background:linear-gradient(90deg, {color}00 0%, {color}F2 45%, {color}8C 100%)"></div>'
        for top, height, color in STREAKS)
    return (f'<div class="fyw-hero">{streaks}<div class="fyw-brand">FindYourWave</div>'
            '<div class="fyw-question">Où surfer cette semaine&nbsp;?</div>'
            '<div class="fyw-tagline">Les meilleurs créneaux de Bretagne, heure par heure, selon ton niveau.</div>'
            '</div>')


# ---------------------------------------------------------------------------
# Résultat
# ---------------------------------------------------------------------------
def card_header_html(rec: dict) -> str:
    background, text = score_colors(rec["score"])
    where = ", ".join(str(x) for x in (rec.get("department"), f"{rec['distance_km']} km") if x)
    return (f'<div class="fyw-head"><div class="fyw-rank">{rec["rank"]}</div>'
            f'<div class="fyw-title"><div class="fyw-name">{esc(rec["spot_name"])}</div>'
            f'<div class="fyw-sub"><b>{esc(rec["slot"])}</b>&nbsp;&nbsp;{esc(where)}</div></div>'
            f'<div class="fyw-badge" style="background:{background};color:{text}">{rec["score"]}</div></div>')


def strip_html(rec: dict) -> str:
    """Bande horaire : une case par heure de la plage choisie, créneau recommandé encadré."""
    cells, labels = [], []
    for hour, score in rec["hourly"].items():
        best = " best" if rec["start_hour"] <= hour < rec["end_hour"] else ""
        title = f"{hour} h : {score}/100" if score is not None else f"{hour} h : non surfable"
        cells.append(f'<div class="fyw-cell{best}" title="{esc(title)}" '
                     f'style="background:{score_colors(score)[0]}"></div>')
        labels.append(f"<span>{hour}h</span>" if hour % 2 == 0 else "<span></span>")
    return f'<div class="fyw-strip">{"".join(cells)}</div><div class="fyw-hours">{"".join(labels)}</div>'


def detail_html(rec: dict, conditions: list[tuple[str, str]], explanation: dict) -> str:
    conds = "".join(f'<div><div class="fyw-k">{esc(k)}</div><div class="fyw-v">{esc(v)}</div></div>'
                    for k, v in conditions)
    warnings = ("".join(f'<p class="fyw-remark">{esc(r)}</p>' for r in explanation.get("remarks", []))
                + "".join(f'<p class="fyw-warn">{esc(w)}</p>' for w in explanation["warnings"]))
    bars = "".join(
        f'<div class="fyw-bar-row"><span class="lbl">{esc(p["label"])}</span>'
        f'<div class="fyw-bar"><div style="width:{max(0, min(100, p["sub_score"])):.0f}%"></div></div>'
        f'<span class="val">{p["sub_score"]:.0f}</span><span class="pts">+{fr_number(p["points"], 0)}</span></div>'
        for p in explanation["contributions"])
    if explanation["onshore_points"] >= 0.5:
        bars += (f'<div class="fyw-bar-row"><span class="lbl">Vent de mer</span><div class="fyw-bar" '
                 f'style="background:transparent"></div><span class="val"></span>'
                 f'<span class="pts">−{fr_number(explanation["onshore_points"], 0)}</span></div>')
    return (f'{strip_html(rec)}<div class="fyw-conds">{conds}</div>'
            f'<p class="fyw-expl">{esc(explanation["summary"])}</p>{warnings}'
            f'<div class="fyw-score"><details><summary>Détail du score</summary>{bars}'
            '<div class="fyw-note">Contribution = sous-score × poids (houle 40 %, période 20 %, vent 25 %, '
            'marée 15 %). La pénalité de vent de mer s’applique ensuite.</div></details></div>')


def empty_html(message: str) -> str:
    return f'<div class="fyw-empty">{esc(message)}</div>'


def legend_html() -> str:
    items = "".join(f'<span><i style="background:{bg}"></i>{label} ({floor}{"+" if floor == 90 else "–" + str(nxt - 1)})</span>'
                    for (floor, label, bg, _), nxt in zip(SCALE, [None, 90, 75, 60]))
    return f'<div class="fyw-legend">{items}</div>'


# ---------------------------------------------------------------------------
# Carte (données des couches pydeck)
# ---------------------------------------------------------------------------
def map_points(recs: list[dict]) -> list[dict]:
    points = []
    for rec in recs:
        background, text = score_colors(rec["score"])
        points.append({"lon": rec["lon"], "lat": rec["lat"], "rank": str(rec["rank"]),
                       "spot_name": rec["spot_name"], "slot": rec["slot"], "score": rec["score"],
                       "fill": hex_to_rgb(background), "text_color": hex_to_rgb(text)})
    return points


def map_zoom(max_km: float, lat: float = 48.0, width_px: int = 640) -> float:
    """Zoom pour que le cercle de recherche tienne dans la largeur de la carte."""
    meters_per_px = 2.6 * max_km * 1000 / width_px
    zoom = math.log2(156543 * math.cos(math.radians(lat)) / meters_per_px)
    return round(min(10.0, max(5.5, zoom)), 2)
