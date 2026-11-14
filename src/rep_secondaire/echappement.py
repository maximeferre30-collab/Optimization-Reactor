"""Pertes d'échappement de la turbine basse pression (BP).

Une partie de l'énergie de la vapeur n'est pas convertie en travail à la
sortie du dernier étage BP :
- l'énergie cinétique de sortie (« leaving loss »), en ~V²/2 ;
- aux faibles vitesses, des pertes de décollement et de recirculation
  (« turn-up loss ») ;
- au-delà d'une vitesse limite, l'écoulement est bloqué (régime sonique dans
  l'aubage terminal). Baisser encore la pression au condenseur ne produit
  alors plus de travail : la détente supplémentaire se fait hors des aubes.

Méthode de Spencer-Cotton-Cannon (SCC, 1963), utilisée par les
constructeurs pour les bilans de turbines à vapeur :
    ELEP  « expansion line end point »   : sortie de la ligne de détente
    UEEP  « used energy end point »      : état réel envoyé au condenseur
    h_UEEP = h_ELEP + EL(V) * 0,87 * (1 - 0,01 Y) * (1 - 0,0065 Y)
avec V la vitesse axiale dans la section annulaire de sortie et Y
l'humidité en % au point ELEP.

La courbe EL(V) ci-dessous est GÉNÉRIQUE : elle reproduit la forme
caractéristique des courbes SCC (minimum vers 150-200 m/s, remontée aux
faibles vitesses, croissance rapide vers le blocage). Elle n'est pas
calée sur la turbine Arabelle du N4, dont les courbes ne sont pas publiques.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from CoolProp.CoolProp import PropsSI
from scipy.optimize import brentq

# Vitesse annulaire (m/s) -> perte d'échappement (kJ/kg de vapeur à l'échappement)
_V = np.array([60, 90, 120, 150, 180, 210, 240, 270, 300, 330, 360, 400])
_EL = np.array([60, 40, 28, 23, 22, 24, 28, 35, 44, 56, 70, 92])


def perte_echappement_kJ_kg(V: float) -> float:
    """Perte brute EL(V) de la courbe générique (bornée aux extrémités)."""
    return float(np.interp(V, _V, _EL))


def facteur_humidite(Y_pourcent: float) -> float:
    """Facteur SCC : une partie de la perte est déjà comptée dans la ligne
    de détente humide."""
    return 0.87 * (1 - 0.01 * Y_pourcent) * (1 - 0.0065 * Y_pourcent)


@dataclass
class EtatEchappement:
    vitesse_annulaire_m_s: float
    bloque: bool
    p_blocage_bar: float  # nan si non bloqué
    perte_MW: float  # puissance perdue (retirée à l'arbre, rendue au fluide)


class LigneDetente:
    """Ligne de détente de la turbine, pour calculer l'état ELEP à une
    pression quelconque (utile pour chercher la pression de blocage)."""

    def __init__(self, p_entree_Pa: float, h_entree: float, eta_s: float):
        self.h1 = h_entree
        self.s1 = PropsSI("S", "P", p_entree_Pa, "H", h_entree, "water")
        self.eta = eta_s

    def h(self, p_Pa: float) -> float:
        h_s = PropsSI("H", "P", p_Pa, "S", self.s1, "water")
        return self.h1 - self.eta * (self.h1 - h_s)

    def volume_massique(self, p_Pa: float) -> float:
        return 1.0 / PropsSI("D", "P", p_Pa, "H", self.h(p_Pa), "water")

    def humidite_pourcent(self, p_Pa: float) -> float:
        x = PropsSI("Q", "P", p_Pa, "H", self.h(p_Pa), "water")
        return 100.0 * (1.0 - min(max(x, 0.0), 1.0))


def section_annulaire(m: float, ligne: LigneDetente, p_Pa: float, V_design: float) -> float:
    """Section annulaire totale (m²) qui donne V_design au point de design."""
    return m * ligne.volume_massique(p_Pa) / V_design


def etat_echappement(
    m: float,
    ligne: LigneDetente,
    p_cond_Pa: float,
    section_m2: float,
    V_blocage: float,
) -> EtatEchappement:
    def vitesse(p):
        return m * ligne.volume_massique(p) / section_m2

    V = vitesse(p_cond_Pa)
    if V <= V_blocage:
        Y = ligne.humidite_pourcent(p_cond_Pa)
        perte = m * perte_echappement_kJ_kg(V) * facteur_humidite(Y) * 1e3
        return EtatEchappement(V, False, float("nan"), perte / 1e6)

    # Écoulement bloqué : la turbine ne « voit » pas en dessous de p*.
    p_star = brentq(lambda p: vitesse(p) - V_blocage, p_cond_Pa, 10 * p_cond_Pa + 1e4)
    Y = ligne.humidite_pourcent(p_star)
    travail_non_recupere = m * (ligne.h(p_star) - ligne.h(p_cond_Pa))
    perte = travail_non_recupere + m * perte_echappement_kJ_kg(V_blocage) * facteur_humidite(Y) * 1e3
    return EtatEchappement(V_blocage, True, p_star / 1e5, perte / 1e6)
