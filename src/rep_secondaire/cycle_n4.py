"""Cycle secondaire complet type N4 : HP, sécheur-surchauffeur, BP, soutirages.

Topologie (simplifiée par rapport à la tranche réelle, mais complète dans son
principe) :

  Primaire ──► [GV] ──► vapeur vive ─┬─► HP1 ─► HP2 ─► HP3 ─► [Sécheur] ─► [Surchauffeur] ─► BP1 ─► BP2 ─► BP3 ─► BP4 ─► [Pertes éch.] ─► [Condenseur]
                ▲                    │      │      │      │      │ purge            ▲ purge vers RHP2  │      │      │                                │
                │                    └──────┼──────┼──────┼──────┼──────────────────┘                   │      │      │                                ▼
                │                     sout. RHP2  RHP1   bâche   bâche                              RBP3   RBP2   RBP1                         [Pompe extraction]
                │                                                                                                                                │
                └── [RHP2] ◄── [RHP1] ◄── [Pompe alimentaire] ◄── [Bâche dégazante] ◄── [RBP3] ◄── [RBP2] ◄── [RBP1] ◄─────────────────────────┘

- 3 tronçons HP (soutirages vers RHP2, RHP1, puis échappement HP vers la bâche
  et le sécheur), 4 tronçons BP (soutirages vers RBP3, RBP2, RBP1).
- Réchauffeurs fermés (Condenser TESPy : purge en liquide saturé) avec
  purges en cascade : surchauffeur -> RHP2 -> RHP1 -> bâche ;
  RBP3 -> RBP2 -> RBP1 -> condenseur.
- Bâche dégazante = réchauffeur à mélange (Merge, sortie en liquide saturé).
- GV modélisé avec son côté primaire (HeatExchanger) : en offdesign, la
  pression vapeur résulte du UA du GV et des températures primaires.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from tespy.components import (
    Condenser,
    CycleCloser,
    DropletSeparator,
    HeatExchanger,
    Merge,
    Pump,
    SimpleHeatExchanger,
    Sink,
    Source,
    Splitter,
    Turbine,
    Valve,
)
from tespy.connections import Connection
from tespy.networks import Network

from CoolProp.CoolProp import PropsSI

from .condenseur import facteur_UA
from .echappement import LigneDetente, etat_echappement, section_annulaire
from .parametres import ParametresN4
from .rankine_simple import ResultatsRankine

EAU = {"water": 1.0}
# Tronçons de turbine : (entrée, sortie)
TRONCONS = {"HP1": ("1c", "e1"), "HP2": ("e1a", "e2"), "HP3": ("e2a", "e3"),
            "BP1": ("bp_in", "e4"), "BP2": ("e4a", "e5"), "BP3": ("e5a", "e6"),
            "BP4": ("e6a", "2")}


def humidite(p_Pa: float, h: float) -> float:
    """Humidité (fraction massique de liquide) ; 0 en vapeur surchauffée."""
    h_g = PropsSI("H", "P", p_Pa, "Q", 1, "water")
    if h >= h_g:
        return 0.0
    return 1.0 - PropsSI("Q", "P", p_Pa, "H", h, "water")
TOL_MW = 1e-4
ITER_MAX = 60


@dataclass
class ResultatsN4(ResultatsRankine):
    T_eau_alimentaire_C: float
    p_vapeur_bar: float
    puissance_HP_MW: float
    puissance_BP_MW: float
    puissance_pompe_extraction_MW: float
    puissance_pompe_alimentaire_MW: float
    humidite_entree_BP_pourcent: float
    T_surchauffe_C: float
    debit_condenseur_kg_s: float
    debit_primaire_kg_s: float


class CycleN4:
    """Construit, résout et exploite le modèle TESPy du cycle N4."""

    def __init__(self, params: ParametresN4 | None = None):
        self.params = params or ParametresN4()
        self.nw = Network(iterinfo=False)
        self.nw.units.set_defaults(
            temperature="degC", temperature_difference="delta_degC",
            pressure="bar", pressure_difference="bar", enthalpy="kJ/kg",
            entropy="kJ/kg/K", power="MW", heat="MW",
        )
        self.section_annulaire_m2 = None
        self.etat_ech = None
        self._construire()

    # ------------------------------------------------------------------ #
    def _construire(self) -> None:
        K = {}  # composants
        K["prim_in"] = Source("primaire chaud")
        K["prim_out"] = Sink("primaire froid")
        K["gv"] = HeatExchanger("generateur de vapeur")
        K["fermeture"] = CycleCloser("fermeture de cycle")
        K["sep_vv"] = Splitter("repartition vapeur vive", num_out=2)
        for n in ("HP1", "HP2", "HP3", "BP1", "BP2", "BP3", "BP4"):
            K[n] = Turbine(n)
        for n in ("s_HP1", "s_HP2", "s_HP3", "s_BP1", "s_BP2", "s_BP3"):
            K[n] = Splitter(n, num_out=2)
        K["secheur"] = DropletSeparator("secheur")
        K["surchauffeur"] = Condenser("surchauffeur")
        for n in ("RHP2", "RHP1", "RBP3", "RBP2", "RBP1"):
            K[n] = Condenser(n)
        K["m_RHP2"] = Merge("melange RHP2", num_in=2)
        K["m_RHP1"] = Merge("melange RHP1", num_in=2)
        K["m_RBP2"] = Merge("melange RBP2", num_in=2)
        K["m_RBP1"] = Merge("melange RBP1", num_in=2)
        K["m_cond"] = Merge("melange condenseur", num_in=2)
        K["bache"] = Merge("bache degazante", num_in=4)
        for n in ("v_surch", "v_RHP2", "v_RHP1", "v_RBP3", "v_RBP2", "v_RBP1", "v_sech", "soupapes_HP"):
            K[n] = Valve(n)
        K["pertes"] = SimpleHeatExchanger("pertes echappement")
        K["condenseur"] = Condenser("condenseur")
        K["CEX"] = Pump("pompe extraction")
        K["APP"] = Pump("pompe alimentaire")
        K["cw_in"] = Source("eau refroidissement")
        K["cw_out"] = Sink("rejet refroidissement")
        self.K = K

        C = {}

        def lien(lbl, a, pa, b, pb):
            C[lbl] = Connection(K[a], pa, K[b], pb, label=lbl)

        # Primaire
        lien("P1", "prim_in", "out1", "gv", "in1")
        lien("P2", "gv", "out1", "prim_out", "in1")
        # Vapeur vive
        lien("0", "fermeture", "out1", "gv", "in2")
        lien("1", "gv", "out2", "sep_vv", "in1")
        lien("1a", "sep_vv", "out1", "soupapes_HP", "in1")
        lien("1c", "soupapes_HP", "out1", "HP1", "in1")
        lien("1b", "sep_vv", "out2", "surchauffeur", "in1")
        # Corps HP
        lien("e1", "HP1", "out1", "s_HP1", "in1")
        lien("e1a", "s_HP1", "out1", "HP2", "in1")
        lien("x_RHP2", "s_HP1", "out2", "m_RHP2", "in1")
        lien("e2", "HP2", "out1", "s_HP2", "in1")
        lien("e2a", "s_HP2", "out1", "HP3", "in1")
        lien("x_RHP1", "s_HP2", "out2", "m_RHP1", "in1")
        lien("e3", "HP3", "out1", "s_HP3", "in1")
        lien("e3a", "s_HP3", "out1", "secheur", "in1")
        lien("x_bache", "s_HP3", "out2", "bache", "in1")
        # Sécheur-surchauffeur
        lien("purge_sech", "secheur", "out1", "v_sech", "in1")
        lien("purge_sech_b", "v_sech", "out1", "bache", "in2")
        lien("v_sech", "secheur", "out2", "surchauffeur", "in2")
        lien("bp_in", "surchauffeur", "out2", "BP1", "in1")
        lien("d_surch", "surchauffeur", "out1", "v_surch", "in1")
        lien("d_surch_b", "v_surch", "out1", "m_RHP2", "in2")
        # Réchauffeurs HP (côté vapeur)
        lien("h_RHP2", "m_RHP2", "out1", "RHP2", "in1")
        lien("d_RHP2", "RHP2", "out1", "v_RHP2", "in1")
        lien("d_RHP2_b", "v_RHP2", "out1", "m_RHP1", "in2")
        lien("h_RHP1", "m_RHP1", "out1", "RHP1", "in1")
        lien("d_RHP1", "RHP1", "out1", "v_RHP1", "in1")
        lien("d_RHP1_b", "v_RHP1", "out1", "bache", "in3")
        # Corps BP
        lien("e4", "BP1", "out1", "s_BP1", "in1")
        lien("e4a", "s_BP1", "out1", "BP2", "in1")
        lien("x_RBP3", "s_BP1", "out2", "RBP3", "in1")
        lien("e5", "BP2", "out1", "s_BP2", "in1")
        lien("e5a", "s_BP2", "out1", "BP3", "in1")
        lien("x_RBP2", "s_BP2", "out2", "m_RBP2", "in1")
        lien("e6", "BP3", "out1", "s_BP3", "in1")
        lien("e6a", "s_BP3", "out1", "BP4", "in1")
        lien("x_RBP1", "s_BP3", "out2", "m_RBP1", "in1")
        lien("2", "BP4", "out1", "pertes", "in1")
        lien("2u", "pertes", "out1", "m_cond", "in1")
        # Réchauffeurs BP (côté vapeur), purges en cascade
        lien("d_RBP3", "RBP3", "out1", "v_RBP3", "in1")
        lien("d_RBP3_b", "v_RBP3", "out1", "m_RBP2", "in2")
        lien("h_RBP2", "m_RBP2", "out1", "RBP2", "in1")
        lien("d_RBP2", "RBP2", "out1", "v_RBP2", "in1")
        lien("d_RBP2_b", "v_RBP2", "out1", "m_RBP1", "in2")
        lien("h_RBP1", "m_RBP1", "out1", "RBP1", "in1")
        lien("d_RBP1", "RBP1", "out1", "v_RBP1", "in1")
        lien("d_RBP1_b", "v_RBP1", "out1", "m_cond", "in2")
        lien("h_cond", "m_cond", "out1", "condenseur", "in1")
        # Poste d'eau
        lien("3", "condenseur", "out1", "CEX", "in1")
        lien("c1", "CEX", "out1", "RBP1", "in2")
        lien("c2", "RBP1", "out2", "RBP2", "in2")
        lien("c3", "RBP2", "out2", "RBP3", "in2")
        lien("c4", "RBP3", "out2", "bache", "in4")
        lien("a0", "bache", "out1", "APP", "in1")
        lien("a1", "APP", "out1", "RHP1", "in2")
        lien("a2", "RHP1", "out2", "RHP2", "in2")
        lien("4", "RHP2", "out2", "fermeture", "in1")
        # Eau de refroidissement
        lien("11", "cw_in", "out1", "condenseur", "in2")
        lien("12", "condenseur", "out2", "cw_out", "in1")

        self.nw.add_conns(*C.values())
        self.c = C
        self.appliquer_parametres()

    # ------------------------------------------------------------------ #
    def appliquer_parametres(self) -> None:
        p, K, c = self.params, self.K, self.c
        ps = p.p_soutirages_bar

        # Primaire et GV
        c["P1"].set_attr(fluid=EAU, p=p.p_primaire_bar, T=p.T_primaire_chaud_C)
        c["P2"].set_attr(T=p.T_primaire_froid_C)
        K["gv"].set_attr(Q=-p.puissance_thermique_MW, dp1=0.0, dp2=p.dp_gv_bar)
        c["1"].set_attr(p=p.p_vapeur_bar, x=p.titre_vapeur)
        c["0"].set_attr(fluid=EAU)

        # Turbines et pressions de soutirage
        for n in ("HP1", "HP2", "HP3"):
            K[n].set_attr(eta_s=p.rendement_isentropique_HP)
        for n in ("BP1", "BP2", "BP3", "BP4"):
            K[n].set_attr(eta_s=p.rendement_isentropique_BP)
        for lbl, cle in (("e1", "RHP2"), ("e2", "RHP1"), ("e3", "bache"),
                         ("e4", "RBP3"), ("e5", "RBP2"), ("e6", "RBP1")):
            c[lbl].set_attr(p=ps[cle])

        # Sécheur-surchauffeur : surchauffe par vapeur vive
        K["surchauffeur"].set_attr(dp1=0.0, dp2=p.dp_surchauffeur_bar, ttd_u=p.ttd_surchauffeur_K)
        K["soupapes_HP"].set_attr(dp=p.dp_admission_HP_bar)

        # Réchauffeurs fermés
        for n in ("RHP2", "RHP1"):
            K[n].set_attr(dp1=0.0, dp2=p.dp_rechauffeurs_HP_bar, ttd_u=p.ttd_rechauffeurs_K)
        for n in ("RBP3", "RBP2", "RBP1"):
            K[n].set_attr(dp1=0.0, dp2=p.dp_rechauffeurs_BP_bar, ttd_u=p.ttd_rechauffeurs_K)

        # Bâche : sortie en liquide saturé
        c["a0"].set_attr(x=0.0)

        # Pompes
        K["CEX"].set_attr(eta_s=p.rendement_isentropique_pompe)
        K["APP"].set_attr(eta_s=p.rendement_isentropique_pompe)

        # Condenseur et eau de refroidissement
        K["condenseur"].set_attr(dp1=0.0, dp2=0.0, ttd_u=p.pincement_condenseur_K)
        c["11"].set_attr(fluid=EAU, T=p.T_eau_refroidissement_C, p=p.p_eau_refroidissement_bar)
        c["12"].set_attr(T=p.T_eau_refroidissement_C + p.echauffement_eau_refroidissement_K)

        # Pertes d'échappement (point fixe)
        K["pertes"].set_attr(Q=0.0, dp=0.0)

        self._valeurs_initiales()
        self._declarer_offdesign()

    def _valeurs_initiales(self) -> None:
        """Valeurs de départ du solveur de Newton (ordres de grandeur)."""
        c = self.c
        h = {"e1": 2620, "e2": 2540, "e3": 2460, "e4": 2830, "e5": 2660,
             "e6": 2480, "2": 2280, "v_sech": 2778, "bp_in": 2970,
             "a0": 763, "a1": 770, "a2": 880, "4": 990, "c1": 125, "c2": 300,
             "c3": 450, "c4": 600, "d_surch": 1290, "h_RHP2": 2300, "h_RHP1": 2200,
             "h_RBP2": 2400, "h_RBP1": 2300, "h_cond": 2250}
        m = {"1": 2400, "1b": 150, "x_RHP2": 150, "x_RHP1": 130, "x_bache": 100,
             "x_RBP3": 90, "x_RBP2": 90, "x_RBP1": 80, "purge_sech": 230, "3": 1500}
        for k, v in h.items():
            c[k].set_attr(h0=v)
        for k, v in m.items():
            c[k].set_attr(m0=v)

    def _declarer_offdesign(self) -> None:
        K, c = self.K, self.c
        # GV : la pression vapeur devient un résultat (UA du GV, débit primaire fixé)
        c["1"].set_attr(design=["p"])
        c["P2"].set_attr(design=["T"])
        c["P1"].set_attr(offdesign=["m"])
        K["gv"].set_attr(offdesign=["UA_char"])
        # Soupapes de réglage HP : perte de charge imposée au design, libre en
        # offdesign (leur ouverture s'adapte : la pression GV vient du UA du
        # GV, la pression d'admission HP vient de la loi du cône).
        K["soupapes_HP"].set_attr(design=["dp"])
        # Turbines : pressions de soutirage -> loi du cône de Stodola
        for lbl in ("e1", "e2", "e3", "e4", "e5", "e6"):
            c[lbl].set_attr(design=["p"])
        for n in ("HP1", "HP2", "HP3", "BP1", "BP2", "BP3", "BP4"):
            K[n].set_attr(design=["eta_s"], offdesign=["eta_s_char", "cone"])
        # Échangeurs : écart de température -> UA
        for n in ("surchauffeur", "RHP2", "RHP1", "RBP3", "RBP2", "RBP1"):
            K[n].set_attr(design=["ttd_u"], offdesign=["UA_char"])
        # Condenseur : UA corrigé selon la température d'eau (point fixe)
        if self.params.correction_UA_temperature:
            K["condenseur"].set_attr(design=["ttd_u"], offdesign=[])
        else:
            K["condenseur"].set_attr(design=["ttd_u"], offdesign=["UA_char"])
        c["12"].set_attr(design=["T"])
        c["11"].set_attr(offdesign=["m"])
        for n in ("CEX", "APP"):
            K[n].set_attr(design=["eta_s"], offdesign=["eta_s_char"])

    # ------------------------------------------------------------------ #
    def _solve(self, mode, design_path=None) -> None:
        self.nw.solve(mode, design_path=design_path, max_iter=100)
        self.nw.assert_convergence()

    def _etat_echappement(self):
        c = self.c
        ligne = LigneDetente(c["e6a"].p.val_SI, c["e6a"].h.val_SI, self.K["BP4"].eta_s.val)
        p_cond, m = c["2"].p.val_SI, c["2"].m.val_SI
        if self.section_annulaire_m2 is None:
            self.section_annulaire_m2 = section_annulaire(
                m, ligne, p_cond, self.params.vitesse_annulaire_design_m_s)
        return etat_echappement(m, ligne, p_cond, self.section_annulaire_m2,
                                self.params.vitesse_annulaire_blocage_m_s,
                                self.params.facteur_pertes_echappement)

    def _appliquer_baumann(self) -> bool:
        """Au design : rendement de chaque tronçon = eta_sec x (1 - a y_moy).
        En offdesign, les caractéristiques TESPy partent de ces valeurs."""
        p, change = self.params, False
        for n, (ci, co) in TRONCONS.items():
            eta_sec = p.rendement_isentropique_HP if n.startswith("HP") else p.rendement_isentropique_BP
            y_moy = 0.5 * (humidite(self.c[ci].p.val_SI, self.c[ci].h.val_SI)
                           + humidite(self.c[co].p.val_SI, self.c[co].h.val_SI))
            eta = eta_sec * (1.0 - p.coefficient_baumann * y_moy)
            if abs(eta - self.K[n].eta_s.val) > 1e-7:
                self.K[n].set_attr(eta_s=eta)
                change = True
        return change

    def _T_moy_eau(self) -> float:
        return 0.5 * (self.c["11"].T.val + self.c["12"].T.val)

    def _UA_cible(self, T_moy_C: float) -> float:
        d = self.complements
        return d["UA_design_W_K"] * facteur_UA(
            T_moy_C, d["T_moy_eau_design_C"], self.params.part_resistance_cote_eau)

    def _point_fixe(self, mode, design_path=None) -> None:
        p, K = self.params, self.K
        corriger_UA = mode == "offdesign" and p.correction_UA_temperature
        self._solve(mode, design_path)
        etat = None
        for _ in range(ITER_MAX):
            change = False
            if p.pertes_echappement:
                if mode == "design":
                    self.section_annulaire_m2 = None
                etat = self._etat_echappement()
                if abs(etat.perte_MW - K["pertes"].Q.val) > TOL_MW:
                    K["pertes"].set_attr(Q=etat.perte_MW)
                    change = True
            if mode == "design":
                change |= self._appliquer_baumann()
            if corriger_UA:
                UA = self._UA_cible(self._T_moy_eau())
                if abs(UA / K["condenseur"].UA.val_SI - 1.0) > 1e-7:
                    K["condenseur"].set_attr(UA=UA)
                    change = True
            if not change:
                break
            self._solve(mode, design_path)
        else:
            raise RuntimeError("Point fixe (échappement / UA) non convergé")
        self.etat_ech = etat

    def resoudre(self) -> ResultatsN4:
        self.K["condenseur"].set_attr(UA=None)
        self._point_fixe("design")
        self.complements = {
            "section_annulaire_m2": self.section_annulaire_m2,
            "UA_design_W_K": self.K["condenseur"].UA.val_SI,
            "T_moy_eau_design_C": self._T_moy_eau(),
        }
        return self.resultats()

    def sauvegarder_design(self, chemin) -> None:
        chemin = Path(chemin)
        self.nw.save(str(chemin))
        self._design_path = str(chemin)
        chemin.with_suffix(".complements.json").write_text(json.dumps(self.complements, indent=2))

    def resoudre_offdesign(self, T_eau_refroidissement_C: float, design_path=None) -> ResultatsN4:
        design_path = design_path or self._design_path
        self.params.T_eau_refroidissement_C = T_eau_refroidissement_C
        self.c["11"].set_attr(T=T_eau_refroidissement_C)
        self.complements = json.loads(Path(design_path).with_suffix(".complements.json").read_text())
        self.section_annulaire_m2 = self.complements["section_annulaire_m2"]
        if self.params.correction_UA_temperature:
            T_moy = T_eau_refroidissement_C + 0.5 * self.params.echauffement_eau_refroidissement_K
            self.K["condenseur"].set_attr(UA=self._UA_cible(T_moy))
        self._point_fixe("offdesign", design_path)
        return self.resultats()

    # ------------------------------------------------------------------ #
    def resultats(self) -> ResultatsN4:
        p, K, c = self.params, self.K, self.c
        Q_gv = -K["gv"].Q.val
        Q_ech = K["pertes"].Q.val
        W_HP = -sum(K[n].P.val for n in ("HP1", "HP2", "HP3"))
        W_BP = -sum(K[n].P.val for n in ("BP1", "BP2", "BP3", "BP4")) - Q_ech
        W_t = W_HP + W_BP
        W_cex, W_app = K["CEX"].P.val, K["APP"].P.val
        W_p = W_cex + W_app
        Q_cond = -K["condenseur"].Q.val
        P_brute = W_t * p.rendement_meca_alternateur
        P_nette = P_brute - W_p / p.rendement_moteur_pompe
        T_chaud = c["1"].T.val + 273.15
        T_froid = c["11"].T.val + 273.15
        ech = self.etat_ech
        x_e3 = c["e3a"].x.val
        return ResultatsN4(
            debit_vapeur_kg_s=c["1"].m.val,
            debit_eau_refroidissement_kg_s=c["11"].m.val,
            T_eau_refroidissement_C=c["11"].T.val,
            T_sortie_eau_refroidissement_C=c["12"].T.val,
            p_admission_bar=c["1"].p.val,
            rendement_isentropique_turbine=K["BP4"].eta_s.val,
            p_condenseur_mbar=c["2"].p.val * 1000.0,
            T_condenseur_C=c["3"].T.val,
            titre_sortie_turbine=c["2u"].x.val,
            vitesse_annulaire_m_s=ech.vitesse_annulaire_m_s if ech else math.nan,
            echappement_bloque=bool(ech and ech.bloque),
            p_blocage_mbar=ech.p_blocage_bar * 1000 if ech else math.nan,
            perte_echappement_MW=Q_ech,
            puissance_thermique_MW=Q_gv,
            puissance_turbine_MW=W_t,
            puissance_pompe_MW=W_p,
            puissance_condenseur_MW=Q_cond,
            puissance_electrique_brute_MW=P_brute,
            puissance_electrique_nette_MW=P_nette,
            rendement_cycle=(W_t - W_p) / Q_gv,
            rendement_net=P_nette / Q_gv,
            rendement_carnot=1.0 - T_froid / T_chaud,
            T_eau_alimentaire_C=c["0"].T.val,
            p_vapeur_bar=c["1"].p.val,
            puissance_HP_MW=W_HP,
            puissance_BP_MW=W_BP,
            puissance_pompe_extraction_MW=W_cex,
            puissance_pompe_alimentaire_MW=W_app,
            humidite_entree_BP_pourcent=100 * (1 - x_e3) if 0 <= x_e3 <= 1 else 0.0,
            T_surchauffe_C=c["bp_in"].T.val,
            debit_condenseur_kg_s=c["3"].m.val,
            debit_primaire_kg_s=c["P1"].m.val,
        )

    def tableau_etats(self):
        df = self.nw.results["Connection"]
        return df[["m", "p", "T", "h", "s", "x"]]
