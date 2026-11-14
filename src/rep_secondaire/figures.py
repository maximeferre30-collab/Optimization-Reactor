"""Figures du rapport (matplotlib, export PNG haute résolution).

Charte : palette catégorielle validée (daltonisme, contraste), une couleur
par entité, toujours dans le même ordre ; texte en encre neutre ; grille
discrète ; un seul axe des ordonnées par graphique.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .echappement import _EL, _V, perte_echappement_kJ_kg

# Slots catégoriels 1 à 4 (ordre fixe)
BLEU, ORANGE, VERT_EAU, JAUNE = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
TEXTE, TEXTE_2, GRILLE, ZONE, FOND = "#0b0b0b", "#52514e", "#e4e3df", "#f0efec", "#fcfcfb"
CLOCHE = "#9b9a94"
DPI = 200


def style(ax, titre, xlabel, ylabel):
    ax.set_facecolor(FOND)
    ax.set_title(titre, loc="left", color=TEXTE, fontsize=12, fontweight="bold")
    ax.set_xlabel(xlabel, color=TEXTE_2)
    ax.set_ylabel(ylabel, color=TEXTE_2)
    ax.grid(True, color=GRILLE, linewidth=0.8)
    ax.set_axisbelow(True)
    for cote in ("top", "right"):
        ax.spines[cote].set_visible(False)
    for cote in ("left", "bottom"):
        ax.spines[cote].set_color(GRILLE)
    ax.tick_params(colors=TEXTE_2)


def _sauver(fig, chemin):
    fig.savefig(chemin, dpi=DPI, facecolor=FOND, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------- #
def fig_Ts(cloche, chemins: dict, chemin):
    """chemins : {libellé: (données chemin_Ts, couleur, style de trait)}."""
    fig, ax = plt.subplots(figsize=(9, 6.5), facecolor=FOND)
    s_c, T_c = cloche
    ax.plot(s_c, T_c, color=CLOCHE, linewidth=1.2)
    ax.text(4.4, 345, "courbe de saturation", color=TEXTE_2, fontsize=9, ha="center")

    for i, (libelle, (d, couleur, trait)) in enumerate(chemins.items()):
        for nom, (s, T) in d["segments"].items():
            ax.plot(s, T, color=couleur, linewidth=2, linestyle=trait,
                    label=libelle if nom == "turbine" else None)
        if i == 0:  # repères d'état sur le cas de référence
            decal = {"1": (6, 6), "2": (-14, 8), "2u": (6, 8), "4": (-26, 8)}
            libelle_pt = {"4": "3≈4"}
            for k, (s, T) in d["points"].items():
                ax.plot(s, T, "o", color=couleur, markersize=6,
                        markeredgecolor=FOND, markeredgewidth=1.5, zorder=5)
                if k in decal:
                    ax.annotate(libelle_pt.get(k, k), (s, T), xytext=decal[k],
                                textcoords="offset points", color=TEXTE,
                                fontsize=10, fontweight="bold")

    notes = [(4.45, 250, "GV : vaporisation\n(80 → 72 bar)"),
             (1.25, 150, "GV : chauffage\nde l'eau\nalimentaire"),
             (6.35, 170, "détente\nturbine"),
             (3.3, 33, "condensation")]
    for s, T, txt in notes:
        ax.text(s, T, txt, color=TEXTE_2, fontsize=9, ha="center")

    ax.set_xlim(0, 8.0)
    ax.set_ylim(0, 380)
    ax.legend(frameon=False, loc="upper left", labelcolor=TEXTE_2)
    ax.text(0.99, 0.01, "2 : fin de détente (ELEP) · 2u : après pertes d'échappement (UEEP)"
            " · pompe 3→4 quasi invisible", transform=ax.transAxes, ha="right",
            va="bottom", color=TEXTE_2, fontsize=8.5)
    style(ax, "Cycle dans le diagramme T-s", "Entropie massique s (kJ/kg/K)",
          "Température T (°C)")
    _sauver(fig, chemin)


# --------------------------------------------------------------------- #
def _bande(ax, x0, x1, y0a, y0b, y1a, y1b, couleur):
    x = np.linspace(x0, x1, 100)
    t = (x - x0) / (x1 - x0)
    lisse = t * t * (3 - 2 * t)
    bas = y0a + (y1a - y0a) * lisse
    haut = y0b + (y1b - y0b) * lisse
    ax.fill_between(x, bas, haut, color=couleur, alpha=0.85, linewidth=0)


def fig_sankey(bilan: dict, chemin):
    Q = bilan["Puissance GV"]
    sorties = [
        ("Électricité nette", BLEU),
        ("Chaleur rejetée au condenseur", ORANGE),
        ("Pertes d'échappement BP (rejetées au condenseur)", VERT_EAU),
        ("Pertes alternateur + moteur de pompe", JAUNE),
    ]
    ech = 1.0 / Q
    ecart = 0.05
    fig, ax = plt.subplots(figsize=(11, 6), facecolor=FOND)
    ax.set_facecolor(FOND)

    # Colonne d'entrée
    ax.add_patch(plt.Rectangle((-0.04, 0), 0.04, 1.0, color=TEXTE_2))
    ax.text(-0.06, 0.5, f"Générateurs\nde vapeur\n{Q:,.0f} MW".replace(",", " "),
            ha="right", va="center", color=TEXTE, fontsize=11, fontweight="bold")

    # Sorties empilées de haut en bas avec un écart constant
    hauteur_tot = 1.0 + ecart * (len(sorties) - 1)
    y_g = 1.0
    y_d = 0.5 + hauteur_tot / 2
    y_label_max = np.inf
    for nom, couleur in sorties:
        h = bilan[nom] * ech
        _bande(ax, 0, 1, y_g - h, y_g, y_d - h, y_d, couleur)
        ax.add_patch(plt.Rectangle((1, y_d - h), 0.03, max(h, 0.004), color=couleur))
        pct = f"{100 * bilan[nom] / Q:.1f}".replace(".", ",")
        valeur = f"{bilan[nom]:,.0f}".replace(",", " ")
        y_lab = min(y_d - h / 2, y_label_max)  # évite le chevauchement
        ax.text(1.05, y_lab, f"{nom}\n{valeur} MW · {pct} %",
                va="center", color=TEXTE, fontsize=10)
        y_label_max = y_lab - 0.11
        y_g -= h
        y_d -= h + ecart

    ax.set_xlim(-0.45, 1.75)
    ax.set_ylim(-0.3, 1.12)
    ax.axis("off")
    ax.set_title("Bilan d'énergie au point de design (eau à 15 °C)", loc="left",
                 color=TEXTE, fontsize=12, fontweight="bold")
    ax.text(-0.45, -0.28, f"Bilan fermé à {abs(bilan['écart de bilan']):.1e} MW près. "
            "Le travail de la pompe (~16 MW) revient au fluide et ressort au condenseur.",
            color=TEXTE_2, fontsize=8.5)
    _sauver(fig, chemin)


# --------------------------------------------------------------------- #
def _zone_blocage(ax, df, en_haut=True):
    bloque = df.index[df["echappement_bloque"].astype(bool)]
    if len(bloque):
        ax.axvspan(df.index.min(), bloque.max() + 0.5, color=ZONE, zorder=0)
        ax.text(df.index.min() + 0.3, 0.97 if en_haut else 0.03,
                "échappement\nbloqué", va="top" if en_haut else "bottom",
                transform=ax.get_xaxis_transform(), color=TEXTE_2, fontsize=9)


def fig_sensibilite(df, df_sans, chemin):
    from .etude_source_froide import optimum

    xl = "Température d'entrée de l'eau de refroidissement (°C)"
    fig, axes = plt.subplots(1, 3, figsize=(17, 4.8), facecolor=FOND)
    T = df.index.values

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
    style(ax, "Puissance électrique nette", xl, "MWe")

    ax = axes[1]
    _zone_blocage(ax, df)
    ax.plot(T, df["p_condenseur_mbar"], color=BLEU, linewidth=2)
    style(ax, "Pression au condenseur", xl, "mbar")

    ax = axes[2]
    _zone_blocage(ax, df, en_haut=False)
    ax.plot(T, df["perte_echappement_MW"], color=BLEU, linewidth=2)
    ax.set_ylim(bottom=0)
    style(ax, "Perte d'échappement BP", xl, "MW")

    fig.tight_layout()
    _sauver(fig, chemin)


# --------------------------------------------------------------------- #
def fig_echappement(df, V_blocage, chemin):
    fig, ax = plt.subplots(figsize=(9, 5.5), facecolor=FOND)
    V = np.linspace(_V.min(), _V.max(), 300)
    ax.axvspan(V_blocage, _V.max() + 30, color=ZONE, zorder=0)
    ax.text(V_blocage + 8, 0.95, "blocage", transform=ax.get_xaxis_transform(),
            color=TEXTE_2, fontsize=9, va="top")
    ax.plot(V, [perte_echappement_kJ_kg(v) for v in V], color=BLEU, linewidth=2,
            label="courbe de perte EL(V) (générique, forme SCC)")

    bloque_masque = df["echappement_bloque"].astype(bool)
    libre = df[~bloque_masque]
    a_etiqueter = [T for T in libre.index if T % 5 == 0]
    for T in a_etiqueter:
        v = libre.loc[T, "vitesse_annulaire_m_s"]
        el = perte_echappement_kJ_kg(v)
        ax.plot(v, el, "o", color=BLEU, markersize=8, markeredgecolor=FOND,
                markeredgewidth=2, zorder=5)
        txt = f"{T:.0f} °C" + (" (design)" if T == 15 else "")
        ax.annotate(txt, (v, el), xytext=(0, -18), textcoords="offset points",
                    ha="center", color=TEXTE, fontsize=9)
    bloque = df[bloque_masque]
    if len(bloque):
        el = perte_echappement_kJ_kg(V_blocage)
        ax.plot(V_blocage, el, "o", color=BLEU, markersize=8, markeredgecolor=FOND,
                markeredgewidth=2, zorder=5)
        ax.annotate(f"eau à {bloque.index.min():.0f}–{bloque.index.max():.0f} °C\n"
                    "(écoulement bloqué)", (V_blocage, el), xytext=(-10, -4),
                    textcoords="offset points", ha="right", va="top",
                    color=TEXTE, fontsize=9)

    ax.set_xlim(_V.min() - 10, _V.max() + 30)
    ax.set_ylim(0, _EL.max() * 1.1)
    ax.legend(frameon=False, loc="upper left", labelcolor=TEXTE_2)
    style(ax, "Pertes d'échappement BP et points de fonctionnement",
          "Vitesse axiale dans la section annulaire de sortie (m/s)",
          "Perte EL (kJ/kg, avant correction d'humidité)")
    _sauver(fig, chemin)
