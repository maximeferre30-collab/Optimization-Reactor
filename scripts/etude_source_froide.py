"""Étude offdesign : effet de la température de l'eau de refroidissement.

Compare le modèle avec pertes d'échappement BP (référence) au modèle sans
pertes. Affiche un tableau de synthèse dans la console.

Usage :
    python scripts/etude_source_froide.py
Sorties dans results/ : CSV + simple_sensibilite.png.
(Pour toutes les figures et le rapport : scripts/figures_rapport.py.)
"""

from dataclasses import replace
from pathlib import Path

import numpy as np

from rep_secondaire import ParametresRankine
from rep_secondaire.etude_source_froide import balayage_temperature, optimum, sensibilite
from rep_secondaire.figures import fig_sensibilite

RESULTATS = Path(__file__).resolve().parents[1] / "results"


def main() -> None:
    RESULTATS.mkdir(exist_ok=True)
    params = ParametresRankine()  # design à 15 °C
    T_ref = params.T_eau_refroidissement_C
    temperatures = np.arange(0, 36, 1.0)

    df = balayage_temperature(temperatures, RESULTATS / "design_rankine_simple.json", params)
    df_sans = balayage_temperature(temperatures, RESULTATS / "design_sans_pertes.json",
                                   replace(params, pertes_echappement=False))
    df.to_csv(RESULTATS / "etude_source_froide.csv")
    df_sans.to_csv(RESULTATS / "etude_source_froide_sans_pertes.csv")

    colonnes = {
        "p_condenseur_mbar": "p_cond [mbar]",
        "T_sortie_eau_refroidissement_C": "T_rejet [°C]",
        "vitesse_annulaire_m_s": "V_ann [m/s]",
        "echappement_bloque": "bloque",
        "perte_echappement_MW": "P_ech [MW]",
        "debit_vapeur_kg_s": "m_vap [kg/s]",
        "puissance_electrique_nette_MW": "P_nette [MWe]",
        "rendement_net": "eta_net",
    }
    affichage = df[list(colonnes)].rename(columns=colonnes)
    affichage["P_nette sans pertes [MWe]"] = df_sans["puissance_electrique_nette_MW"]
    print(affichage.iloc[::5].to_string(float_format=lambda v: f"{v:9.3f}"))

    T_opt, P_opt = optimum(df)
    P_ref = df.loc[T_ref, "puissance_electrique_nette_MW"]
    pente_chaud = sensibilite(df, T_min=T_ref)
    print(f"\nOptimum : {P_opt:.1f} MWe à {T_opt:.0f} °C")
    print(f"Pente au-dessus de {T_ref:.0f} °C : {pente_chaud:.2f} MWe/°C "
          f"({100 * pente_chaud / P_ref:.3f} %/°C)")
    print(f"Pente sans pertes d'échappement (0-35 °C) : {sensibilite(df_sans):.2f} MWe/°C")

    fig_sensibilite(df, df_sans, RESULTATS / "simple_sensibilite.png")
    print(f"\nFigure : {RESULTATS / 'simple_sensibilite.png'}")


if __name__ == "__main__":
    main()
