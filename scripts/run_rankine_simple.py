"""Résout le cycle de Rankine simple et affiche les résultats.

Usage :
    python scripts/run_rankine_simple.py
"""

from pathlib import Path

import pandas as pd

from rep_secondaire import ParametresRankine, RankineSimple

RESULTATS = Path(__file__).resolve().parents[1] / "results"


def main() -> None:
    params = ParametresRankine()
    modele = RankineSimple(params)
    r = modele.resoudre()

    pd.set_option("display.float_format", lambda v: f"{v:10.4f}")
    print("\n=== États aux points du cycle ===")
    print("(m en kg/s, p en bar, T en °C, h en kJ/kg, s en kJ/kg/K, x titre)")
    print(modele.tableau_etats().to_string())

    print("\n=== Bilan ===")
    print(f"Débit vapeur                  : {r.debit_vapeur_kg_s:8.1f} kg/s")
    print(f"Débit eau de refroidissement  : {r.debit_eau_refroidissement_kg_s:8.1f} kg/s")
    print(f"Pression condenseur           : {r.p_condenseur_mbar:8.1f} mbar")
    print(f"Température de condensation   : {r.T_condenseur_C:8.1f} °C")
    print(f"Titre en sortie turbine       : {r.titre_sortie_turbine:8.3f}")
    print(f"Vitesse annulaire échappement : {r.vitesse_annulaire_m_s:8.1f} m/s "
          f"(section {modele.section_annulaire_m2:.0f} m²)")
    print(f"Perte d'échappement BP        : {r.perte_echappement_MW:8.1f} MW")
    print(f"Puissance thermique GV        : {r.puissance_thermique_MW:8.1f} MW")
    print(f"Puissance mécanique turbine   : {r.puissance_turbine_MW:8.1f} MW")
    print(f"Puissance pompe alimentaire   : {r.puissance_pompe_MW:8.1f} MW")
    print(f"Chaleur rejetée au condenseur : {r.puissance_condenseur_MW:8.1f} MW")
    print(f"Puissance électrique brute    : {r.puissance_electrique_brute_MW:8.1f} MWe")
    print(f"Puissance électrique nette    : {r.puissance_electrique_nette_MW:8.1f} MWe")
    ecart = (r.puissance_thermique_MW + r.puissance_pompe_MW
             - r.puissance_turbine_MW - r.puissance_condenseur_MW)
    print(f"Fermeture du bilan d'énergie  : {ecart:8.2e} MW")
    print()
    print(f"Rendement du cycle (W_net/Q)  : {100 * r.rendement_cycle:6.2f} %")
    print(f"Rendement net électrique      : {100 * r.rendement_net:6.2f} %")
    print(f"Rendement de Carnot (réf.)    : {100 * r.rendement_carnot:6.2f} %")

    RESULTATS.mkdir(exist_ok=True)
    modele.tableau_etats().to_csv(RESULTATS / "rankine_simple_etats.csv")


if __name__ == "__main__":
    main()
