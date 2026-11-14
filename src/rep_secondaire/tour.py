"""Tour aéroréfrigérante humide à tirage naturel (méthode de Merkel).

Les tranches N4 (Chooz B, Civaux) sont refroidies en circuit fermé par des
tours. L'eau froide qui entre au condenseur ne dépend donc pas directement de
la rivière, mais de l'air : température sèche, humidité, pression.

Modèle
------
1. Merkel (contre-courant, Le = 1, évaporation négligée dans le bilan d'eau) :
       Me = ∫_{Tf}^{Tc} cp dT / (h_s(T) − h_a(T)),
       h_a(T) = h_a,e + (L/G) · cp · (T − Tf)
   h_s : enthalpie de l'air saturé à la température de l'eau ; h_a,e :
   enthalpie de l'air entrant. Intégrale par Tchebychev à 4 points (norme
   CTI ATC-105).
2. Caractéristique de la tour : Me = Me_d · ((L/G) / (L/G)_d)^(-n), n = 0,6.
3. Tirage naturel : le débit d'air vérifie ΔP_tirage = g·H·(ρ_amb − ρ_sortie)
   = k·G², donc G = G_d · sqrt(Δρ / Δρ_d). L'air sort saturé, à l'enthalpie
   h_a,s = h_a,e + (L/G)·cp·(Tc − Tf).

Hypothèses : débit d'eau constant, hauteur et pertes de charge de la tour
fixes, Le = 1. Propriétés de l'air humide : CoolProp (HAPropsSI).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from CoolProp.CoolProp import HAPropsSI, PropsSI
from scipy.optimize import brentq

CP_EAU = 4186.0  # J/kg/K, constant sur 0-50 °C à 1 % près
P_ATM = 101325.0
_TCHEB = (0.1, 0.4, 0.6, 0.9)


@lru_cache(maxsize=20000)
def h_sat(T_C: float, P: float = P_ATM) -> float:
    """Enthalpie de l'air saturé (J/kg air sec) à la température T."""
    return HAPropsSI("H", "T", T_C + 273.15, "P", P, "R", 1.0)


def h_air(T_C: float, HR: float, P: float = P_ATM) -> float:
    return HAPropsSI("H", "T", T_C + 273.15, "P", P, "R", min(max(HR, 1e-3), 1.0))


def rho_air(T_C: float, HR: float, P: float = P_ATM) -> float:
    """Masse volumique de l'air humide (kg/m³ d'air humide)."""
    v = HAPropsSI("Vha", "T", T_C + 273.15, "P", P, "R", min(max(HR, 1e-3), 1.0))
    return 1.0 / v


def T_humide(T_C: float, HR: float, P: float = P_ATM) -> float:
    return HAPropsSI("Twb", "T", T_C + 273.15, "P", P, "R", min(max(HR, 1e-3), 1.0)) - 273.15


def T_sat_air(h: float, P: float = P_ATM) -> float:
    """Température de l'air saturé d'enthalpie h."""
    return brentq(lambda T: h_sat(round(T, 6), P) - h, -30.0, 80.0, xtol=1e-6)


def merkel(T_froide: float, T_chaude: float, h_air_e: float, L_G: float, P: float = P_ATM) -> float:
    """Nombre de Merkel requis (Tchebychev 4 points). inf si infaisable."""
    R = T_chaude - T_froide
    somme = 0.0
    for f in _TCHEB:
        T = T_froide + f * R
        ha = h_air_e + L_G * CP_EAU * f * R
        dh = h_sat(round(T, 6), P) - ha
        if dh <= 0:
            return np.inf
        somme += 1.0 / dh
    return CP_EAU * R / 4.0 * somme


@dataclass
class ConceptionTour:
    T_seche_C: float = 8.0
    HR: float = 0.80
    T_eau_froide_C: float = 15.0
    plage_K: float = 10.0
    L_G: float = 1.0
    exposant_n: float = 0.6
    P: float = P_ATM


class TourNaturelle:
    """Tour dimensionnée pour les conditions de conception, puis figée."""

    def __init__(self, conception: ConceptionTour | None = None):
        d = conception or ConceptionTour()
        self.d = d
        h_e = h_air(d.T_seche_C, d.HR, d.P)
        self.Me_d = merkel(d.T_eau_froide_C, d.T_eau_froide_C + d.plage_K, h_e, d.L_G, d.P)
        if not np.isfinite(self.Me_d):
            raise ValueError("Conception infaisable : réduire L/G ou augmenter l'approche")
        self.drho_d = self._delta_rho(d.T_seche_C, d.HR, h_e, d.L_G, d.plage_K, d.P)

    @staticmethod
    def _delta_rho(T_s, HR, h_e, L_G, plage, P):
        h_s = h_e + L_G * CP_EAU * plage
        T_sortie = T_sat_air(h_s, P)
        return rho_air(T_s, HR, P) - rho_air(T_sortie, 1.0, P)

    def eau_froide(self, T_seche_C: float, HR: float, plage_K: float, P: float = P_ATM) -> dict:
        """Température d'eau froide pour une plage (échauffement condenseur)
        donnée et des conditions d'air données. Le débit d'air (tirage) et la
        caractéristique de la tour sont résolus par point fixe."""
        d = self.d
        h_e = h_air(T_seche_C, HR, P)

        # 1) Débit d'air : équilibre tirage = pertes de charge. Avec
        #    G = L / (L/G) et G² ∝ Δρ : (L/G)² · Δρ(L/G) = (L/G)_d² · Δρ_d.
        #    Δρ ne dépend que de l'enthalpie de l'air sortant (air saturé), donc
        #    de L/G : équation scalaire monotone, résolue par dichotomie.
        cible = d.L_G ** 2 * self.drho_d

        def equilibre(lg):
            return lg ** 2 * self._delta_rho(T_seche_C, HR, h_e, lg, plage_K, P) - cible

        L_G = brentq(equilibre, 0.2, 8.0, xtol=1e-8)

        # 2) Eau froide : Merkel requis = Merkel disponible de la tour
        Me = self.Me_d * (L_G / d.L_G) ** (-d.exposant_n)
        T_wb = T_humide(T_seche_C, HR, P)

        def f(Tf):
            return merkel(Tf, Tf + plage_K, h_e, L_G, P) - Me

        # L'eau froide est au-dessus de la température humide (approche > 0) ;
        # près de T_wb le Merkel requis est infini (f > 0), loin il est faible.
        Tf = brentq(f, T_wb + 0.05, min(T_wb + 45.0, 80.0 - plage_K), xtol=1e-5)
        return {"T_eau_froide_C": Tf, "T_humide_C": T_wb, "approche_K": Tf - T_wb,
                "L_G": L_G, "debit_air_relatif": d.L_G / L_G}


def couplage_centrale(tour: TourNaturelle, T_seche_C: float, HR: float,
                      plage_de_T, P: float = P_ATM) -> dict:
    """Couple la tour et la centrale. plage_de_T(T_eau_froide) donne
    l'échauffement au condenseur calculé par le modèle de la centrale
    (interpolé sur le balayage offdesign). Point fixe sur T_eau_froide."""
    Tf = tour.d.T_eau_froide_C
    for _ in range(100):
        res = tour.eau_froide(T_seche_C, HR, float(plage_de_T(Tf)), P)
        if abs(res["T_eau_froide_C"] - Tf) < 1e-4:
            return res
        Tf = res["T_eau_froide_C"]
    raise RuntimeError("Couplage tour-centrale non convergé")


def eau_vers_air_P(T):
    """Utilitaire de test : pression de saturation de l'eau (Pa)."""
    return PropsSI("P", "T", T + 273.15, "Q", 0, "water")
