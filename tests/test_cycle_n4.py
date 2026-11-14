"""Vérifications du cycle N4 complet, de l'exergie, de la tour et des rejets."""

import numpy as np
import pytest
from scipy.integrate import quad

from rep_secondaire.cycle_n4 import CycleN4, TRONCONS
from rep_secondaire.exergie import _sgen, bilan_exergie
from rep_secondaire.parametres import ParametresN4
from rep_secondaire.rejets import LimitesRejet, facteur_puissance
from rep_secondaire.tour import CP_EAU, ConceptionTour, TourNaturelle, h_air, h_sat, merkel


@pytest.fixture(scope="module")
def n4():
    m = CycleN4(ParametresN4())
    m.resoudre()
    return m


def test_bilan_energie(n4):
    r = n4.resultats()
    ecart = r.puissance_thermique_MW + r.puissance_pompe_MW - r.puissance_turbine_MW - r.puissance_condenseur_MW
    assert abs(ecart) < 1e-6


def test_bilans_matiere(n4):
    c = n4.c
    # Tout le débit de vapeur revient comme eau alimentaire
    assert c["4"].m.val == pytest.approx(c["1"].m.val, rel=1e-9)
    # Ce qui arrive au condenseur = échappement BP + purges BP en cascade
    assert c["3"].m.val == pytest.approx(
        c["2"].m.val + c["x_RBP1"].m.val + c["x_RBP2"].m.val + c["x_RBP3"].m.val, rel=1e-9)


def test_ordres_de_grandeur_N4(n4):
    r = n4.resultats()
    assert 225 < r.T_eau_alimentaire_C < 235            # ~230 °C publié
    assert abs(r.puissance_electrique_brute_MW / 1560 - 1) < 0.05  # ~1 560 MWe brut publié
    assert 2300 < r.debit_vapeur_kg_s < 2500
    assert r.titre_sortie_turbine > 0.84                 # MSR : humidité < 16 %
    assert 0.34 < r.rendement_cycle < 0.39


def test_baumann_applique(n4):
    p = n4.params
    # Tronçon BP1 entièrement en vapeur surchauffée : pas de pénalité
    assert n4.K["BP1"].eta_s.val == pytest.approx(p.rendement_isentropique_BP, abs=1e-6)
    # Tronçons humides pénalisés
    for n in ("HP2", "HP3", "BP4"):
        assert n4.K[n].eta_s.val < 0.88


def test_second_principe_par_composant(n4):
    for nom, comp in n4.K.items():
        if nom in ("prim_in", "prim_out", "cw_in", "cw_out"):
            continue
        assert _sgen(comp) > -1e-3, nom  # W/K : aucune création d'exergie


def test_bilan_exergie_ferme(n4):
    b = bilan_exergie(n4)
    assert abs(b["ecart_bilan_MW"]) < 1e-6
    assert abs(b["destruction_neutres_MW"]) < 1e-6
    assert 0.6 < b["rendement_exergetique"] < 0.8


def test_offdesign_redonne_le_design(n4, tmp_path):
    m = CycleN4(ParametresN4())
    d = m.resoudre()
    m.sauvegarder_design(tmp_path / "d.json")
    o = m.resoudre_offdesign(15.0)
    assert o.puissance_electrique_nette_MW == pytest.approx(d.puissance_electrique_nette_MW, rel=1e-5)
    assert o.p_vapeur_bar == pytest.approx(d.p_vapeur_bar, rel=1e-5)
    m.resoudre_offdesign(16.0)
    r = m.resoudre_offdesign(17.0)
    assert r.puissance_electrique_nette_MW < d.puissance_electrique_nette_MW
    assert r.p_vapeur_bar == pytest.approx(72.0, abs=0.5)  # pression GV calculée, quasi constante


# ----------------------------- tour ---------------------------------- #
def test_merkel_tchebychev_contre_integration_fine():
    h_e = h_air(10.0, 0.7)
    Tf, Tc, LG = 18.0, 28.0, 1.0
    exact, _ = quad(lambda T: CP_EAU / (h_sat(T) - (h_e + LG * CP_EAU * (T - Tf))), Tf, Tc)
    assert merkel(Tf, Tc, h_e, LG) == pytest.approx(exact, rel=0.01)


def test_tour_point_de_conception_et_monotonie():
    d = ConceptionTour()
    t = TourNaturelle(d)
    assert t.eau_froide(d.T_seche_C, d.HR, d.plage_K)["T_eau_froide_C"] == pytest.approx(d.T_eau_froide_C, abs=1e-3)
    Tf = [t.eau_froide(T, 0.7, 10.0)["T_eau_froide_C"] for T in (0, 10, 20, 30)]
    assert all(np.diff(Tf) > 0)
    for T in (0, 10, 20, 30):
        r = t.eau_froide(T, 0.7, 10.0)
        assert r["approche_K"] > 0  # l'eau ne descend jamais sous la température humide


# ----------------------------- rejets -------------------------------- #
def test_rejets():
    lim = LimitesRejet(dT_max_K=3.0, T_aval_max_C=28.0)
    assert facteur_puissance(10.0, 1e5, 2600.0, lim) == 1.0       # grand fleuve : aucune limite
    assert facteur_puissance(27.0, 300.0, 2600.0, lim) < facteur_puissance(20.0, 300.0, 2600.0, lim)
    assert facteur_puissance(29.0, 300.0, 2600.0, lim) == 0.0      # rivière déjà au-dessus de la limite
