"""Explication d'une recommandation : phrases en français tirées de templates, sans IA.

Section « Génération de l'explication de la recommandation » du doc :
- on cite les 2 critères qui contribuent le plus au score global ;
- puis tout sous-score < 50 comme point de vigilance ;
- et le vent de mer quand il retire une part notable du score (facteur onshore).

Le module ne lit rien en base : il reçoit les sous-scores d'une heure
(spot_hour_scores) et les conditions prévues de la même heure (marine_forecast).
"""
import datetime as dt

from score import CALM_WIND_KMH, WEIGHTS, onshore_factor

CRITERIA = {  # clé de WEIGHTS -> (libellé, colonne de spot_hour_scores)
    "swell": ("Houle", "swell_score"),
    "period": ("Période", "period_score"),
    "wind": ("Vent", "wind_score"),
    "tide": ("Marée", "tide_score"),
}
WARNING_BELOW = 50       # sous-score en dessous duquel on signale un point de vigilance (barre rose)
REMARK_BELOW = 70        # entre 50 et 70 : une remarque qui dit pourquoi le critère n'est pas idéal
ONSHORE_MENTION = 0.95   # on parle du vent de mer s'il retire au moins 5 % du score
MISALIGNED_SWELL = 80    # swell_direction_score sous lequel la houle est « mal orientée »
EFFECTIVE_SHOWN = 95     # en dessous, on affiche aussi la hauteur utile (hauteur × facteur de direction)

DIRECTIONS = ["nord", "nord-est", "est", "sud-est", "sud", "sud-ouest", "ouest", "nord-ouest"]
WEEKDAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
          "septembre", "octobre", "novembre", "décembre"]
SHORT_MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août",
                "sept.", "oct.", "nov.", "déc."]


# ---------------------------------------------------------------------------
# Libellés
# ---------------------------------------------------------------------------
def fr_number(x: float, decimals: int = 1) -> str:
    """0.84 -> '0,8' ; 1.0 -> '1' ; 11.1 (decimals=0) -> '11'."""
    text = f"{x:.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def direction_name(degrees: float) -> str:
    return DIRECTIONS[round(degrees / 45) % 8]


def from_direction(degrees: float) -> str:
    """Provenance : 'du nord', 'd'ouest', 'de sud-ouest'."""
    name = direction_name(degrees)
    if name in ("nord", "sud"):
        return f"du {name}"
    if name in ("est", "ouest"):
        return f"d’{name}"
    return f"de {name}"


def tide_label(stage: str | None, direction: str | None) -> str:
    """('mi-maree', 'montante') -> 'mi-marée montante' ; ('basse', 'descendante') -> 'marée basse, descendante'."""
    base = {"basse": "marée basse", "mi-maree": "mi-marée", "pleine": "pleine mer"}.get(stage or "")
    if base is None:
        return f"marée {direction}" if direction else "marée inconnue"
    if not direction:
        return base
    return f"{base} {direction}" if stage == "mi-maree" else f"{base}, {direction}"


def fr_date(day: dt.date) -> str:
    """mardi 20 octobre"""
    return f"{WEEKDAYS[day.weekday()]} {day.day} {MONTHS[day.month - 1]}"


def fr_short_date(day: dt.date) -> str:
    """mar. 20"""
    return f"{WEEKDAYS[day.weekday()][:3].capitalize()}. {day.day}"


def fr_datetime(moment: dt.datetime) -> str:
    """20 oct. à 13 h 02"""
    return f"{moment.day} {SHORT_MONTHS[moment.month - 1]} à {moment.hour} h {moment.minute:02d}"


def slot_label(start_hour: int, end_hour: int) -> str:
    return f"{start_hour} h – {end_hour} h"


def spot_height(cond: dict, scores: dict | None) -> float | None:
    """Hauteur sur le spot = hauteur au large × facteur de direction : c'est elle que juge le
    scoring (éligibilité et score de houle). None sans scores."""
    factor = (scores or {}).get("swell_direction_score")
    if factor is None:
        return None
    return cond["swell_height_m"] * factor / 100


def effective_height(cond: dict, scores: dict | None) -> float | None:
    """Hauteur sur le spot quand la houle arrive hors de la fenêtre du spot ; None si elle est
    bien orientée (les deux hauteurs sont alors égales)."""
    factor = (scores or {}).get("swell_direction_score")
    if factor is None or factor >= EFFECTIVE_SHOWN:
        return None
    return spot_height(cond, scores)


def conditions_list(cond: dict, scores: dict | None = None) -> list[tuple[str, str]]:
    """Conditions prévues à afficher : [('Houle au large', '2,1 m, 9 s de nord-ouest'),
    ('Houle sur le spot', '0,8 m, mal orientée'), ...]. Sans scores, une seule ligne « Houle »."""
    offshore = (f"{fr_number(cond['swell_height_m'])} m, {fr_number(cond['swell_period_s'], 0)} s "
                f"{from_direction(cond['swell_direction_deg'])}")
    on_spot = spot_height(cond, scores)
    if on_spot is None:
        swell_items = [("Houle", offshore)]
    else:
        aligned = scores["swell_direction_score"] >= EFFECTIVE_SHOWN
        swell_items = [("Houle au large", offshore),
                       ("Houle sur le spot", f"{fr_number(on_spot)} m, "
                                             f"{'bien orientée' if aligned else 'mal orientée'}")]
    items = [
        *swell_items,
        ("Vent", _wind_text(cond)),
        ("Marée", tide_label(cond.get("tide_stage"), cond.get("tide_direction"))),
    ]
    if cond.get("water_temp_c") is not None:
        items.append(("Eau", f"{fr_number(cond['water_temp_c'], 0)} °C"))
    return items


def _wind_text(cond: dict) -> str:
    speed = cond["wind_speed_kmh"]
    if speed < CALM_WIND_KMH:
        return f"{fr_number(speed, 0)} km/h"
    return f"{fr_number(speed, 0)} km/h {from_direction(cond['wind_direction_deg'])}"


# ---------------------------------------------------------------------------
# Détail du score
# ---------------------------------------------------------------------------
def contributions(scores: dict) -> list[dict]:
    """Contribution de chaque critère au score global, en points sur 100 (sous-score × poids)."""
    return [{"key": key, "label": label, "sub_score": scores[column], "weight": WEIGHTS[key],
             "points": round(scores[column] * WEIGHTS[key], 1)}
            for key, (label, column) in CRITERIA.items()]


def onshore_penalty(scores: dict, wind_speed_kmh: float) -> tuple[float, float]:
    """(facteur vent de mer, points retirés). Somme des contributions − points retirés = score global."""
    factor = onshore_factor(scores["wind_direction_score"], wind_speed_kmh)
    total = sum(scores[column] * WEIGHTS[key] for key, (_, column) in CRITERIA.items())
    return factor, round(total * (1 - factor), 1)


# ---------------------------------------------------------------------------
# Phrases
# ---------------------------------------------------------------------------
def _quality(sub_score: float, ideal: str, good: str, fair: str) -> str:
    if sub_score >= 90:
        return ideal
    if sub_score >= 70:
        return good
    return fair


def _wind_kind(direction_score: float) -> str:
    if direction_score >= 90:
        return "vent de terre"
    if direction_score >= 60:
        return "vent de travers"
    return "vent de mer"


def _wind_strength(speed: float) -> str:
    if speed <= 12:
        return "léger"
    if speed <= 25:
        return "modéré"
    return "fort"


def _positive(key: str, scores: dict, cond: dict, level_ref: dict | None = None) -> str:
    """Description d'un critère qui contribue au score (phrase principale)."""
    sub = scores[CRITERIA[key][1]]
    if key == "swell":
        what = _quality(sub, "houle idéale pour ton niveau", "bonne houle pour ton niveau", "houle correcte")
        on_spot = spot_height(cond, scores)
        edge = _ideal_edge(on_spot, level_ref) if sub >= 90 else None
        if edge:  # dans la fourchette idéale, mais tout près d'une borne : on le dit
            low, high = level_ref["swell_height_ideal_min"], level_ref["swell_height_ideal_max"]
            return (f"houle dans la fourchette idéale pour ton niveau, mais {edge} "
                    f"({fr_number(on_spot)} m sur le spot, idéal de {fr_number(low)} à {fr_number(high)} m)")
        if sub < 70 and level_ref and on_spot is not None:  # dire pourquoi elle n'est que correcte
            if on_spot > level_ref["swell_height_ideal_max"]:
                what = "houle correcte, un peu grosse pour ton niveau"
            elif on_spot < level_ref["swell_height_ideal_min"]:
                what = "houle correcte, un peu petite pour ton niveau"
        effective = effective_height(cond, scores)
        if effective is not None:
            # houle mal orientée : le scoring juge la hauteur utile, pas la hauteur au large
            return (f"{what} sur ce spot (environ {fr_number(effective)} m utiles : "
                    f"{fr_number(cond['swell_height_m'])} m au large {from_direction(cond['swell_direction_deg'])}, "
                    "en partie hors de la fenêtre du spot)")
        return f"{what} ({fr_number(cond['swell_height_m'])} m {from_direction(cond['swell_direction_deg'])})"
    if key == "period":
        period = fr_number(cond["swell_period_s"], 0)
        if sub >= 90:
            return f"période idéale ({period} s) pour des vagues bien formées"
        if sub < REMARK_BELOW:
            return f"période {'un peu courte' if _short_period(cond, level_ref) else 'un peu longue'} ({period} s)"
        return f"bonne période ({period} s)"
    if key == "wind":
        speed = cond["wind_speed_kmh"]
        if speed < CALM_WIND_KMH:
            return "vent quasi nul"
        return (f"{_wind_kind(scores['wind_direction_score'])} {_wind_strength(round(speed))} "
                f"({fr_number(speed, 0)} km/h {from_direction(cond['wind_direction_deg'])})")
    tide = tide_label(cond.get("tide_stage"), cond.get("tide_direction"))
    if sub >= 90:
        return f"marée idéale pour ce spot ({tide})"
    if sub >= 70:
        return f"bonne hauteur de marée ({tide})"
    return f"marée un peu en dehors de la fenêtre idéale du spot ({tide})"


IDEAL_EDGE = 0.2  # dans les 20 % du bas ou du haut de la fourchette idéale de houle, on le précise


def _ideal_edge(on_spot: float | None, level_ref: dict | None) -> str | None:
    """'en bas de fourchette' / 'en haut de fourchette' si la houle sur le spot est dans l'idéal
    du niveau mais près d'une borne ; None sinon."""
    if on_spot is None or not level_ref:
        return None
    low, high = level_ref["swell_height_ideal_min"], level_ref["swell_height_ideal_max"]
    if high <= low or not low <= on_spot <= high:
        return None
    position = (on_spot - low) / (high - low)
    if position < IDEAL_EDGE:
        return "en bas de fourchette"
    if position > 1 - IDEAL_EDGE:
        return "en haut de fourchette"
    return None


def _short_period(cond: dict, level_ref: dict | None) -> bool:
    return cond["swell_period_s"] < (level_ref["period_ideal_min"] if level_ref else 8)


def _remark(key: str, scores: dict, cond: dict, level_ref: dict | None, onshore_mentioned: bool) -> str | None:
    """Raison d'un critère noté entre WARNING_BELOW et REMARK_BELOW (remarque, ton neutre)."""
    if key == "swell":
        on_spot = spot_height(cond, scores) or cond["swell_height_m"]
        if effective_height(cond, scores) is not None:
            return (f"houle en partie mal orientée pour ce spot ({fr_number(on_spot)} m sur le spot pour "
                    f"{fr_number(cond['swell_height_m'])} m au large) : vagues plus petites")
        if level_ref and on_spot > level_ref["swell_height_ideal_max"]:
            return f"houle un peu grosse pour ton niveau ({fr_number(on_spot)} m sur le spot)"
        if level_ref and on_spot < level_ref["swell_height_ideal_min"]:
            return f"houle un peu petite pour ton niveau ({fr_number(on_spot)} m sur le spot)"
        return f"houle un peu en dehors de l’idéal ({fr_number(on_spot)} m sur le spot)"
    if key == "period":
        period = fr_number(cond["swell_period_s"], 0)
        if _short_period(cond, level_ref):
            return f"période un peu courte ({period} s) : vagues moins puissantes"
        return f"période longue ({period} s) : séries plus puissantes et espacées"
    if key == "wind":
        speed = cond["wind_speed_kmh"]
        if _value(scores, "wind_speed_score") < REMARK_BELOW:
            return f"vent un peu soutenu pour ton niveau ({fr_number(speed, 0)} km/h)"
        if onshore_mentioned:
            return None  # déjà dit par la phrase sur le vent de mer
        kind = _wind_kind(_value(scores, "wind_direction_score"))
        return (f"{kind} ({fr_number(speed, 0)} km/h {from_direction(cond['wind_direction_deg'])}) : "
                "vagues un peu moins propres")
    return (f"marée un peu en dehors de la fenêtre idéale du spot "
            f"({tide_label(cond.get('tide_stage'), cond.get('tide_direction'))})")


def _value(scores: dict, column: str, default: float = 100.0) -> float:
    value = scores.get(column)
    return default if value is None else value


def _warning(key: str, scores: dict, cond: dict, level_ref: dict | None, onshore_mentioned: bool) -> str | None:
    """Description d'un critère noté sous WARNING_BELOW (point de vigilance)."""
    if key == "swell":
        height = cond["swell_height_m"]
        text = f"{fr_number(height)} m {from_direction(cond['swell_direction_deg'])}"
        if _value(scores, "swell_direction_score") < MISALIGNED_SWELL:
            return f"houle mal orientée pour ce spot ({text})"
        if level_ref:
            on_spot = height * _value(scores, "swell_direction_score") / 100
            if on_spot < level_ref["swell_height_ideal_min"]:
                return (f"houle petite pour ton niveau ({fr_number(on_spot)} m sur le spot, idéal à partir de "
                        f"{fr_number(level_ref['swell_height_ideal_min'])} m)")
            if on_spot > level_ref["swell_height_ideal_max"]:
                return (f"houle grosse pour ton niveau ({fr_number(on_spot)} m sur le spot, idéal jusqu’à "
                        f"{fr_number(level_ref['swell_height_ideal_max'])} m)")
        return f"houle peu favorable ({text})"
    if key == "period":
        period = cond["swell_period_s"]
        short_limit = level_ref["period_ideal_min"] if level_ref else 8
        if period < short_limit:
            return f"période courte ({fr_number(period, 0)} s) : vagues molles et rapprochées"
        return f"période très longue ({fr_number(period, 0)} s) : séries puissantes et espacées"
    if key == "wind":
        speed = cond["wind_speed_kmh"]
        if _value(scores, "wind_speed_score") < WARNING_BELOW:
            return f"vent soutenu pour ton niveau ({fr_number(speed, 0)} km/h)"
        if onshore_mentioned:
            return None  # déjà dit par la phrase sur le vent de mer
        return f"vent mal orienté pour ce spot ({fr_number(speed, 0)} km/h {from_direction(cond['wind_direction_deg'])})"
    return f"marée peu favorable pour ce spot ({tide_label(cond.get('tide_stage'), cond.get('tide_direction'))})"


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:] + "."


def explain(scores: dict, cond: dict, level_ref: dict | None = None) -> dict:
    """Explication d'une heure scorée.

    scores    : ligne de spot_hour_scores (swell_score, period_score, wind_score, tide_score,
                wind_direction_score, wind_speed_score, swell_direction_score, global_score)
    cond      : ligne de marine_forecast de la même heure
    level_ref : ligne de surf_level_conditions_reference du niveau (facultatif, précise
                « houle trop petite / trop grosse » et « période courte »)

    Renvoie {"summary", "remarks", "warnings", "contributions", "onshore_factor", "onshore_points"} :
    remarks pour les sous-scores de 50 à 69 qui ne sont pas déjà dans la phrase principale,
    warnings pour les sous-scores sous 50 et le vent de mer.
    """
    parts = contributions(scores)
    factor, penalty = onshore_penalty(scores, cond["wind_speed_kmh"])
    onshore = factor < ONSHORE_MENTION

    # Phrase principale : les 2 plus fortes contributions parmi les critères notés 50 ou plus
    # (un critère sous 50 n'est pas un point fort : il passe en vigilance). Tri stable.
    top = [p for p in sorted(parts, key=lambda p: -p["points"]) if p["sub_score"] >= WARNING_BELOW][:2]
    summary = (_sentence(" et ".join(_positive(p["key"], scores, cond, level_ref) for p in top)) if top
               else "Aucun critère n’est vraiment favorable sur ce créneau.")

    cited = {p["key"] for p in top}
    remarks = []
    for part in parts:
        if WARNING_BELOW <= part["sub_score"] < REMARK_BELOW and part["key"] not in cited:
            text = _remark(part["key"], scores, cond, level_ref, onshore)
            if text:
                remarks.append(_sentence(text))

    warnings = []
    if onshore:
        warnings.append(f"Vent de mer à {fr_number(cond['wind_speed_kmh'], 0)} km/h : "
                        f"les vagues seront moins propres (−{fr_number(penalty, 0)} points).")
    for part in parts:
        if part["sub_score"] < WARNING_BELOW:
            text = _warning(part["key"], scores, cond, level_ref, onshore)
            if text:
                warnings.append(_sentence(text))

    return {"summary": summary, "remarks": remarks, "warnings": warnings, "contributions": parts,
            "onshore_factor": round(factor, 3), "onshore_points": penalty}
