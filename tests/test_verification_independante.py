"""Vérification indépendante du point de design.

On refait le calcul du cycle « à la main », avec les seules tables de
CoolProp et les bilans du premier principe, sans TESPy, puis on compare.
Si TESPy et ce calcul divergent, l'un des deux est faux.
"""

import pytest
from CoolProp.CoolProp import PropsSI

from rep_secondaire import ParametresRankine, RankineSimple
from rep_secondaire.echappement import (
    LigneDetente,
    facteur_humidite,
    perte_echappement_kJ_kg,
)

W = "water"


def calcul_a_la_main(p: ParametresRankine) -> dict:
    # Condenseur : T_sat = T_sortie eau + pincement
    T_sat = p.T_eau_refroidissement_C + p.echauffement_eau_refroidissement_K \
        + p.pincement_condenseur_K + 273.15
    p_cond = PropsSI("P", "T", T_sat, "Q", 0, W)

    # 1 : vapeur saturée à l'admission
    p1 = p.p_vapeur_bar * 1e5
    h1 = PropsSI("H", "P", p1, "Q", p.titre_vapeur, W)
    s1 = PropsSI("S", "P", p1, "Q", p.titre_vapeur, W)

    # 2 : détente (définition du rendement isentropique)
    h2s = PropsSI("H", "P", p_cond, "S", s1, W)
    h2 = h1 - p.rendement_isentropique_turbine * (h1 - h2s)

    # 3 : liquide saturé ; 4 : pompe
    h3 = PropsSI("H", "P", p_cond, "Q", 0, W)
    s3 = PropsSI("S", "P", p_cond, "Q", 0, W)
    p4 = p1 + p.dp_alimentation_bar * 1e5
    h4s = PropsSI("H", "P", p4, "S", s3, W)
    h4 = h3 + (h4s - h3) / p.rendement_isentropique_pompe

    # Débit : bilan sur le GV
    m = p.puissance_thermique_MW * 1e6 / (h1 - h4)

    # Pertes d'échappement (SCC) au point de design, V = V_design par construction
    perte = 0.0
    if p.pertes_echappement:
        Y = 100 * (1 - PropsSI("Q", "P", p_cond, "H", h2, W))
        perte = m * perte_echappement_kJ_kg(p.vitesse_annulaire_design_m_s) \
            * facteur_humidite(Y) * 1e3

    W_t = m * (h1 - h2) - perte
    W_p = m * (h4 - h3)
    Q_cond = m * (h2 - h3) + perte
    return {
        "p_cond_mbar": p_cond / 100,
        "m": m,
        "W_t_MW": W_t / 1e6,
        "W_p_MW": W_p / 1e6,
        "Q_cond_MW": Q_cond / 1e6,
        "rendement_cycle": (W_t - W_p) / (p.puissance_thermique_MW * 1e6),
    }


@pytest.mark.parametrize("pertes", [False, True])
def test_tespy_egale_calcul_a_la_main(pertes):
    p = ParametresRankine(pertes_echappement=pertes)
    ref = calcul_a_la_main(p)
    r = RankineSimple(p).resoudre()
    assert r.p_condenseur_mbar == pytest.approx(ref["p_cond_mbar"], rel=1e-5)
    assert r.debit_vapeur_kg_s == pytest.approx(ref["m"], rel=1e-5)
    assert r.puissance_turbine_MW == pytest.approx(ref["W_t_MW"], rel=1e-5)
    assert r.puissance_pompe_MW == pytest.approx(ref["W_p_MW"], rel=1e-4)
    assert r.puissance_condenseur_MW == pytest.approx(ref["Q_cond_MW"], rel=1e-5)
    assert r.rendement_cycle == pytest.approx(ref["rendement_cycle"], rel=1e-5)


def test_second_principe_respecte():
    """Le rendement doit rester sous Carnot entre T_sat admission et T_sat
    condenseur (cycle endoréversible le plus favorable)."""
    m = RankineSimple()
    r = m.resoudre()
    T_h = m.c["1"].T.val + 273.15
    T_c = r.T_condenseur_C + 273.15
    assert r.rendement_cycle < 1 - T_c / T_h


def test_ligne_detente_coherente_avec_tespy():
    m = RankineSimple(ParametresRankine(pertes_echappement=False))
    m.resoudre()
    ligne = LigneDetente(m.c["1"].p.val_SI, m.c["1"].h.val_SI, m.turbine.eta_s.val)
    assert ligne.h(m.c["2"].p.val_SI) == pytest.approx(m.c["2"].h.val_SI, rel=1e-7)
