"""Calcul de la marée (tide_level_pct, tide_direction, tide_stage) à partir de
sea_level_height_m, selon la section « Calcul de tide_stage » du doc."""


def _find_extremes(levels):
    """Renvoie [(index, 'basse'|'pleine'), ...] : minima et maxima locaux."""
    extremes = []
    for i in range(1, len(levels) - 1):
        prev, cur, nxt = levels[i - 1], levels[i], levels[i + 1]
        if prev is None or cur is None or nxt is None:
            continue
        if prev == cur == nxt:
            continue
        if cur <= prev and cur <= nxt:
            extremes.append((i, "basse"))
        elif cur >= prev and cur >= nxt:
            extremes.append((i, "pleine"))

    # Deux extrêmes consécutifs du même type (palier) : on garde le plus extrême
    kept = []
    for idx, kind in extremes:
        if kept and kept[-1][1] == kind:
            last_idx = kept[-1][0]
            more_extreme = levels[idx] < levels[last_idx] if kind == "basse" else levels[idx] > levels[last_idx]
            if more_extreme:
                kept[-1] = (idx, kind)
        else:
            kept.append((idx, kind))
    return kept


def stage_from_pct(pct):
    if pct is None:
        return None
    if pct < 0.3:
        return "basse"
    if pct > 0.7:
        return "pleine"
    return "mi-maree"


def compute_tide(levels):
    """levels : hauteurs d'eau horaires triées par date (None si absente).

    Renvoie trois listes de même longueur : tide_level_pct (0 = basse mer,
    1 = pleine mer), tide_direction et tide_stage. Les heures avant le premier
    extrême ou après le dernier restent à None.
    """
    n = len(levels)
    pct = [None] * n
    direction = [None] * n
    extremes = _find_extremes(levels)

    for (a, kind_a), (b, _) in zip(extremes, extremes[1:]):
        start, end = levels[a], levels[b]
        rising = kind_a == "basse"
        for i in range(a, b + 1):
            if levels[i] is None or end == start:
                continue
            progression = (levels[i] - start) / (end - start)
            progression = min(max(progression, 0.0), 1.0)
            pct[i] = round(progression if rising else 1 - progression, 3)
            direction[i] = "montante" if rising else "descendante"

    # Le dernier extrême garde sinon le sens du segment qui y mène : comme pour les
    # extrêmes intermédiaires, une pleine mer est le début de la descente (et inversement).
    if len(extremes) >= 2:
        last, kind = extremes[-1]
        if pct[last] is not None:
            direction[last] = "descendante" if kind == "pleine" else "montante"

    stage = [stage_from_pct(p) for p in pct]
    return pct, direction, stage
