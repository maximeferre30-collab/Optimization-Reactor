"""Étude offdesign : effet de la température de l'eau de refroidissement.

Usage :
    python scripts/etude_source_froide.py
Sorties dans results/ : CSV + figures PNG.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from rep_secondaire import ParametresRankine
from rep_secondaire.etude_source_froide import balayage_temperature, sensibilite

RESULTATS = Path(__file__).resolve().parents[1] / "results"

# Style sobre : une seule série par graphique, grille discrète
BLEU = "#2a78d6"
TEXTE = "#0b0b0b"
TEXTE_2 = "#52514e"
GRILLE = "#e4e3df"
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


def tracer(df, T_ref, chemin):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), facecolor=FOND)
    T = df.index.values

    # 1) Puissance électrique nette
    ax = axes[0]
    P = df["puissance_electrique_nette_MW"]
    ax.plot(T, P, color=BLEU, linewidth=2)
    P_ref = P.loc[T_ref]
    ax.plot([T_ref], [P_ref], "o", color=BLEU, markersize=8,
            markeredgecolor=FOND, markeredgewidth=2)
    ax.annotate(f"design {T_ref:.0f} °C : {P_ref:.0f} MWe", (T_ref, P_ref),
                xytext=(10, 10), textcoords="offset points", color=TEXTE)
    pente = sensibilite(df)
    ax.text(0.98, 0.95, f"pente moyenne : {pente:.2f} MWe/°C",
            transform=ax.transAxes, ha="right", va="top", color=TEXTE_2)
    _style(ax, "Puissance électrique nette", "MWe")

    # 2) Pression au condenseur
    ax = axes[1]
    ax.plot(T, df["p_condenseur_mbar"], color=BLEU, linewidth=2)
    _style(ax, "Pression au condenseur", "mbar")

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
    df.to_csv(RESULTATS / "etude_source_froide.csv")

    colonnes = {
        "p_condenseur_mbar": "p_cond [mbar]",
        "T_condenseur_C": "T_cond [°C]",
        "T_sortie_eau_refroidissement_C": "T_rejet [°C]",
        "titre_sortie_turbine": "x_sortie",
        "debit_vapeur_kg_s": "m_vap [kg/s]",
        "puissance_electrique_nette_MW": "P_nette [MWe]",
        "rendement_net": "eta_net",
    }
    affichage = df[list(colonnes)].rename(columns=colonnes)
    print(affichage.iloc[::5].to_string(float_format=lambda v: f"{v:9.3f}"))

    pente = sensibilite(df)
    P_ref = df.loc[T_ref, "puissance_electrique_nette_MW"]
    print(f"\nPente moyenne : {pente:.2f} MWe/°C "
          f"({100 * pente / P_ref:.3f} %/°C de la puissance de design)")
    print(f"Écart 0 °C -> 35 °C : "
          f"{df['puissance_electrique_nette_MW'].iloc[-1] - df['puissance_electrique_nette_MW'].iloc[0]:.1f} MWe")

    tracer(df, T_ref, RESULTATS / "etude_source_froide.png")
    print(f"\nFigure : {RESULTATS / 'etude_source_froide.png'}")


if __name__ == "__main__":
    main()
