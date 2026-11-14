import numpy as np
import pytest

from rep_secondaire import ParametresRankine, RankineSimple
from rep_secondaire.etude_source_froide import balayage_temperature


@pytest.fixture(scope="module")
def balayage(tmp_path_factory):
    chemin = tmp_path_factory.mktemp("design") / "design.json"
    return balayage_temperature([5, 10, 15, 20, 25], chemin)


def test_offdesign_au_point_de_design_redonne_le_design(tmp_path):
    m = RankineSimple()
    design = m.resoudre()
    m.sauvegarder_design(tmp_path / "design.json")
    off = m.resoudre_offdesign(ParametresRankine().T_eau_refroidissement_C)
    assert off.puissance_electrique_nette_MW == pytest.approx(
        design.puissance_electrique_nette_MW, rel=1e-6)
    assert off.p_condenseur_mbar == pytest.approx(design.p_condenseur_mbar, rel=1e-6)


def test_debit_eau_refroidissement_fige(balayage):
    m = balayage["debit_eau_refroidissement_kg_s"].values
    assert np.allclose(m, m[0], rtol=1e-9)


def test_puissance_decroit_et_pression_croit(balayage):
    assert balayage["puissance_electrique_nette_MW"].is_monotonic_decreasing
    assert balayage["p_condenseur_mbar"].is_monotonic_increasing


def test_bilan_energie_offdesign(balayage):
    ecart = (balayage["puissance_thermique_MW"] + balayage["puissance_pompe_MW"]
             - balayage["puissance_turbine_MW"] - balayage["puissance_condenseur_MW"])
    assert np.abs(ecart).max() < 1e-6
