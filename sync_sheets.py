"""Google Sheet (référentiels) -> Supabase.

Lit les 3 onglets de référence, les nettoie, vérifie chaque valeur et ne
charge rien si une seule erreur est trouvée (la liste des cellules à corriger
est affichée).

Usage :
    python sync_sheets.py                       # lit le Google Sheet en ligne
    python sync_sheets.py --xlsx matrice.xlsx   # lit un export .xlsx local
    python sync_sheets.py --dry-run             # vérifie sans rien écrire
"""
import argparse
import datetime as dt
import io
import sys
import unicodedata

import pandas as pd
import requests

import config
import db

LEVELS = {"debutant", "intermediaire", "avance", "expert", "pro"}

# Pour chaque table : clé, colonnes (avec leur type) et valeurs autorisées.
TABLES = {
    "surf_spot_properties": {
        "key": "spot_id",
        "tab_prefix": "Ref - surf_spot_properties",
        "columns": {
            "spot_id": "id", "spot_name": "text", "spot_description": "text",
            "department": "text", "localisation_lat": "float", "localisation_lon": "float",
            "spot_orientation_deg": "int", "bottom_type": "enum", "wave_type": "enum",
            "accessibility": "enum",
        },
        "required": ["spot_id", "spot_name", "department", "localisation_lat",
                     "localisation_lon", "spot_orientation_deg", "accessibility"],
        "enums": {
            "bottom_type": {"sable", "roche", "reef", "mixte"},
            "wave_type": {"beachbreak", "reefbreak", "pointbreak"},
            "accessibility": {"facile", "moyenne", "difficile"},
        },
        "ranges": {"localisation_lat": (-90, 90), "localisation_lon": (-180, 180),
                   "spot_orientation_deg": (0, 360)},
    },
    "surf_spot_conditions_reference": {
        "key": "spot_id",
        "tab_prefix": "Ref - surf_spot_conditions_ref",
        "columns": {
            "spot_id": "id", "min_level": "enum",
            "ideal_swell_orientation_min": "int", "ideal_swell_orientation_max": "int",
            "ideal_wind_orientation_min": "int", "ideal_wind_orientation_max": "int",
            "ideal_tide_stage": "enum", "crowd_level": "int",
        },
        "required": ["spot_id", "min_level"],
        "enums": {
            "min_level": LEVELS,
            "ideal_tide_stage": {"basse", "mi-maree", "pleine", "montante", "descendante", "toutes"},
        },
        "ranges": {c: (0, 360) for c in ["ideal_swell_orientation_min", "ideal_swell_orientation_max",
                                          "ideal_wind_orientation_min", "ideal_wind_orientation_max"]}
                  | {"crowd_level": (1, 5)},
    },
    "surf_level_conditions_reference": {
        "key": "surf_level",
        "tab_prefix": "Ref - surf_level_conditions_ref",
        "columns": {
            "surf_level": "enum",
            "swell_height_min": "float", "swell_height_ideal_min": "float",
            "swell_height_ideal_max": "float", "swell_height_max": "float",
            "period_min": "float", "period_ideal_min": "float",
            "period_ideal_max": "float", "period_max": "float",
            "wind_speed_ideal_max": "float", "wind_speed_max": "float",
        },
        "required": "all",
        "enums": {"surf_level": LEVELS},
        "ranges": {c: (0, 10) for c in ["swell_height_min", "swell_height_ideal_min",
                                         "swell_height_ideal_max", "swell_height_max"]}
                  | {c: (0, 30) for c in ["period_min", "period_ideal_min", "period_ideal_max", "period_max"]}
                  | {"wind_speed_ideal_max": (0, 150), "wind_speed_max": (0, 150)},
    },
}


def normalize_text(value: str) -> str:
    """'Intermédiaire ' -> 'intermediaire', 'Mi-marée' -> 'mi-maree'."""
    value = unicodedata.normalize("NFKD", str(value).strip().lower())
    return "".join(c for c in value if not unicodedata.combining(c))


def normalize_header(name) -> str:
    """'period_min (sec)' -> 'period_min'."""
    name = str(name).replace("\ufeff", "").strip()
    return name.split(" (")[0].strip()


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------
def read_from_google(table: str) -> pd.DataFrame:
    gid = config.SHEET_GIDS[table]
    if not gid:
        sys.exit(f"gid manquant pour l'onglet {table} : renseigne-le dans .env (voir .env.example).")
    url = f"https://docs.google.com/spreadsheets/d/{config.SHEET_ID}/export?format=csv&gid={gid}"
    resp = requests.get(url, timeout=30)
    if resp.status_code != 200 or resp.text.lstrip().startswith("<"):
        sys.exit(
            f"Impossible de lire l'onglet {table} (HTTP {resp.status_code}). "
            "Vérifie que le Sheet est partagé en « Tous les utilisateurs disposant du lien : lecteur »."
        )
    raw = pd.read_csv(io.StringIO(resp.text), dtype=str, keep_default_na=False, header=None)
    return promote_header(raw.replace("", None), table, f"l'onglet gid={gid}")


def promote_header(raw: pd.DataFrame, table: str, where: str) -> pd.DataFrame:
    """Trouve la ligne d'en-tête (celle qui contient la clé, ex. spot_id), même
    s'il y a des lignes ou des colonnes vides avant le tableau."""
    key = TABLES[table]["key"]
    raw = raw.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
    for i in range(min(len(raw), 20)):
        headers = [normalize_header(v) if v is not None and not pd.isna(v) else "" for v in raw.iloc[i]]
        if key in headers:
            df = raw.iloc[i + 1:].reset_index(drop=True)
            df.columns = headers
            return df.loc[:, [c for c in df.columns if c]]
    first = [str(v) for v in raw.iloc[0].tolist()[:4]] if len(raw) else []
    sys.exit(
        f"{table} : colonne « {key} » introuvable dans {where}. "
        f"Début de l'onglet lu : {first}. Vérifie que le gid pointe bien vers l'onglet « {TABLES[table]['tab_prefix']}… »."
    )


def read_from_xlsx(path: str, table: str) -> pd.DataFrame:
    prefix = TABLES[table]["tab_prefix"]
    sheets = pd.read_excel(path, sheet_name=None, header=None, dtype=object)
    for name, raw in sheets.items():
        if name.strip().startswith(prefix):
            return promote_header(raw, table, f"l'onglet « {name} »")
    sys.exit(f"Onglet commençant par « {prefix} » introuvable dans {path}.")


# ---------------------------------------------------------------------------
# Nettoyage + contrôles
# ---------------------------------------------------------------------------
def parse_number(value, kind):
    """Renvoie (nombre, message d'erreur)."""
    if isinstance(value, (dt.date, dt.datetime, pd.Timestamp)):
        return None, f"« {value} » a été transformé en date par Google Sheets"
    text = str(value).strip().replace(",", ".").replace(" ", "")
    if "/" in text:
        return None, f"« {value} » ressemble à une date"
    try:
        number = float(text)
    except ValueError:
        return None, f"« {value} » n'est pas un nombre"
    if kind == "int":
        return int(round(number)), None
    return number, None


def clean_table(table: str, df: pd.DataFrame) -> tuple[list[dict], list[str]]:
    spec = TABLES[table]
    errors = []

    df = df.rename(columns=normalize_header)
    df = df.loc[:, [c for c in df.columns if c and not str(c).startswith("Unnamed") and str(c) != "nan"]]
    missing = [c for c in spec["columns"] if c not in df.columns]
    if missing:
        return [], [f"{table} : colonne(s) absente(s) du Sheet : {', '.join(missing)}"]

    required = list(spec["columns"]) if spec["required"] == "all" else spec["required"]
    rows = []
    for line_no, raw in enumerate(df.to_dict("records"), start=2):
        key_value = raw.get(spec["key"])
        if key_value is None or str(key_value).strip() in ("", "nan"):
            continue  # ligne vide
        row = {}
        for col, kind in spec["columns"].items():
            value = raw.get(col)
            where = f"{table}, ligne {line_no} ({key_value}), colonne {col}"
            if value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() in ("", "nan"):
                if col in required:
                    errors.append(f"{where} : valeur obligatoire vide")
                row[col] = None
                continue
            if kind == "id":
                row[col] = normalize_text(value).replace(" ", "_")
            elif kind == "enum":
                row[col] = normalize_text(value)
                if row[col] not in spec["enums"][col]:
                    errors.append(f"{where} : « {value} » n'est pas dans {sorted(spec['enums'][col])}")
            elif kind == "text":
                row[col] = str(value).strip()
            else:
                number, err = parse_number(value, kind)
                if err:
                    errors.append(f"{where} : {err}")
                elif col in spec["ranges"]:
                    low, high = spec["ranges"][col]
                    if not low <= number <= high:
                        errors.append(f"{where} : {number} hors de l'intervalle {low}–{high}")
                row[col] = number
        rows.append(row)

    keys = [r[spec["key"]] for r in rows]
    for dup in sorted({k for k in keys if keys.count(k) > 1}):
        errors.append(f"{table} : {spec['key']} « {dup} » en double")
    if table == "surf_level_conditions_reference" and not errors:
        errors += check_level_order(rows)
    return rows, errors


def check_level_order(rows):
    errors = []
    orders = [
        ["swell_height_min", "swell_height_ideal_min", "swell_height_ideal_max", "swell_height_max"],
        ["period_min", "period_ideal_min", "period_ideal_max", "period_max"],
        ["wind_speed_ideal_max", "wind_speed_max"],
    ]
    for row in rows:
        for cols in orders:
            values = [row[c] for c in cols]
            if values != sorted(values):
                errors.append(f"surf_level_conditions_reference ({row['surf_level']}) : "
                              f"il faut {' ≤ '.join(cols)}, lu {values}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--xlsx", help="chemin d'un export .xlsx du Sheet (sinon lecture en ligne)")
    parser.add_argument("--dry-run", action="store_true", help="vérifie sans écrire dans Supabase")
    args = parser.parse_args()

    cleaned, all_errors = {}, []
    for table in TABLES:
        df = read_from_xlsx(args.xlsx, table) if args.xlsx else read_from_google(table)
        rows, errors = clean_table(table, df)
        cleaned[table] = rows
        all_errors += errors
        print(f"{table} : {len(rows)} ligne(s) lue(s)")

    spot_ids = {r["spot_id"] for r in cleaned["surf_spot_properties"]}
    for row in cleaned["surf_spot_conditions_reference"]:
        if row["spot_id"] not in spot_ids:
            all_errors.append(f"surf_spot_conditions_reference : spot « {row['spot_id']} » "
                              "absent de surf_spot_properties")

    if all_errors:
        print("\nRien n'a été chargé. À corriger dans le Sheet :")
        for err in all_errors:
            print(f"  - {err}")
        sys.exit(1)

    if args.dry_run:
        print("\nTout est valide (dry-run : rien n'a été écrit).")
        return

    client = db.get_client()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    for table in TABLES:  # ordre important : les spots avant leurs conditions
        rows = [r | {"updated_at": now} for r in cleaned[table]]
        n = db.upsert(client, table, rows, on_conflict=TABLES[table]["key"])
        print(f"{table} : {n} ligne(s) chargée(s) dans Supabase")


if __name__ == "__main__":
    main()
