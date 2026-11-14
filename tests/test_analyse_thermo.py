"""Le modèle numérique doit retrouver les raisonnements thermodynamiques à la main."""

import numpy as np
import pytest

from rep_secondaire import ParametresRankine, RankineSimple
from rep_secondaire.analyse_thermo import (
    analyse_temperatures_moyennes,
    decomposition_sensibilite,
    profil_TQ_condenseur,
    profil_TQ_gv,
    sensibilite_clapeyron,
)
from rep_secondaire.cycle_n4 import CycleN4
from rep_secondaire.parametres import ParametresN4


@pytest.fixture(scope="module")
def n4():
    m = CycleN4(ParametresN4())
    m.resoudre()
    return m


def test_clapeyron_contre_coolprop(n4):
    r = sensibilite_clapeyron(n4, "BP4", "2", "3", 0.985)
    assert r["clapeyron_dp_dT_Pa_K"] == pytest.approx(r["coolprop_dp_dT_Pa_K"], rel=1e-3)


def test_sensibilite_a_la_main_contre_modele(tmp_path):
    """Clapeyron + crédit régénératif doit retrouver la pente du modèle sans
    pertes d'échappement à 5 % près ; les pertes d'échappement expliquent le reste."""
    d = decomposition_sensibilite(ParametresN4(), tmp_path / "d.json")
    assert d["a_la_main"] == pytest.approx(d["modele_sans_pertes"], rel=0.05)
    assert d["clapeyron"] < 0 < d["credit_regeneratif"]
    total = d["a_la_main"] + d["residu_autres_effets"] + d["effet_pertes_echappement"]
    assert total == pytest.approx(d["modele_complet"], rel=1e-9)


def test_temperature_moyenne_explique_le_gain_du_rechauffage(n4):
    a_n4 = analyse_temperatures_moyennes(n4, "0", "1")
    s = RankineSimple(ParametresRankine())
    s.resoudre()
    a_s = analyse_temperatures_moyennes(s, "0", "1")
    # Le réchauffage élève fortement la température moyenne d'apport de chaleur…
    assert a_n4["T_moyenne_apport_C"] > a_s["T_moyenne_apport_C"] + 50
    # …tandis que la « qualité » des machines (fraction du rendement endoréversible) reste comparable
    assert abs(a_n4["efficacite_relative"] - a_s["efficacite_relative"]) < 0.05
    for a in (a_n4, a_s):
        assert a["rendement_cycle"] < a["rendement_endoreversible"] < a["rendement_carnot_vapeur"]


def test_pincements_positifs(n4):
    gv, cond = profil_TQ_gv(n4), profil_TQ_condenseur(n4)
    assert gv["pincement_K"] > 0
    assert cond["pincement_K"] == pytest.approx(n4.params.pincement_condenseur_K, abs=1e-6)
    assert gv["Q_MW"][-1] == pytest.approx(n4.params.puissance_thermique_MW, rel=1e-6)
