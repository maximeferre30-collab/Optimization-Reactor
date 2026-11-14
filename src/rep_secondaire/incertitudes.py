"""Propagation des incertitudes de modélisation (cycle N4).

- Monte-Carlo par hypercube latin sur les hypothèses incertaines
  (distributions uniformes sur les plages ci-dessous) ;
- analyse « une à la fois » (tornade) : chaque hypothèse à ses bornes, les
  autres à leur valeur nominale.

Grandeurs suivies : courbe P_nette(T_eau), pente moyenne au-dessus de 15 °C,
température d'optimum, puissance au design.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
from scipy.stats import qmc

from .etude_source_froide import balayage_temperature, optimum, sensibilite
from .parametres import ParametresN4

PLAGES = {
    "rendement_isentropique_HP": (0.87, 0.91),
    "rendement_isentropique_BP": (0.89, 0.93),
    "coefficient_baumann": (0.7, 1.3),
    "vitesse_annulaire_design_m_s": (220.0, 280.0),
    "vitesse_annulaire_blocage_m_s": (360.0, 440.0),
    "facteur_pertes_echappement": (0.8, 1.2),
    "part_resistance_cote_eau": (0.35, 0.55),
    "pincement_condenseur_K": (3.0, 5.0),
}
LIBELLES = {
    "rendement_isentropique_HP": "Rendement HP (sec)",
    "rendement_isentropique_BP": "Rendement BP (sec)",
    "coefficient_baumann": "Coefficient de Baumann",
    "vitesse_annulaire_design_m_s": "Vitesse d'échappement au design",
    "vitesse_annulaire_blocage_m_s": "Vitesse de blocage",
    "facteur_pertes_echappement": "Échelle de la courbe EL(V)",
    "part_resistance_cote_eau": "Part de résistance côté eau",
    "pincement_condenseur_K": "Pincement du condenseur",
}
TEMPERATURES = list(range(0, 36))


def echantillons_mc(n: int, graine: int = 2026) -> list[dict]:
    lhs = qmc.LatinHypercube(d=len(PLAGES), seed=graine).random(n)
    bornes = np.array(list(PLAGES.values()))
    x = qmc.scale(lhs, bornes[:, 0], bornes[:, 1])
    return [dict(zip(PLAGES, ligne)) for ligne in x]


def echantillons_tornade() -> list[dict]:
    out = []
    for k, (lo, hi) in PLAGES.items():
        out.append({k: lo, "_tornade": (k, "bas")})
        out.append({k: hi, "_tornade": (k, "haut")})
    return out


def evaluer(args) -> dict:
    """Un calcul complet (design + balayage). Exécuté dans un processus fils."""
    i, surcharges, dossier = args
    surch = {k: v for k, v in surcharges.items() if not k.startswith("_")}
    params = replace(ParametresN4(), **surch)
    try:
        df = balayage_temperature(TEMPERATURES, Path(dossier) / f"design_{i}.json", params)
    except Exception as e:  # un échec est rapporté, pas masqué
        return {"i": i, "surcharges": surcharges, "erreur": repr(e)}
    T_opt, P_opt = optimum(df)
    return {
        "i": i,
        "surcharges": surcharges,
        "P_nette": [float(v) for v in df["puissance_electrique_nette_MW"]],
        "pente_15_35": float(sensibilite(df, T_min=15)),
        "T_optimum": float(T_opt),
        "P_optimum": float(P_opt),
        "P_design": float(df.loc[15.0, "puissance_electrique_nette_MW"]),
    }
