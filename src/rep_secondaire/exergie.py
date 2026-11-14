"""Analyse exergétique du cycle N4 (théorème de Gouy-Stodola).

Exergie détruite dans un composant adiabatique :
    Ex_d = T0 · S_gen = T0 · ( Σ_sorties ṁ s − Σ_entrées ṁ s )

Tous les composants du modèle sont adiabatiques vis-à-vis de l'extérieur,
GV compris puisque son côté primaire est modélisé. Le bloc « pertes
d'échappement » représente une dissipation interne à la turbine BP : on
lui applique la même formule. L'exergie est rapportée à l'état mort
T0 = température d'entrée de l'eau de refroidissement.

Bilan vérifié :
    Ex_primaire = P_nette + Σ Ex_d(composants) + Ex_d(alternateur, moteurs)
                  + Ex_eau_refroidissement (exergie rejetée au milieu)
"""

from __future__ import annotations

GROUPES = {
    "Générateurs de vapeur": ["gv"],
    "Turbine HP (et soupapes)": ["soupapes_HP", "HP1", "HP2", "HP3"],
    "Turbine BP": ["BP1", "BP2", "BP3", "BP4"],
    "Pertes d'échappement BP": ["pertes"],
    "Sécheur-surchauffeur": ["secheur", "surchauffeur", "v_sech", "v_surch"],
    "Réchauffeurs HP et BP": ["RHP2", "RHP1", "RBP3", "RBP2", "RBP1", "m_RHP2", "m_RHP1",
                              "m_RBP2", "m_RBP1", "v_RHP2", "v_RHP1", "v_RBP3", "v_RBP2", "v_RBP1"],
    "Bâche dégazante": ["bache"],
    "Condenseur": ["condenseur", "m_cond"],
    "Pompes": ["CEX", "APP"],
}
NEUTRES = ["sep_vv", "s_HP1", "s_HP2", "s_HP3", "s_BP1", "s_BP2", "s_BP3", "fermeture",
           "prim_in", "prim_out", "cw_in", "cw_out"]


def _sgen(comp) -> float:
    """Entropie générée (W/K)."""
    sortie = sum(c.m.val_SI * c.s.val_SI for c in comp.outl)
    entree = sum(c.m.val_SI * c.s.val_SI for c in comp.inl)
    return sortie - entree


def bilan_exergie(modele) -> dict:
    """Exergie (MW) : entrée primaire, électricité nette, destructions par
    groupe de composants, pertes électromécaniques, rejet au milieu."""
    K, c, p = modele.K, modele.c, modele.params
    T0 = c["11"].T.val_SI
    r = modele.resultats()

    # Contrôle : tous les composants sont classés
    classes = {n for g in GROUPES.values() for n in g} | set(NEUTRES)
    manquants = set(K) - classes
    assert not manquants, f"composants non classés : {manquants}"

    ex_primaire = c["P1"].m.val_SI * ((c["P1"].h.val_SI - c["P2"].h.val_SI)
                                      - T0 * (c["P1"].s.val_SI - c["P2"].s.val_SI)) / 1e6
    destructions = {g: T0 * sum(_sgen(K[n]) for n in noms) / 1e6 for g, noms in GROUPES.items()}
    # Les composants « neutres » (répartiteurs, fermeture) ne créent pas
    # d'entropie : on le vérifie plutôt que de le supposer.
    ex_neutres = T0 * sum(_sgen(K[n]) for n in NEUTRES
                          if n not in ("prim_in", "prim_out", "cw_in", "cw_out")) / 1e6

    W_t = r.puissance_turbine_MW
    pertes_em = (W_t * (1 - p.rendement_meca_alternateur)
                 + r.puissance_pompe_MW * (1 / p.rendement_moteur_pompe - 1))
    destructions["Alternateur et moteurs"] = pertes_em

    ex_eau = c["11"].m.val_SI * ((c["12"].h.val_SI - c["11"].h.val_SI)
                                 - T0 * (c["12"].s.val_SI - c["11"].s.val_SI)) / 1e6
    P_nette = r.puissance_electrique_nette_MW
    ecart = ex_primaire - P_nette - sum(destructions.values()) - ex_eau - ex_neutres
    return {
        "T0_C": T0 - 273.15,
        "exergie_primaire_MW": ex_primaire,
        "electricite_nette_MW": P_nette,
        "destructions_MW": destructions,
        "exergie_rejetee_eau_MW": ex_eau,
        "destruction_neutres_MW": ex_neutres,
        "rendement_exergetique": P_nette / ex_primaire,
        "ecart_bilan_MW": ecart,
    }
