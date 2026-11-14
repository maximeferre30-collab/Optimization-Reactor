"""Figures du cycle N4 et des études complémentaires (même charte que figures.py)."""

from __future__ import annotations

import numpy as np

from .figures import (
    BLEU, CLOCHE, FOND, GRILLE, JAUNE, ORANGE, TEXTE, TEXTE_2, VERT_EAU,
    _sauver, _zone_blocage, plt, style,
)

MOIS = ["jan", "fév", "mar", "avr", "mai", "juin", "juil", "août", "sep", "oct", "nov", "déc"]


def _fr(v, d=0):
    return f"{v:,.{d}f}".replace(",", " ").replace(".", ",")


def fig_Ts_n4(cloche, d, chemin, d_simple=None):
    fig, ax = plt.subplots(figsize=(10, 7), facecolor=FOND)
    s_c, T_c = cloche
    ax.plot(s_c, T_c, color=CLOCHE, linewidth=1.2)
    if d_simple is not None:
        for nom, (s, T) in d_simple["segments"].items():
            ax.plot(s, T, color=ORANGE, linewidth=1.5, linestyle="--",
                    label="cycle simple (étapes 1 à 3)" if nom == "turbine" else None)
    for nom, (s, T) in d["segments"].items():
        ax.plot(s, T, color=BLEU, linewidth=2, label="cycle N4 complet" if nom == "GV" else None)
    lib = {"1": ("vapeur vive", (6, 6)), "e3": ("échappement HP", (8, -10)),
           "v_sech": ("sortie sécheur", (8, 2)), "bp_in": ("entrée BP (resurchauffée)", (8, 2)),
           "2": ("fin de détente", (8, 6)), "3": ("condensat", (-12, 12)),
           "a0": ("bâche", (-36, 6)), "4": ("eau alimentaire", (-96, 2))}
    for k, (s, T) in d["points"].items():
        ax.plot(s, T, "o", color=BLEU, markersize=6, markeredgecolor=FOND, markeredgewidth=1.5, zorder=5)
        txt, off = lib[k]
        ax.annotate(txt, (s, T), xytext=off, textcoords="offset points", color=TEXTE, fontsize=9)
    ax.set_xlim(0, 8.0)
    ax.set_ylim(0, 380)
    ax.legend(frameon=False, loc="upper left", labelcolor=TEXTE_2)
    style(ax, "Cycle N4 complet dans le diagramme T-s (eau à 15 °C)",
          "Entropie massique s (kJ/kg/K)", "Température T (°C)")
    _sauver(fig, chemin)


def fig_comparaison_cycles(df_n4, df_n4_sans, df_simple, chemin):
    from .etude_source_froide import optimum

    fig, axes = plt.subplots(1, 2, figsize=(15, 5), facecolor=FOND)
    xl = "Température d'entrée de l'eau de refroidissement (°C)"
    ax = axes[0]
    _zone_blocage(ax, df_n4, en_haut=False)
    ax.plot(df_n4_sans.index, df_n4_sans["puissance_electrique_nette_MW"], color=ORANGE,
            linewidth=2, linestyle="--", label="N4 sans pertes d'échappement")
    ax.plot(df_n4.index, df_n4["puissance_electrique_nette_MW"], color=BLEU, linewidth=2,
            label="N4 complet (référence)")
    T_opt, P_opt = optimum(df_n4)
    ax.plot([T_opt], [P_opt], "o", color=BLEU, markersize=8, markeredgecolor=FOND, markeredgewidth=2)
    ax.annotate(f"optimum {T_opt:.0f} °C : {P_opt:.0f} MWe", (T_opt, P_opt),
                xytext=(8, 10), textcoords="offset points", color=TEXTE)
    ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0.2, 0), labelcolor=TEXTE_2)
    style(ax, "Puissance électrique nette du cycle N4", xl, "MWe")

    ax = axes[1]
    for df, coul, trait, lib in ((df_n4, BLEU, "-", "N4 complet"), (df_simple, VERT_EAU, ":", "cycle simple")):
        P15 = df.loc[15.0, "puissance_electrique_nette_MW"]
        ax.plot(df.index, 100 * (df["puissance_electrique_nette_MW"] / P15 - 1), color=coul,
                linewidth=2, linestyle=trait, label=lib)
    ax.axhline(0, color=TEXTE_2, linewidth=0.8)
    ax.legend(frameon=False, loc="lower left", labelcolor=TEXTE_2)
    style(ax, "Écart relatif à la puissance de design", xl, "% de P(15 °C)")
    fig.tight_layout()
    _sauver(fig, chemin)


def fig_exergie(bex, chemin):
    d = dict(sorted(bex["destructions_MW"].items(), key=lambda kv: kv[1]))
    Ex = bex["exergie_primaire_MW"]
    noms = list(d) + ["Exergie rejetée avec l'eau", "Électricité nette"]
    vals = list(d.values()) + [bex["exergie_rejetee_eau_MW"], bex["electricite_nette_MW"]]
    coul = [ORANGE] * len(d) + [JAUNE, BLEU]
    fig, ax = plt.subplots(figsize=(10, 6), facecolor=FOND)
    y = np.arange(len(noms))
    ax.barh(y, vals, color=coul, height=0.62, linewidth=0)
    for yi, v in zip(y, vals):
        ax.text(v + Ex * 0.006, yi, f"{_fr(v)} MW · {_fr(100 * v / Ex, 1)} %", va="center", color=TEXTE, fontsize=9)
    ax.set_yticks(y, noms)
    ax.set_xlim(0, Ex * 0.92)
    style(ax, f"Bilan d'exergie : {_fr(Ex)} MW fournis par le primaire (état mort {bex['T0_C']:.0f} °C)", "MW", "")
    ax.grid(axis="y", visible=False)
    ax.text(0.99, 0.02, f"Rendement exergétique {_fr(100 * bex['rendement_exergetique'], 1)} %  ·  "
            f"bilan fermé à {abs(bex['ecart_bilan_MW']):.0e} MW près",
            transform=ax.transAxes, ha="right", color=TEXTE_2, fontsize=9)
    _sauver(fig, chemin)


def fig_mensuel(syntheses: dict, chemin):
    """syntheses : {libellé: (synthese, couleur, trait)} ; la 1re reçoit la bande."""
    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor=FOND)
    x = np.arange(1, 13)
    for i, (lib, (s, coul, trait)) in enumerate(syntheses.items()):
        m = s["mensuel"]
        if i == 0:
            ax.fill_between(x, m["P_min"], m["P_max"], color=coul, alpha=0.15, linewidth=0,
                            label=f"{lib} : 5e-95e centile horaire")
        ax.plot(x, m["P"], color=coul, linewidth=2, linestyle=trait, marker="o", markersize=5,
                label=f"{lib} : moyenne mensuelle")
    ax.set_xticks(x, MOIS)
    ax.legend(frameon=False, loc="lower left", labelcolor=TEXTE_2, fontsize=9)
    style(ax, "Puissance nette mois par mois, météo réelle 2015-2024", "", "MWe")
    _sauver(fig, chemin)


def fig_carte_journaliere(carte, site, chemin):
    fig, ax = plt.subplots(figsize=(13, 4.2), facecolor=FOND)
    Z = carte.values
    im = ax.imshow(Z, aspect="auto", cmap="Blues", interpolation="nearest",
                   extent=[0.5, Z.shape[1] + 0.5, carte.index.max() + 0.5, carte.index.min() - 0.5])
    cb = fig.colorbar(im, ax=ax, pad=0.01)
    cb.set_label("MWe (moyenne journalière)", color=TEXTE_2)
    cb.ax.tick_params(colors=TEXTE_2)
    debuts = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
    ax.set_xticks(debuts, MOIS)
    ax.set_yticks(carte.index)
    style(ax, f"Puissance nette jour par jour à {site} (foncé = plus de puissance)", "", "")
    ax.grid(False)
    _sauver(fig, chemin)


def fig_rejets(T_riv, Q_riv, P, lim, chemin):
    fig, ax = plt.subplots(figsize=(9.5, 6), facecolor=FOND)
    niveaux = np.arange(0, 1701, 100)
    cs = ax.contourf(Q_riv, T_riv, P, levels=niveaux, cmap="Blues")
    lignes = ax.contour(Q_riv, T_riv, P, levels=[800, 1200, 1500], colors=TEXTE_2, linewidths=0.8)
    ax.clabel(lignes, fmt="%d MWe", fontsize=8, colors=TEXTE)
    cb = fig.colorbar(cs, ax=ax, pad=0.01)
    cb.set_label("Puissance nette admissible (MWe)", color=TEXTE_2)
    cb.ax.tick_params(colors=TEXTE_2)
    ax.set_xscale("log")
    style(ax, "Variante circuit ouvert : puissance admise par les limites de rejet",
          "Débit de la rivière (m³/s, échelle log)", "Température de la rivière (°C)")
    ax.grid(False)
    ax.text(0.01, 0.01, f"Limites ILLUSTRATIVES : ΔT rivière ≤ {lim.dT_max_K:.0f} K, "
            f"T aval ≤ {lim.T_aval_max_C:.0f} °C (chaque site a son arrêté)",
            transform=ax.transAxes, color=TEXTE, fontsize=8.5,
            bbox=dict(facecolor=FOND, edgecolor=GRILLE, boxstyle="round,pad=0.3"))
    _sauver(fig, chemin)


def stats_incertitudes(inc) -> dict:
    ok = [r for r in inc["monte_carlo"] if "erreur" not in r]
    P = np.array([r["P_nette"] for r in ok])
    pentes = np.array([r["pente_15_35"] for r in ok])
    Topt = np.array([r["T_optimum"] for r in ok])
    Pd = np.array([r["P_design"] for r in ok])
    tornade = {}
    for r in inc["tornade"]:
        if "erreur" in r:
            continue
        k, cote = r["surcharges"]["_tornade"]
        tornade.setdefault(k, {})[cote] = r["pente_15_35"]
    q = lambda a: [float(x) for x in np.percentile(a, [5, 50, 95])]  # noqa: E731
    return {
        "n_ok": len(ok), "n_total": len(inc["monte_carlo"]),
        "T": inc["temperatures"],
        "P_q05": [float(x) for x in np.percentile(P, 5, axis=0)],
        "P_q50": [float(x) for x in np.percentile(P, 50, axis=0)],
        "P_q95": [float(x) for x in np.percentile(P, 95, axis=0)],
        "pente_q": q(pentes), "T_opt_q": q(Topt), "P_design_q": q(Pd),
        "tornade": tornade,
    }


def fig_incertitudes(st, chemin, pente_nominale):
    from .incertitudes import LIBELLES

    T = np.array(st["T"], float)
    fig, axes = plt.subplots(1, 2, figsize=(16, 5.5), facecolor=FOND,
                             gridspec_kw={"width_ratios": [1.1, 1]})
    ax = axes[0]
    ax.fill_between(T, st["P_q05"], st["P_q95"], color=BLEU, alpha=0.18, linewidth=0,
                    label="intervalle 5-95 %")
    ax.plot(T, st["P_q50"], color=BLEU, linewidth=2, label="médiane")
    ax.legend(frameon=False, loc="lower left", labelcolor=TEXTE_2)
    p, t = st["pente_q"], st["T_opt_q"]
    ax.text(0.98, 0.97, f"{st['n_ok']} tirages (hypercube latin)\n"
            f"pente 15-35 °C : {_fr(p[1], 2)} MWe/°C  [{_fr(p[0], 2)} ; {_fr(p[2], 2)}]\n"
            f"optimum : {t[1]:.0f} °C  [{t[0]:.0f} ; {t[2]:.0f}]",
            transform=ax.transAxes, ha="right", va="top", color=TEXTE, fontsize=9)
    style(ax, "Puissance nette : propagation des incertitudes",
          "Température d'entrée de l'eau de refroidissement (°C)", "MWe")

    ax = axes[1]
    ref = pente_nominale  # tornade : écarts au cas nominal
    tor = st["tornade"]
    ordre = sorted(tor, key=lambda k: abs(tor[k].get("haut", ref) - tor[k].get("bas", ref)))
    y = np.arange(len(ordre))
    for yi, k in zip(y, ordre):
        for cote, coul in (("bas", ORANGE), ("haut", BLEU)):
            v = tor[k].get(cote, ref) - ref
            ax.barh(yi, v, color=coul, height=0.6, edgecolor=FOND, linewidth=1.5,
                    label=("hypothèse à sa borne basse" if cote == "bas" else "hypothèse à sa borne haute")
                    if yi == len(ordre) - 1 else None)
    ax.axvline(0, color=TEXTE_2, linewidth=1)
    ax.set_yticks(y, [LIBELLES[k] for k in ordre])
    ax.legend(frameon=False, loc="lower right", labelcolor=TEXTE_2, fontsize=9)
    style(ax, f"Tornade : effet sur la pente (nominal {_fr(ref, 2)} MWe/°C)", "écart au cas nominal (MWe/°C)", "")
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    _sauver(fig, chemin)
