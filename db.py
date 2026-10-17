"""Connexion à Supabase et écriture par lots (upsert)."""
import math
import sys

from supabase import Client, create_client

import config

BATCH_SIZE = 500


def get_client() -> Client:
    if not config.SUPABASE_URL or not config.SUPABASE_SECRET_KEY:
        sys.exit(
            "SUPABASE_URL ou SUPABASE_SECRET_KEY manquant : "
            "copie .env.example en .env et remplis les deux valeurs."
        )
    return create_client(config.SUPABASE_URL, config.SUPABASE_SECRET_KEY)


def _clean(value):
    """NaN -> None, pour que Postgres reçoive NULL."""
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def upsert(client: Client, table: str, rows: list[dict], on_conflict: str) -> int:
    """Insère ou met à jour les lignes (clé = on_conflict). Renvoie le nombre de lignes."""
    rows = [{k: _clean(v) for k, v in row.items()} for row in rows]
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start:start + BATCH_SIZE]
        client.table(table).upsert(batch, on_conflict=on_conflict).execute()
    return len(rows)
