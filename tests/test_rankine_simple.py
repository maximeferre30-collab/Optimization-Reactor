import pytest

from rep_secondaire import ParametresRankine, RankineSimple


@pytest.fixture(scope="module")
def resultats():
    return RankineSimple().resoudre()


def test_bilan_energie_ferme(resultats):
    r = resultats
    ecart = (r.puissance_thermique_MW + r.puissance_pompe_MW
             - r.puissance_turbine_MW - r.puissance_condenseur_MW)
    assert abs(ecart) < 1e-6


def test_ordres_de_grandeur(resultats):
    r = resultats
    assert 0.30 < r.rendement_cycle < 0.36
    assert r.rendement_cycle < r.rendement_carnot
    assert 30 < r.p_condenseur_mbar < 60
    assert 0.65 < r.titre_sortie_turbine < 0.80


def test_pompe_refoule_au_dessus_de_la_pression_gv():
    m = RankineSimple()
    m.resoudre()
    p = m.params
    assert m.c["4"].p.val == pytest.approx(p.p_vapeur_bar + p.dp_alimentation_bar)


def test_eau_plus_chaude_baisse_le_rendement():
    froid = RankineSimple(ParametresRankine(T_eau_refroidissement_C=10)).resoudre()
    chaud = RankineSimple(ParametresRankine(T_eau_refroidissement_C=25)).resoudre()
    assert chaud.p_condenseur_mbar > froid.p_condenseur_mbar
    assert chaud.puissance_electrique_nette_MW < froid.puissance_electrique_nette_MW
