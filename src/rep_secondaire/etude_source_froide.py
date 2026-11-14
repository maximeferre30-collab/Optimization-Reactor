"""Sensibilité du cycle à la température de l'eau de refroidissement.

Démarche :
1. dimensionnement (design) à la température de référence : on fixe le
   pincement et l'échauffement du condenseur, TESPy en déduit le UA du
   condenseur et le débit d'eau de refroidissement ;
2. hors dimensionnement (offdesign) : UA et débit d'eau sont figés (c'est la
   même installation), seule la température d'entrée de l'eau change.

Le solveur de Newton a besoin d'un bon point de départ : on se déplace
par pas d'au plus 1 K à partir du point de dimensionnement, chaque calcul
partant du précédent.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd

from .parametres import ParametresN4, ParametresRankine
from .rankine_simple import RankineSimple


def creer_modele(params):
    """Cycle complet N4 si les paramètres sont des ParametresN4, sinon cycle simple."""
    if isinstance(params, ParametresN4):
        from .cycle_n4 import CycleN4
        return CycleN4(params)
    return RankineSimple(params)

PAS_MAX_K = 1.0


def _chemin(T_depart: float, T_cible: float) -> list[float]:
    n = max(1, int(np.ceil(abs(T_cible - T_depart) / PAS_MAX_K)))
    return list(np.linspace(T_depart, T_cible, n + 1)[1:])


def balayage_temperature(
    temperatures_C,
    design_path: str | Path,
    params: ParametresRankine | None = None,
) -> pd.DataFrame:
    """Résout le cycle pour chaque température d'eau de refroidissement.

    Retourne un DataFrame indexé par la température d'entrée (°C).
    """
    # Copie : resoudre_offdesign() modifie les paramètres du modèle, il ne
    # faut pas altérer l'objet de l'appelant.
    params = replace(params) if params else ParametresRankine()
    T_ref = params.T_eau_refroidissement_C

    modele = creer_modele(params)
    modele.resoudre()
    modele.sauvegarder_design(design_path)

    cibles = sorted(set(float(t) for t in temperatures_C))
    resultats = {}
    # Deux branches au départ du point de dimensionnement : montante puis
    # descendante (on revient au point de design entre les deux).
    for branche in ([t for t in cibles if t >= T_ref],
                    [t for t in reversed(cibles) if t < T_ref]):
        T_courant = T_ref
        modele.resoudre_offdesign(T_ref)
        for T in branche:
            for T_inter in _chemin(T_courant, T):
                r = modele.resoudre_offdesign(T_inter)
            if T == T_ref:
                r = modele.resoudre_offdesign(T_ref)
            resultats[T] = asdict(r)
            T_courant = T

    df = pd.DataFrame.from_dict(resultats, orient="index").sort_index()
    df.index.name = "T_eau_C"
    return df


def sensibilite(
    df: pd.DataFrame,
    colonne: str = "puissance_electrique_nette_MW",
    T_min: float | None = None,
    T_max: float | None = None,
):
    """Pente moyenne (régression linéaire) de la colonne en fonction de T,
    éventuellement restreinte à [T_min, T_max]."""
    d = df.loc[(T_min if T_min is not None else -np.inf):
               (T_max if T_max is not None else np.inf)]
    pente, _ = np.polyfit(d.index.values, d[colonne].values, 1)
    return pente


def optimum(df: pd.DataFrame, colonne: str = "puissance_electrique_nette_MW"):
    """Température d'eau donnant la puissance maximale, et cette puissance."""
    T = df[colonne].idxmax()
    return T, df.loc[T, colonne]
