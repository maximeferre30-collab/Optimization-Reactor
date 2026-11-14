"""Analyses thermodynamiques « à la main », pour contrôler et expliquer le modèle.

1. Sensibilité de la puissance à la température de condensation, par la
   relation de Clapeyron (sans TESPy) :

   Sur le dernier étage BP, le travail vaut w = η (h_e − h_s), et h_s est
   l'enthalpie isentropique de sortie. À entropie fixée, dh = v dp (relation
   de Gibbs), donc une hausse dp de la pression d'échappement retire
       dW = − η ṁ v_s dp.
   Clapeyron : dp/dT = h_fg / (T (v_g − v_f)) ≈ h_fg / (T v_g), et v_s ≈ x v_g.
   D'où :
       dW/dT_c ≈ − η ṁ x h_fg / T_c = − η Q̇_lat / T_c
   Q̇_lat = ṁ x h_fg est la chaleur latente cédée au condenseur par la vapeur
   d'échappement. C'est la version « de terrain » de dW = −Q dT/T.

2. Température moyenne entropique de l'apport de chaleur :
       T̄ = (h_sortie − h_entrée) / (s_sortie − s_entrée)
   Le rendement d'un cycle endoréversible qui recevrait toute la chaleur à
   T̄ et la rejetterait à T_c vaut 1 − T_c/T̄. C'est la grandeur qui explique
   pourquoi le réchauffage de l'eau alimentaire améliore le rendement.

3. Diagrammes T-Q (profils de température le long de l'échangeur,
   pincement) du GV et du condenseur.
"""

from __future__ import annotations

import numpy as np
from CoolProp.CoolProp import PropsSI

W = "water"


def T_moyenne_entropique(h_e: float, s_e: float, h_s: float, s_s: float) -> float:
    """T̄ (K) à partir des états d'entrée et de sortie (SI)."""
    return (h_s - h_e) / (s_s - s_e)


def analyse_temperatures_moyennes(modele, entree: str, sortie: str) -> dict:
    """T̄ d'apport de chaleur au secondaire, T de condensation, rendements."""
    c = modele.c
    ce, cs = c[entree], c[sortie]
    Tm = T_moyenne_entropique(ce.h.val_SI, ce.s.val_SI, cs.h.val_SI, cs.s.val_SI)
    Tc = c["3"].T.val_SI
    r = modele.resultats()
    return {
        "T_moyenne_apport_C": Tm - 273.15,
        "T_condensation_C": Tc - 273.15,
        "T_vapeur_C": cs.T.val_SI - 273.15,
        "rendement_endoreversible": 1 - Tc / Tm,
        "rendement_carnot_vapeur": 1 - Tc / cs.T.val_SI,
        "rendement_cycle": r.rendement_cycle,
        "efficacite_relative": r.rendement_cycle / (1 - Tc / Tm),
    }


def sensibilite_clapeyron(modele, turbine_finale: str, conn_echappement: str, conn_condensat: str,
                          rendement_alternateur: float) -> dict:
    """Estimation de dP_brute/dT_condensation (MW/K) par Clapeyron."""
    c, K = modele.c, modele.K
    ce = c[conn_echappement]
    p, h, m = ce.p.val_SI, ce.h.val_SI, ce.m.val_SI
    x = PropsSI("Q", "P", p, "H", h, W)
    T = PropsSI("T", "P", p, "Q", 0, W)
    h_fg = PropsSI("H", "P", p, "Q", 1, W) - PropsSI("H", "P", p, "Q", 0, W)
    v_g, v_f = PropsSI("D", "P", p, "Q", 1, W) ** -1, PropsSI("D", "P", p, "Q", 0, W) ** -1
    eta = K[turbine_finale].eta_s.val
    Q_lat = m * x * h_fg
    dWdT = -eta * Q_lat / T * rendement_alternateur
    # Contrôle de Clapeyron contre CoolProp (dérivée numérique de p_sat)
    dpdT_clap = h_fg / (T * (v_g - v_f))
    dpdT_num = (PropsSI("P", "T", T + 0.05, "Q", 0, W) - PropsSI("P", "T", T - 0.05, "Q", 0, W)) / 0.1
    return {
        "eta_dernier_etage": eta, "titre_echappement": x, "T_condensation_C": T - 273.15,
        "h_fg_kJ_kg": h_fg / 1e3, "debit_echappement_kg_s": m, "Q_latent_MW": Q_lat / 1e6,
        "dP_dTc_MW_K": dWdT / 1e6,
        "clapeyron_dp_dT_Pa_K": dpdT_clap, "coolprop_dp_dT_Pa_K": dpdT_num,
    }


def credit_regeneratif(modele, rendement_alternateur: float) -> dict:
    """Second terme de la sensibilité, propre au cycle à soutirages.

    Le réchauffeur RBP1 porte le condensat à une température fixée par son
    écart terminal. Si le condensat arrive plus chaud de dT, il faut
    ṁ_c·cp·dT de moins, donc un soutirage réduit de
        dṁ_x = ṁ_c cp dT / (h_x − h_purge).
    Cette vapeur poursuit sa détente dans le dernier tronçon BP et produit
        dW = dṁ_x (h_e6 − h_2).
    Le crédit est positif : il compense une partie de la perte de Clapeyron."""
    c = modele.c
    mc = c["3"].m.val_SI
    cp = PropsSI("C", "T", c["3"].T.val_SI, "Q", 0, W)
    hx, hd = c["x_RBP1"].h.val_SI, c["d_RBP1"].h.val_SI
    he6, h2 = c["e6a"].h.val_SI, c["2"].h.val_SI
    dmx_dT = mc * cp / (hx - hd)
    return {"dmx_dT_kg_s_K": dmx_dT, "dP_dTc_MW_K": dmx_dT * (he6 - h2) * rendement_alternateur / 1e6}


def decomposition_sensibilite(params, design_path, T_eau=(15.0, 16.0, 17.0, 18.0, 19.0, 20.0)) -> dict:
    """Décompose la pente dP_brute/dT_condensation près du design :
    estimation à la main (Clapeyron + crédit régénératif), modèle sans pertes
    d'échappement, modèle complet. Pentes par kelvin de température de
    condensation."""
    from dataclasses import replace
    from pathlib import Path

    from .cycle_n4 import CycleN4

    out = {}
    for nom, pertes in (("sans_pertes", False), ("complet", True)):
        m = CycleN4(replace(params, pertes_echappement=pertes))
        m.resoudre()
        if nom == "complet":
            cl = sensibilite_clapeyron(m, "BP4", "2", "3", params.rendement_meca_alternateur)
            cr = credit_regeneratif(m, params.rendement_meca_alternateur)
        m.sauvegarder_design(Path(design_path).with_name(f"decomp_{nom}.json"))
        Tc, P = [], []
        for t in T_eau:
            r = m.resoudre_offdesign(t)
            Tc.append(r.T_condenseur_C)
            P.append(r.puissance_electrique_brute_MW)
        out[nom] = float(np.polyfit(Tc, P, 1)[0])
    a_la_main = cl["dP_dTc_MW_K"] + cr["dP_dTc_MW_K"]
    return {
        "clapeyron": cl["dP_dTc_MW_K"], "credit_regeneratif": cr["dP_dTc_MW_K"], "a_la_main": a_la_main,
        "modele_sans_pertes": out["sans_pertes"], "residu_autres_effets": out["sans_pertes"] - a_la_main,
        "effet_pertes_echappement": out["complet"] - out["sans_pertes"], "modele_complet": out["complet"],
        "plage_T_eau_C": [min(T_eau), max(T_eau)], "details_clapeyron": cl,
    }


def profil_TQ_gv(modele, n: int = 80) -> dict:
    """Profil T-Q du GV (contre-courant). Q compté depuis l'entrée d'eau
    alimentaire. Côté secondaire : p et h linéaires en Q (perte de charge
    répartie) ; côté primaire : h linéaire en Q."""
    c = modele.c
    s0, s1, p1, p2 = c["0"], c["1"], c["P1"], c["P2"]
    Qt = s1.m.val_SI * (s1.h.val_SI - s0.h.val_SI)
    q = np.linspace(0, 1, n)
    h_s = s0.h.val_SI + q * (s1.h.val_SI - s0.h.val_SI)
    p_s = s0.p.val_SI + q * (s1.p.val_SI - s0.p.val_SI)
    T_s = np.array([PropsSI("T", "P", a, "H", b, W) for a, b in zip(p_s, h_s)]) - 273.15
    h_p = p2.h.val_SI + q * (p1.h.val_SI - p2.h.val_SI)
    T_p = np.array([PropsSI("T", "P", p1.p.val_SI, "H", b, W) for b in h_p]) - 273.15
    dT = T_p - T_s
    i = int(np.argmin(dT))
    return {"Q_MW": list(q * Qt / 1e6), "T_secondaire": list(T_s), "T_primaire": list(T_p),
            "pincement_K": float(dT[i]), "Q_pincement_MW": float(q[i] * Qt / 1e6)}


def profil_TQ_condenseur(modele, n: int = 40) -> dict:
    """Profil T-Q du condenseur. Q compté depuis la sortie de condensat
    (côté entrée d'eau froide, contre-courant)."""
    c = modele.c
    hin = c["h_cond"] if "h_cond" in c else c["2u"]
    hout, w_in, w_out = c["3"], c["11"], c["12"]
    Qt = hout.m.val_SI * (hin.h.val_SI - hout.h.val_SI)
    q = np.linspace(0, 1, n)
    h_v = hout.h.val_SI + q * (hin.h.val_SI - hout.h.val_SI)
    T_v = np.array([PropsSI("T", "P", hout.p.val_SI, "H", b, W) for b in h_v]) - 273.15
    T_e = w_in.T.val + q * (w_out.T.val - w_in.T.val)
    dT = T_v - T_e
    i = int(np.argmin(dT))
    return {"Q_MW": list(q * Qt / 1e6), "T_vapeur": list(T_v), "T_eau": list(T_e),
            "pincement_K": float(dT[i]), "Q_pincement_MW": float(q[i] * Qt / 1e6)}


def chemin_hs_n4(modele) -> dict:
    """Détentes HP et BP dans le diagramme de Mollier (h-s), tronçon par tronçon,
    avec les détentes isentropiques de référence."""
    from .cycle_n4 import TRONCONS
    from .echappement import LigneDetente

    c, K = modele.c, modele.K
    out = {}
    for n, (ci, co) in TRONCONS.items():
        pi, hi = c[ci].p.val_SI, c[ci].h.val_SI
        po = c[co].p.val_SI
        ligne = LigneDetente(pi, hi, K[n].eta_s.val)
        pp = np.geomspace(pi, po, 30)
        h = np.array([ligne.h(x) for x in pp])
        s = np.array([PropsSI("S", "P", a, "H", b, W) for a, b in zip(pp, h)])
        hs_iso = PropsSI("H", "P", po, "S", ligne.s1, W)
        out[n] = {"s": list(s / 1e3), "h": list(h / 1e3), "s_iso": [ligne.s1 / 1e3, ligne.s1 / 1e3],
                  "h_iso": [hi / 1e3, hs_iso / 1e3], "eta": float(K[n].eta_s.val),
                  "p_in_bar": pi / 1e5, "p_out_bar": po / 1e5}
    # sécheur et surchauffe
    for nom, a, b in (("sécheur", "e3a", "v_sech"), ("surchauffeur", "v_sech", "bp_in")):
        pa, ha, pb, hb = c[a].p.val_SI, c[a].h.val_SI, c[b].p.val_SI, c[b].h.val_SI
        pp, hh = np.linspace(pa, pb, 20), np.linspace(ha, hb, 20)
        s = [PropsSI("S", "P", x, "H", y, W) / 1e3 for x, y in zip(pp, hh)]
        out[nom] = {"s": s, "h": list(hh / 1e3)}
    # courbe de saturation et isobares de référence dans la zone utile
    sat = {"s": [], "h": []}
    for T in np.linspace(273.16 + 5, 647.0, 120):
        sat["s"].append(PropsSI("S", "T", T, "Q", 1, W) / 1e3)
        sat["h"].append(PropsSI("H", "T", T, "Q", 1, W) / 1e3)
    isobares = {}
    for p_bar in (72, 30, 10, 4, 1.5, 0.4, 0.04):
        ss = np.linspace(5.4, 8.2, 60)
        hh = []
        for sv in ss:
            try:
                hh.append(PropsSI("H", "P", p_bar * 1e5, "S", sv * 1e3, W) / 1e3)
            except ValueError:
                hh.append(None)
        isobares[str(p_bar)] = {"s": list(ss), "h": hh}
    return {"troncons": out, "saturation": sat, "isobares": isobares}
