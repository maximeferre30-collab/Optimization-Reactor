"""Étude offdesign : effet de la température de l'eau de refroidissement.

Compare le modèle avec pertes d'échappement BP (référence) au modèle sans
pertes (turbine « idéale » de l'étape 2).

Usage :
    python scripts/etude_source_froide.py
Sorties dans results/ : CSV + figure PNG.
"""

from dataclasses import replace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from rep_secondaire import ParametresRankine
from rep_secondaire.etude_source_froide import (
    balayage_temperature,
    optimum,
    sensibilite,
)

RESULTATS = Path(__file__).resolve().parents[1] / "results"

# Palette validée (slots catégoriels 1 et 2), grille discrète
BLEU = "#2a78d6"     # avec pertes d'échappement (référence)
ORANGE = "#eb6834"   # sans pertes d'échappement
TEXTE = "#0b0b0b"
TEXTE_2 = "#52514e"
GRILLE = "#e4e3df"
ZONE = "#f0efec"
FOND = "#fcfcfb"


def _style(ax, titre, ylabel):
    ax.set_facecolor(FOND)
    ax.set_title(titre, loc="left", color=TEXTE, fontsize=12, fontweight="bold")
    ax.set_xlabel("Température d'entrée de l'eau de refroidissement (°C)",
                  color=TEXTE_2)
    ax.set_ylabel(ylabel, color=TEXTE_2)
    ax.grid(True, color=GRILLE, linewidth=0.8)
    ax.set_axisbelow(True)
    for cote in ("top", "right"):
        ax.spines[cote].set_visible(False)
    for cote in ("left", "bottom"):
        ax.spines[cote].set_color(GRILLE)
    ax.tick_params(colors=TEXTE_2)


def _zone_blocage(ax, df, en_haut=True):
    bloque = df.index[df["echappement_bloque"].astype(bool)]
    if len(bloque):
        ax.axvspan(df.index.min(), bloque.max() + 0.5, color=ZONE, zorder=0)
        ax.text(df.index.min() + 0.3, 0.97 if en_haut else 0.03,
                "échappement\nbloqué", va="top" if en_haut else "bottom",
                transform=ax.get_xaxis_transform(), color=TEXTE_2, fontsize=9)


def tracer(df, df_sans, T_ref, chemin):
    fig, axes = plt.subplots(1, 3, figsize=(17, 4.8), facecolor=FOND)
    T = df.index.values

    # 1) Puissance électrique nette : avec / sans pertes d'échappement
    ax = axes[0]
    _zone_blocage(ax, df, en_haut=False)
    ax.plot(df_sans.index, df_sans["puissance_electrique_nette_MW"], color=ORANGE,
            linewidth=2, linestyle="--", label="sans pertes d'échappement")
    ax.plot(T, df["puissance_electrique_nette_MW"], color=BLEU, linewidth=2,
            label="avec pertes d'échappement")
    T_opt, P_opt = optimum(df)
    ax.plot([T_opt], [P_opt], "o", color=BLEU, markersize=8,
            markeredgecolor=FOND, markeredgewidth=2)
    ax.annotate(f"optimum {T_opt:.0f} °C : {P_opt:.0f} MWe", (T_opt, P_opt),
                xytext=(8, 10), textcoords="offset points", color=TEXTE)
    ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0.22, 0.0),
              labelcolor=TEXTE_2)
    _style(ax, "Puissance électrique nette", "MWe")

    # 2) Pression au condenseur
    ax = axes[1]
    _zone_blocage(ax, df)
    ax.plot(T, df["p_condenseur_mbar"], color=BLEU, linewidth=2)
    _style(ax, "Pression au condenseur", "mbar")

    # 3) Perte d'échappement
    ax = axes[2]
    _zone_blocage(ax, df)
    ax.plot(T, df["perte_echappement_MW"], color=BLEU, linewidth=2)
    ax.set_ylim(bottom=0)
    _style(ax, "Perte d'échappement BP", "MW")

    fig.tight_layout()
    fig.savefig(chemin, dpi=150, facecolor=FOND)
    plt.close(fig)


def main() -> None:
    RESULTATS.mkdir(exist_ok=True)
    params = ParametresRankine()  # design à 15 °C
    T_ref = params.T_eau_refroidissement_C
    temperatures = np.arange(0, 36, 1.0)

    df = balayage_temperature(temperatures, RESULTATS / "design_rankine_simple.json",
                              params)
    df_sans = balayage_temperature(
        temperatures, RESULTATS / "design_sans_pertes.json",
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
    print(affichage.iloc[::5].to_string(float_format=lambda v: f"{v:9.3f}"))

    T_opt, P_opt = optimum(df)
    P_ref = df.loc[T_ref, "puissance_electrique_nette_MW"]
    pente_chaud = sensibilite(df, T_min=T_ref)
    pente_sans = sensibilite(df_sans)
    print(f"\nOptimum : {P_opt:.1f} MWe à {T_opt:.0f} °C")
    print(f"Pente au-dessus de {T_ref:.0f} °C : {pente_chaud:.2f} MWe/°C "
          f"({100 * pente_chaud / P_ref:.3f} %/°C)")
    print(f"Pente sans pertes d'échappement (0-35 °C) : {pente_sans:.2f} MWe/°C")

    tracer(df, df_sans, T_ref, RESULTATS / "etude_source_froide.png")
    print(f"\nFigure : {RESULTATS / 'etude_source_froide.png'}")


if __name__ == "__main__":
    main()
