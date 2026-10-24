"""FindYourWave : interface Streamlit (maquette C v2).

Lecture seule dans Supabase avec la clé publishable. Le calcul des scores reste
dans le batch (score.py) ; ici on filtre, on choisit et on affiche.

Lancement :
    streamlit run app.py
"""
import datetime as dt
import os

import pandas as pd
import pydeck as pdk
import streamlit as st
from supabase import create_client

import config  # noqa: F401  (charge le fichier .env en local)
import explain
import selection
import ui
from score import LEVELS, fetch_all

st.set_page_config(page_title="FindYourWave", page_icon="🌊", layout="centered")
st.markdown(ui.CSS, unsafe_allow_html=True)

CACHE_SECONDS = 600
STALE_AFTER = dt.timedelta(hours=12)  # au-delà, une collecte a probablement échoué
SCORE_COLUMNS = ["spot_id", "forecast_datetime", "is_eligible", "ineligibility_reason", "swell_score",
                 "swell_direction_score", "period_score", "wind_speed_score", "wind_direction_score",
                 "wind_score", "tide_score", "global_score", "scored_at"]
FORECAST_COLUMNS = ["spot_id", "forecast_datetime", "swell_height_m", "swell_period_s", "swell_direction_deg",
                    "wind_speed_kmh", "wind_direction_deg", "tide_stage", "tide_direction", "water_temp_c"]
NUMERIC = ["swell_score", "swell_direction_score", "period_score", "wind_speed_score", "wind_direction_score",
           "wind_score", "tide_score", "global_score", "swell_height_m", "swell_period_s",
           "swell_direction_deg", "wind_speed_kmh", "wind_direction_deg", "water_temp_c",
           "localisation_lat", "localisation_lon"]


# ---------------------------------------------------------------------------
# Données (Supabase, lecture seule)
# ---------------------------------------------------------------------------
def secret(name: str) -> str:
    """st.secrets (Streamlit Cloud ou .streamlit/secrets.toml), sinon variable d'environnement / .env."""
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:  # pas de fichier secrets.toml en local
        pass
    return os.getenv(name, "")


@st.cache_resource
def client():
    url, key = secret("SUPABASE_URL"), secret("SUPABASE_PUBLISHABLE_KEY")
    if not url or not key:
        st.error("Clés Supabase manquantes : ajoute SUPABASE_URL et SUPABASE_PUBLISHABLE_KEY "
                 "dans .streamlit/secrets.toml (ou dans .env en local).")
        st.stop()
    return create_client(url, key)


def numeric(df: pd.DataFrame) -> pd.DataFrame:
    for column in NUMERIC:
        if column in df:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def load_spots() -> pd.DataFrame:
    rows = (client().table("surf_spot_properties")
            .select("spot_id, spot_name, department, localisation_lat, localisation_lon").execute().data)
    return numeric(pd.DataFrame(rows))


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def load_level(level: str) -> dict | None:
    rows = client().table("surf_level_conditions_reference").select("*").eq("surf_level", level).execute().data
    if not rows:
        return None
    return {k: float(v) if k != "surf_level" and _is_number(v) else v for k, v in rows[0].items()}


def _is_number(value) -> bool:
    if isinstance(value, bool):
        return False
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def load_scores(level: str, start: str, end: str) -> pd.DataFrame:
    rows = fetch_all(client().table("spot_hour_scores").select(", ".join(SCORE_COLUMNS))
                     .eq("surf_level", level).gte("forecast_datetime", start).lt("forecast_datetime", end)
                     .order("spot_id").order("forecast_datetime"))
    return numeric(pd.DataFrame(rows, columns=SCORE_COLUMNS))


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def load_forecasts(start: str, end: str) -> pd.DataFrame:
    rows = fetch_all(client().table("marine_forecast").select(", ".join(FORECAST_COLUMNS))
                     .gte("forecast_datetime", start).lt("forecast_datetime", end)
                     .order("spot_id").order("forecast_datetime"))
    df = numeric(pd.DataFrame(rows, columns=FORECAST_COLUMNS))
    df["forecast_datetime"] = pd.to_datetime(df["forecast_datetime"], utc=True)
    return df


def clean(value):
    """NaN -> None, pour les phrases et l'affichage."""
    return None if isinstance(value, float) and pd.isna(value) else value


# ---------------------------------------------------------------------------
# Formulaire
# ---------------------------------------------------------------------------
today = pd.Timestamp.now(tz=selection.TIMEZONE).date()
last_day = today + dt.timedelta(days=6)  # les scores couvrent 7 jours
DEFAULTS = {"level": "intermediaire", "city": "Lorient", "max_km": 100,
            "days": (today, today + dt.timedelta(days=1)), "hours": (8, 20)}
params = st.session_state.setdefault("params", DEFAULTS.copy())
# Une recherche gardée en mémoire peut dater d'hier : on la ramène dans la fenêtre des scores
params["days"] = tuple(min(max(d, today), last_day) for d in params["days"])

st.html(ui.hero_html())

with st.form("search", border=False):
    level = st.segmented_control("Ton niveau", LEVELS, default=params["level"],
                                 format_func=selection.LEVEL_LABELS.get, selection_mode="single")
    left, right = st.columns(2)
    cities = sorted(selection.CITIES)
    city = left.selectbox("Ville de départ", cities, index=cities.index(params["city"]))
    max_km = right.slider("Distance max", 10, 300, params["max_km"], step=10, format="%d km")
    left, right = st.columns(2)
    days = left.date_input("Dates", value=params["days"], min_value=today, max_value=last_day,
                           format="DD/MM/YYYY")
    hours = right.slider("Horaires", 6, 22, params["hours"], format="%d h")
    if st.form_submit_button("Trouver mes vagues", type="primary", width="stretch"):
        days = tuple(days) if isinstance(days, (tuple, list)) else (days,)
        params = {"level": level or params["level"], "city": city, "max_km": max_km,
                  "days": (days[0], days[-1]) if days else params["days"], "hours": hours}
        st.session_state["params"] = params

# ---------------------------------------------------------------------------
# Recherche
# ---------------------------------------------------------------------------
first, last = params["days"]
first, last = max(first, today), min(last, last_day)
search_days = [first + dt.timedelta(days=i) for i in range((last - first).days + 1)] or [today]
start, end = selection.utc_bounds(search_days)
hour_from, hour_to = params["hours"]

try:
    spots = load_spots()
    level_ref = load_level(params["level"])
    scores = load_scores(params["level"], start.isoformat(), end.isoformat())
    forecasts = load_forecasts(start.isoformat(), end.isoformat())
except Exception as error:  # réseau, clé invalide…
    st.error(f"Impossible de lire les données dans Supabase : {error}")
    st.stop()

results = selection.recommend(scores, spots, params["city"], params["max_km"], search_days,
                              hour_from, hour_to, params["level"])

forecast_index = forecasts.set_index(["spot_id", "forecast_datetime"]) if not forecasts.empty else None
for res in results:
    for rec in res.recommendations:
        cond = {}
        if forecast_index is not None and (rec["spot_id"], rec["best_datetime"]) in forecast_index.index:
            cond = {k: clean(v) for k, v in forecast_index.loc[(rec["spot_id"], rec["best_datetime"])].items()}
        scores_row = {k: clean(v) for k, v in rec["scores"].items()}
        if cond.get("wind_speed_kmh") is not None and cond.get("swell_height_m") is not None:
            rec["conditions"] = explain.conditions_list(cond, scores_row)
            rec["explanation"] = explain.explain(scores_row, cond, level_ref)
        else:  # prévision absente : on affiche quand même le score
            rec["conditions"] = []
            rec["explanation"] = {"summary": "", "remarks": [], "warnings": [], "contributions": explain.contributions(scores_row),
                                  "onshore_factor": 1.0, "onshore_points": 0.0}

# ---------------------------------------------------------------------------
# Affichage
# ---------------------------------------------------------------------------
def show_map(recs: list[dict]) -> None:
    lat, lon = selection.CITIES[params["city"]]
    points = ui.map_points(recs)
    layers = [
        pdk.Layer("ScatterplotLayer", data=[{"lat": lat, "lon": lon}], get_position="[lon, lat]",
                  get_radius=params["max_km"] * 1000, stroked=True, filled=False,
                  get_line_color=ui.hex_to_rgb(ui.OCEAN), line_width_min_pixels=1.5),
        pdk.Layer("ScatterplotLayer", data=[{"lat": lat, "lon": lon}], get_position="[lon, lat]",
                  get_fill_color=ui.hex_to_rgb(ui.INK), get_radius=1, radius_min_pixels=5),
        pdk.Layer("TextLayer", data=[{"lat": lat, "lon": lon, "name": params["city"]}],
                  get_position="[lon, lat]", get_text="name", get_size=13, get_color=ui.hex_to_rgb(ui.INK),
                  get_text_anchor=pdk.types.String("start"), get_pixel_offset=[10, 0], font_family="Montserrat",
                  font_weight=600),
        pdk.Layer("ScatterplotLayer", data=points, get_position="[lon, lat]", get_fill_color="fill",
                  get_radius=1, radius_min_pixels=12, stroked=True, get_line_color=[255, 255, 255],
                  line_width_min_pixels=2, pickable=True),
        pdk.Layer("TextLayer", data=points, get_position="[lon, lat]", get_text="rank", get_size=12,
                  get_color="text_color", font_family="Montserrat", font_weight=800),
    ]
    deck = pdk.Deck(
        layers=layers, map_style=None,  # fond de carte Carto par défaut de Streamlit, sans clé
        initial_view_state=pdk.ViewState(latitude=lat, longitude=lon, zoom=ui.map_zoom(params["max_km"], lat)),
        tooltip={"html": "<b>{spot_name}</b><br/>{slot}, {score}/100",
                 "style": {"fontFamily": "Montserrat", "fontSize": "13px"}},
    )
    st.pydeck_chart(deck, height=380)
    st.html(ui.legend_html())


tabs = st.tabs([explain.fr_short_date(res.day) for res in results])
for tab, res in zip(tabs, results):
    with tab:
        if not res.recommendations:
            st.html(ui.empty_html(res.message))
            continue
        for rec in res.recommendations:
            with st.container(key=f"fyw-card-{res.day.isoformat()}-{rec['rank']}"):
                st.html(ui.card_header_html(rec))
                with st.expander("Voir le détail", expanded=rec["rank"] == 1):
                    st.html(ui.detail_html(rec, rec["conditions"], rec["explanation"]))
        n = len(res.recommendations)
        st.html(f'<div class="fyw-section">Sur la carte</div><div class="fyw-caption">'
                f'{"Le spot" if n == 1 else f"Les {n} spots"} du {explain.fr_date(res.day)}, '
                f'à moins de {params["max_km"]} km de {params["city"]}.</div>')
        show_map(res.recommendations)

# Pied de page : fraîcheur des scores, rafraîchir, export
scored_at = pd.to_datetime(scores["scored_at"], utc=True).max() if not scores.empty else None
st.divider()
left, middle, right = st.columns([2, 1, 1.4], vertical_alignment="center")
if scored_at is not None and not pd.isna(scored_at):
    local = scored_at.tz_convert(selection.TIMEZONE)
    left.html(f'<div class="fyw-fresh">Scores calculés le {explain.fr_datetime(local)}</div>')
else:
    left.html('<div class="fyw-fresh">Aucun score en base pour ces dates.</div>')
if middle.button("Rafraîchir", width="stretch"):
    st.cache_data.clear()
    st.rerun()
export = selection.export_table(results)
right.download_button("Télécharger les résultats (CSV)", export.to_csv(index=False, sep=";").encode("utf-8-sig"),
                      file_name=f"findyourwave_{first.isoformat()}.csv", mime="text/csv",
                      disabled=export.empty, width="stretch")
if scored_at is not None and not pd.isna(scored_at) and pd.Timestamp.now(tz="UTC") - scored_at > STALE_AFTER:
    st.html('<div class="fyw-stale">La dernière mise à jour date de plus de 12 h : la collecte a peut-être '
            'échoué. Les résultats affichés utilisent les derniers scores disponibles.</div>')
