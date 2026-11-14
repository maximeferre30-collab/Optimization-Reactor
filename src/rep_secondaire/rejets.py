"""Limites réglementaires de rejet thermique (variante en circuit ouvert).

Les tranches N4 réelles sont refroidies par tours : l'essentiel de la chaleur
part dans l'air et la limite thermique en rivière pèse peu. Ce module étudie
la variante « bord de rivière » (eau du condenseur prélevée et rendue à la
rivière), où ces limites provoquent les baisses de production estivales.

Bilan de mélange complet en aval du rejet :
    ΔT_riviere = Q_cond / (ρ · cp · Q_riviere)
Contraintes (valeurs ILLUSTRATIVES, chaque site a son arrêté de rejet) :
    ΔT_riviere ≤ ΔT_max      et      T_riviere + ΔT_riviere ≤ T_aval_max
Si une contrainte est active, on réduit la puissance du réacteur d'un
facteur f. On suppose le rendement constant à charge partielle, donc
Q_cond ∝ f et P ∝ f. C'est une approximation au premier ordre : le
rendement réel baisse un peu à charge partielle.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

RHO_CP = 1000.0 * 4186.0  # J/m³/K


@dataclass
class LimitesRejet:
    dT_max_K: float = 3.0
    T_aval_max_C: float = 28.0


def facteur_puissance(T_riv, Q_riv_m3s, Q_cond_MW, lim: LimitesRejet):
    """Fraction de la puissance nominale autorisée (0 à 1)."""
    T_riv = np.asarray(T_riv, float)
    Q_riv = np.asarray(Q_riv_m3s, float)
    capacite = RHO_CP * Q_riv / 1e6  # MW/K
    f_dT = lim.dT_max_K * capacite / Q_cond_MW
    f_Taval = np.maximum(lim.T_aval_max_C - T_riv, 0.0) * capacite / Q_cond_MW
    return np.clip(np.minimum(f_dT, f_Taval), 0.0, 1.0)


def carte_puissance(courbes, Q_cond_de_T, T_riv, Q_riv, lim: LimitesRejet):
    """P admissible (MWe) sur une grille (T rivière, débit rivière), en
    circuit ouvert : l'eau du condenseur est l'eau de la rivière."""
    TT, QQ = np.meshgrid(T_riv, Q_riv, indexing="ij")
    Qc = Q_cond_de_T(TT)
    f = facteur_puissance(TT, QQ, Qc, lim)
    return f * courbes.P(TT), f
