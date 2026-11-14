"""Correction du coefficient d'échange du condenseur avec la température de l'eau.

Le coefficient global U (et donc UA) d'un condenseur dépend de la
température de l'eau de refroidissement. Les normes HEI (Heat Exchange
Institute) en tiennent compte par un « facteur de correction de température
d'entrée ». Côté tubes, l'eau froide est plus visqueuse et échange moins bien.

Modèle retenu, explicite et vérifiable :
- résistance côté eau (convection forcée turbulente, Dittus-Boelter à vitesse
  fixée, débit constant) :
      h_eau ∝ k^0,6 · ρ^0,8 · cp^0,4 · µ^-0,4
  avec les propriétés évaluées à la température moyenne de l'eau
  (CoolProp) ;
- autres résistances (condensation côté vapeur, paroi, encrassement)
  supposées constantes ;
- au point de design, la résistance côté eau représente une fraction
  `part_eau` de la résistance totale 1/U.

Alors :
    U(T) / U_design = 1 / [ part_eau · h_eau(T_design) / h_eau(T) + (1 - part_eau) ]
"""

from __future__ import annotations

from CoolProp.CoolProp import PropsSI

P_EAU_PA = 2e5


def _groupe_dittus_boelter(T_C: float) -> float:
    T = T_C + 273.15
    k = PropsSI("L", "T", T, "P", P_EAU_PA, "water")
    rho = PropsSI("D", "T", T, "P", P_EAU_PA, "water")
    cp = PropsSI("C", "T", T, "P", P_EAU_PA, "water")
    mu = PropsSI("V", "T", T, "P", P_EAU_PA, "water")
    return k**0.6 * rho**0.8 * cp**0.4 * mu**-0.4


def facteur_UA(T_moy_C: float, T_moy_design_C: float, part_eau: float) -> float:
    """Rapport UA(T) / UA_design."""
    rapport_h = _groupe_dittus_boelter(T_moy_C) / _groupe_dittus_boelter(T_moy_design_C)
    return 1.0 / (part_eau / rapport_h + (1.0 - part_eau))
