"""Calcule toutes les études, écrit les figures et les données du rapport.

Usage :
    python scripts/figures_rapport.py            # tout recalculer (~8 min)
    python scripts/figures_rapport.py --cache    # réutiliser les balayages déjà calculés

Pré-requis facultatifs :
    data/meteo_*.csv          (scripts/telecharger_meteo.py) pour la production annuelle
    results/incertitudes.json (scripts/incertitudes.py) pour les incertitudes

Sorties (results/) :
    fig1_cycle_n4_Ts.png          cycle N4 dans le diagramme T-s
    fig2_bilan_sankey.png         bilan d'énergie du cycle N4 au design
    fig3_puissance_n4.png         puissance vs température d'eau (N4 / sans pertes / cycle simple)
    fig4_pertes_echappement.png   courbe de pertes et points de fonctionnement
    fig5_exergie.png              destructions d'exergie par composant
    fig6_production_mensuelle.png météo réelle, deux sites, scénario +2 °C
    fig7_carte_journaliere.png    puissance jour par jour (Chooz)
    fig8_rejets.png               variante circuit ouvert : limites de rejet
    fig9_incertitudes.png         Monte-Carlo et tornade
    rapport_donnees.json          données du rapport interactif
"""

import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd

from rep_secondaire import ParametresRankine, RankineSimple
from rep_secondaire.annuel import CourbesCentrale, carte_journaliere, production, synthese, table_tour
from rep_secondaire.cycle_n4 import CycleN4
from rep_secondaire.diagrammes import bilan_sankey, chemin_Ts, chemin_Ts_n4, cloche_saturation
from rep_secondaire.echappement import _EL, _V
from rep_secondaire.etude_source_froide import balayage_temperature, optimum, sensibilite
from rep_secondaire.exergie import bilan_exergie
from rep_secondaire.figures import BLEU, ORANGE, VERT_EAU, fig_echappement, fig_sankey
from rep_secondaire.figures_n4 import (
    fig_carte_journaliere, fig_comparaison_cycles, fig_exergie, fig_incertitudes,
    fig_mensuel, fig_rejets, fig_Ts_n4, stats_incertitudes,
)
from rep_secondaire.parametres import ParametresN4
from rep_secondaire.rejets import LimitesRejet, carte_puissance
from rep_secondaire.tour import ConceptionTour, TourNaturelle

RACINE = Path(__file__).resolve().parents[1]
RES, DATA = RACINE / "results", RACINE / "data"
T_SWEEP = np.arange(0, 36, 1.0)
VALEURS_PUBLIQUES_N4 = {  # ordres de grandeur publics (EDF, documentation N4)
    "puissance_electrique_brute_MW": 1560.0,
    "T_eau_alimentaire_C": 230.0,
    "p_vapeur_bar": 72.0,
    "debit_vapeur_kg_s": 2400.0,
}


def _liste(a, pas=1, d=4):
    return [round(float(x), d) for x in np.asarray(a)[::pas]]


def balayage(nom, params, cache):
    f = RES / f"balayage_{nom}.csv"
    if cache and f.exists():
        return pd.read_csv(f, index_col=0)
    df = balayage_temperature(T_SWEEP, RES / f"design_{nom}.json", params)
    df.to_csv(f)
    return df


def colonnes(df, cols):
    out = {"T": _liste(df.index)}
    for k in cols:
        out[k] = [bool(v) if isinstance(v, (bool, np.bool_)) else round(float(v), 4) for v in df[k]]
    return out


def main() -> None:
    cache = "--cache" in sys.argv
    RES.mkdir(exist_ok=True)
    pN4, pS = ParametresN4(), ParametresRankine()
    cloche = cloche_saturation()

    # 1) Point de design N4 + exergie + Sankey + validation
    n4 = CycleN4(replace(pN4))
    r = n4.resoudre()
    Ts_n4 = chemin_Ts_n4(n4)
    bex = bilan_exergie(n4)
    bilan = bilan_sankey(r, pN4)
    validation = {k: {"modele": getattr(r, k), "public": v, "ecart_pct": 100 * (getattr(r, k) / v - 1)}
                  for k, v in VALEURS_PUBLIQUES_N4.items()}
    print(f"N4 design : {r.puissance_electrique_brute_MW:.1f} MWe brut, {r.puissance_electrique_nette_MW:.1f} net, "
          f"eta {100 * r.rendement_cycle:.2f} %")

    simple = RankineSimple(replace(pS))
    simple.resoudre()
    Ts_simple = chemin_Ts(simple)

    # 2) Balayages
    df = balayage("n4", pN4, cache)
    df_sans = balayage("n4_sans_pertes", replace(pN4, pertes_echappement=False), cache)
    df_simple = balayage("simple", pS, cache)
    T_opt, P_opt = optimum(df)

    # 3) Tour + météo réelle
    courbes = CourbesCentrale.depuis_balayage(df)
    annuel, carte, cartes, tables = {}, None, {}, {}
    for site in ("chooz", "civaux"):
        f = DATA / f"meteo_{site}.csv"
        if not f.exists():
            print(f"(pas de météo pour {site} : lancer scripts/telecharger_meteo.py)")
            continue
        meteo = pd.read_csv(f, parse_dates=["temps_utc"])
        tab = table_tour(TourNaturelle(ConceptionTour()), courbes, meteo["P_hPa"].mean() * 100)
        tables[site] = {"T": _liste(tab.grid[0]), "HR": _liste(tab.grid[1]),
                        "Z": [[round(float(v), 3) for v in ligne] for ligne in tab.values]}
        P_ref = float(df.loc[15.0, "puissance_electrique_nette_MW"])
        for dT in (0.0, 2.0):
            prod = production(meteo, tab, courbes, dT)
            s = synthese(prod, P_ref)
            s["T_eau_froide_moy_C"] = float(prod["T_eau_froide_C"].mean())
            annuel[f"{site}{'_+2' if dT else ''}"] = s
            if dT == 0:
                cartes[site] = carte_journaliere(prod)
                if site == "chooz":
                    carte = cartes[site]
    if annuel:
        fig_mensuel({
            "Chooz": (annuel["chooz"], BLEU, "-"),
            "Civaux": (annuel["civaux"], VERT_EAU, ":"),
            "Chooz, climat +2 °C": (annuel["chooz_+2"], ORANGE, "--"),
        }, RES / "fig6_production_mensuelle.png")
        fig_carte_journaliere(carte, "Chooz", RES / "fig7_carte_journaliere.png")

    # 4) Limites de rejet (variante circuit ouvert)
    lim = LimitesRejet()
    T_riv = np.arange(0, 31, 1.0)
    Q_riv = np.geomspace(50, 3000, 40)
    Qc = lambda T: np.interp(T, df.index.values, df["puissance_condenseur_MW"].values)  # noqa: E731
    P_adm, _ = carte_puissance(courbes, Qc, T_riv, Q_riv, lim)
    fig_rejets(T_riv, Q_riv, P_adm, lim, RES / "fig8_rejets.png")

    # 5) Incertitudes
    st = None
    f_inc = RES / "incertitudes.json"
    if f_inc.exists():
        st = stats_incertitudes(json.loads(f_inc.read_text(encoding="utf-8")))
        st["pente_nominale"] = float(sensibilite(df, T_min=15))
        fig_incertitudes(st, RES / "fig9_incertitudes.png", st["pente_nominale"])
    else:
        print("(pas d'incertitudes : lancer scripts/incertitudes.py)")

    # 6) Figures du cycle
    fig_Ts_n4(cloche, Ts_n4, RES / "fig1_cycle_n4_Ts.png", d_simple=Ts_simple)
    fig_sankey(bilan, RES / "fig2_bilan_sankey.png")
    fig_comparaison_cycles(df, df_sans, df_simple, RES / "fig3_puissance_n4.png")
    fig_echappement(df, pN4.vitesse_annulaire_blocage_m_s, RES / "fig4_pertes_echappement.png")
    fig_exergie(bex, RES / "fig5_exergie.png")

    # 7) Détail par composant (schéma interactif)
    from rep_secondaire.exergie import _sgen
    T0 = n4.c["11"].T.val_SI
    composants = {}
    for nom, k in n4.K.items():
        d = {"ExD_MW": T0 * _sgen(k) / 1e6 if nom not in ("prim_in", "prim_out", "cw_in", "cw_out") else 0.0}
        for attr in ("P", "Q"):
            par = getattr(k, attr, None)
            if par is not None and getattr(par, "val", None) is not None:
                try:
                    d[f"{attr}_MW"] = float(par.val)
                except (TypeError, ValueError):
                    pass
        d["entrees"] = [[c.label, round(c.T.val, 2), round(c.p.val, 4), round(c.m.val, 2)] for c in k.inl]
        d["sorties"] = [[c.label, round(c.T.val, 2), round(c.p.val, 4), round(c.m.val, 2)] for c in k.outl]
        composants[nom] = d
    debits = {lbl: round(float(c.m.val), 2) for lbl, c in n4.c.items()}

    # 8) Analyses thermodynamiques à la main
    from rep_secondaire.analyse_thermo import (
        analyse_temperatures_moyennes, chemin_hs_n4, decomposition_sensibilite,
        profil_TQ_condenseur, profil_TQ_gv,
    )
    thermo = {
        "decomposition": decomposition_sensibilite(replace(pN4), RES / "decomp.json"),
        "T_moyennes": {"n4": analyse_temperatures_moyennes(n4, "0", "1"),
                       "simple": analyse_temperatures_moyennes(simple, "0", "1")},
        "TQ_gv": profil_TQ_gv(n4), "TQ_condenseur": profil_TQ_condenseur(n4),
        "mollier": chemin_hs_n4(n4),
        "dTc_dTeau": float(np.polyfit(df.index[15:], df["T_condenseur_C"].values[15:], 1)[0]),
    }

    # 9) Code source affiché dans le rapport
    sources = {}
    for rel in ("src/rep_secondaire/cycle_n4.py", "src/rep_secondaire/analyse_thermo.py",
                "src/rep_secondaire/echappement.py", "src/rep_secondaire/tour.py",
                "src/rep_secondaire/exergie.py", "src/rep_secondaire/condenseur.py",
                "src/rep_secondaire/annuel.py", "src/rep_secondaire/incertitudes.py",
                "tests/test_analyse_thermo.py", "tests/test_cycle_n4.py",
                "tests/test_verification_independante.py"):
        sources[rel] = (RACINE / rel).read_text(encoding="utf-8")

    # 10) Données du rapport interactif
    cols = ["p_condenseur_mbar", "T_condenseur_C", "T_sortie_eau_refroidissement_C",
            "vitesse_annulaire_m_s", "echappement_bloque", "perte_echappement_MW",
            "debit_vapeur_kg_s", "puissance_electrique_nette_MW", "rendement_net",
            "titre_sortie_turbine", "p_vapeur_bar", "T_eau_alimentaire_C", "puissance_condenseur_MW"]
    etats = n4.tableau_etats()
    cles_etats = ["1", "1c", "e1", "e2", "e3", "v_sech", "bp_in", "e4", "e5", "e6", "2", "2u",
                  "3", "c4", "a0", "a1", "4", "x_RHP2", "x_bache", "x_RBP1", "P1", "P2"]
    donnees = {
        "parametres": {k: v for k, v in asdict(pN4).items()},
        "design": asdict(r),
        "validation": validation,
        "etats": [{"id": k, **{c: round(float(etats.loc[k, c]), 5) for c in ["m", "p", "T", "h", "s", "x"]}}
                  for k in cles_etats],
        "bilan": bilan,
        "exergie": bex,
        "Ts": {
            "cloche": {"s": _liste(cloche[0], 2), "T": _liste(cloche[1], 2)},
            "n4": {"segments": {k: {"s": _liste(s, 4), "T": _liste(T, 4)} for k, (s, T) in Ts_n4["segments"].items()},
                   "points": Ts_n4["points"]},
            "simple": {"segments": {k: {"s": _liste(s, 4), "T": _liste(T, 4)} for k, (s, T) in Ts_simple["segments"].items()},
                       "points": Ts_simple["points"]},
        },
        "balayage": colonnes(df, cols),
        "balayage_sans_pertes": colonnes(df_sans, ["puissance_electrique_nette_MW"]),
        "balayage_simple": colonnes(df_simple, ["puissance_electrique_nette_MW"]),
        "courbe_EL": {"V": _liste(_V), "EL": _liste(_EL)},
        "synthese": {
            "T_optimum": float(T_opt), "P_optimum": float(P_opt),
            "pente_au_dessus_design": float(sensibilite(df, T_min=15)),
            "pente_simple": float(sensibilite(df_simple, T_min=15)),
            "pente_sans_pertes": float(sensibilite(df_sans)),
            "T_max_blocage": float(df.index[df["echappement_bloque"].astype(bool)].max())
            if df["echappement_bloque"].astype(bool).any() else None,
        },
        "annuel": annuel,
        "carte_chooz": None if carte is None else {
            "annees": [int(a) for a in carte.index], "valeurs": [[None if pd.isna(v) else round(float(v), 1) for v in ligne]
                                                             for ligne in carte.values]},
        "rejets": {"T": _liste(T_riv), "Q": _liste(Q_riv, d=1), "P": [[round(float(v), 1) for v in l] for l in P_adm],
                   "limites": asdict(lim)},
        "incertitudes": st,
        "composants": composants,
        "thermo": thermo,
        "sources": sources,
        "debits": debits,
        "tables_tour": tables,
        "cartes": {site: {"annees": [int(a) for a in c.index],
                          "valeurs": [[None if pd.isna(v) else round(float(v), 1) for v in ligne]
                                      for ligne in c.values]} for site, c in cartes.items()},
        "tour": asdict(ConceptionTour()),
    }
    (RES / "rapport_donnees.json").write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
    print(f"Optimum {P_opt:.1f} MWe à {T_opt:.0f} °C ; pente >15 °C {sensibilite(df, T_min=15):.2f} MWe/°C")
    print(f"Figures et données écrites dans {RES}")


if __name__ == "__main__":
    main()
