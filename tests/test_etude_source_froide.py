import numpy as np
import pytest

from rep_secondaire import ParametresRankine, RankineSimple
from rep_secondaire.etude_source_froide import balayage_temperature, optimum


@pytest.fixture(scope="module")
def balayage(tmp_path_factory):
    chemin = tmp_path_factory.mktemp("design") / "design.json"
    return balayage_temperature([0, 5, 10, 15, 20, 25, 30], chemin)


@pytest.fixture(scope="module")
def balayage_sans_pertes(tmp_path_factory):
    chemin = tmp_path_factory.mktemp("design_sans") / "design.json"
    return balayage_temperature(
        [5, 15, 25], chemin, ParametresRankine(pertes_echappement=False))


def test_offdesign_au_point_de_design_redonne_le_design(tmp_path):
    m = RankineSimple()
    design = m.resoudre()
    m.sauvegarder_design(tmp_path / "design.json")
    off = m.resoudre_offdesign(ParametresRankine().T_eau_refroidissement_C)
    assert off.puissance_electrique_nette_MW == pytest.approx(
        design.puissance_electrique_nette_MW, rel=1e-5)
    assert off.p_condenseur_mbar == pytest.approx(design.p_condenseur_mbar, rel=1e-5)
    assert off.vitesse_annulaire_m_s == pytest.approx(250.0, rel=1e-4)


def test_balayage_ne_modifie_pas_les_parametres(tmp_path):
    params = ParametresRankine()
    balayage_temperature([13, 15], tmp_path / "design.json", params)
    assert params.T_eau_refroidissement_C == 15.0


def test_debit_eau_refroidissement_fige(balayage):
    m = balayage["debit_eau_refroidissement_kg_s"].values
    assert np.allclose(m, m[0], rtol=1e-9)


def test_pression_croit_avec_la_temperature(balayage):
    assert balayage["p_condenseur_mbar"].is_monotonic_increasing


def test_puissance_decroit_au_dessus_de_l_optimum(balayage):
    assert balayage.loc[15:, "puissance_electrique_nette_MW"].is_monotonic_decreasing


def test_optimum_et_blocage_en_eau_froide(balayage):
    T_opt, _ = optimum(balayage)
    assert 5 < T_opt < 15
    assert bool(balayage.loc[0, "echappement_bloque"])
    assert not bool(balayage.loc[15, "echappement_bloque"])


def test_sans_pertes_puissance_strictement_decroissante(balayage_sans_pertes):
    P = balayage_sans_pertes["puissance_electrique_nette_MW"]
    assert P.is_monotonic_decreasing
    assert (balayage_sans_pertes["perte_echappement_MW"] == 0).all()


def test_bilan_energie_offdesign(balayage):
    ecart = (balayage["puissance_thermique_MW"] + balayage["puissance_pompe_MW"]
             - balayage["puissance_turbine_MW"] - balayage["puissance_condenseur_MW"])
    assert np.abs(ecart).max() < 1e-6
