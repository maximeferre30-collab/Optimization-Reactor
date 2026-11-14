"""Données pour les diagrammes : chemin du cycle dans le plan T-s, cloche de
saturation et bilan d'énergie (Sankey).

Chemins entre états (hypothèses de tracé, pas de calcul supplémentaire) :
- GV (4 -> 1) : p et h varient linéairement (perte de charge répartie) ;
- turbine (1 -> 2) : ligne de détente à rendement isentropique constant,
  pressions réparties géométriquement ;
- pertes d'échappement (2 -> 2u) et condensation (2u -> 3) : isobares ;
- pompe (3 -> 4) : p et h linéaires (le segment est quasi invisible en T-s).
"""

from __future__ import annotations

import numpy as np
from CoolProp.CoolProp import PropsSI

from .echappement import LigneDetente

W = "water"
N = 60


def _Ts(p, h):
    T = np.array([PropsSI("T", "P", pi, "H", hi, W) for pi, hi in zip(p, h)]) - 273.15
    s = np.array([PropsSI("S", "P", pi, "H", hi, W) for pi, hi in zip(p, h)]) / 1e3
    return s, T


def cloche_saturation(T_min_C=5.0, n=200):
    T_crit = PropsSI("Tcrit", W)
    T = np.linspace(T_min_C + 273.15, T_crit - 0.01, n)
    s_l = np.array([PropsSI("S", "T", t, "Q", 0, W) for t in T]) / 1e3
    s_v = np.array([PropsSI("S", "T", t, "Q", 1, W) for t in T]) / 1e3
    return np.concatenate([s_l, s_v[::-1]]), np.concatenate([T, T[::-1]]) - 273.15


def chemin_Ts(modele) -> dict:
    """Segments (s [kJ/kg/K], T [°C]) de chaque transformation + points."""
    c = {k: (v.p.val_SI, v.h.val_SI) for k, v in modele.c.items()}
    seg = {}

    p4, h4 = c["4"]; p1, h1 = c["1"]
    seg["generateur de vapeur"] = _Ts(np.linspace(p4, p1, N), np.linspace(h4, h1, N))

    p2, h2 = c["2"]
    ligne = LigneDetente(p1, h1, modele.turbine.eta_s.val)
    pp = np.geomspace(p1, p2, N)
    seg["turbine"] = _Ts(pp, [ligne.h(x) for x in pp])

    p2u, h2u = c["2u"]
    seg["pertes echappement"] = _Ts(np.full(N, p2), np.linspace(h2, h2u, N))

    p3, h3 = c["3"]
    seg["condenseur"] = _Ts(np.full(N, p3), np.linspace(h2u, h3, N))
    seg["pompe"] = _Ts(np.linspace(p3, p4, N), np.linspace(h3, h4, N))

    points = {}
    for k in ("1", "2", "2u", "3", "4"):
        p, h = c[k]
        s, T = _Ts([p], [h])
        points[k] = (float(s[0]), float(T[0]))
    return {"segments": seg, "points": points}


def chemin_Ts_n4(modele) -> dict:
    """Segments T-s du cycle N4 (chemin principal de la vapeur et de l'eau).

    Hypothèses de tracé : lignes de détente à rendement constant par tronçon ;
    sécheur = passage isobare à la vapeur saturée ; surchauffe, condensation
    et réchauffeurs isobares (p et h linéaires si Δp) ; GV p et h linéaires.
    """
    from .cycle_n4 import TRONCONS

    c, K = modele.c, modele.K
    ph = {k: (v.p.val_SI, v.h.val_SI) for k, v in c.items()}
    seg = {}

    def lin(nom, a, b):
        (pa, ha), (pb, hb) = ph[a], ph[b]
        seg[nom] = _Ts(np.linspace(pa, pb, N), np.linspace(ha, hb, N))

    lin("GV", "0", "1")
    lin("soupapes HP", "1a", "1c")
    for n, (ci, co) in TRONCONS.items():
        pi, hi = ph[ci]
        po, _ = ph[co]
        ligne = LigneDetente(pi, hi, K[n].eta_s.val)
        pp = np.geomspace(pi, po, N)
        seg[n] = _Ts(pp, [ligne.h(x) for x in pp])
    lin("sécheur", "e3a", "v_sech")
    lin("surchauffeur", "v_sech", "bp_in")
    lin("pertes échappement", "2", "2u")
    lin("condenseur", "2u", "3")
    chaine = ["3", "c1", "c2", "c3", "c4", "a0", "a1", "a2", "4"]
    for a, b in zip(chaine[:-1], chaine[1:]):
        lin(f"eau {a}-{b}", a, b)

    points = {}
    for k in ("1", "e3", "v_sech", "bp_in", "2", "3", "a0", "4"):
        s, T = _Ts([ph[k][0]], [ph[k][1]])
        points[k] = (float(s[0]), float(T[0]))
    return {"segments": seg, "points": points}


def bilan_sankey(r, params) -> dict:
    """Décomposition de la puissance thermique du GV (MW).

    Q_GV = P_nette + Q_condenseur + pertes alternateur + pertes moteur pompe
    (le travail de pompe revient au fluide, il est donc compris dans Q_cond).
    """
    pertes_alt = r.puissance_turbine_MW * (1 - params.rendement_meca_alternateur)
    pertes_moteur = r.puissance_pompe_MW * (1 / params.rendement_moteur_pompe - 1)
    q_cond_hors_ech = r.puissance_condenseur_MW - r.perte_echappement_MW
    d = {
        "Puissance GV": r.puissance_thermique_MW,
        "Électricité nette": r.puissance_electrique_nette_MW,
        "Chaleur rejetée au condenseur": q_cond_hors_ech,
        "Pertes d'échappement BP (rejetées au condenseur)": r.perte_echappement_MW,
        "Pertes alternateur + moteur de pompe": pertes_alt + pertes_moteur,
    }
    d["écart de bilan"] = d["Puissance GV"] - sum(
        v for k, v in d.items() if k != "Puissance GV")
    return d
