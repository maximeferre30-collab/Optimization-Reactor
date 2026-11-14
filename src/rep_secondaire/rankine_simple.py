"""Cycle de Rankine simple représentant le circuit secondaire d'un REP N4.

Topologie (eau/vapeur) :

    (4) --> [Fermeture de cycle] --> (0) --> [GV] --> (1) --> [Turbine] --> (2)
     ^                                                                       |
     |                                                          [Pertes d'échappement]
     |                                                                       | (2u)
     |                                                                       v
  [Pompe alimentaire] <-------------- (3) <------------------- [Condenseur côté chaud]

(2) = fin de la ligne de détente (ELEP), (2u) = état réel à l'échappement
(UEEP). Le bloc « pertes d'échappement » rend au fluide l'énergie que la
turbine n'a pas pu convertir (voir echappement.py). Cette énergie est
retirée de la puissance turbine dans resultats().

Circuit de refroidissement (ouvert) :

    [Source eau froide] --> (11) --> [Condenseur côté froid] --> (12) --> [Rejet]

Pas de soutirages, pas de sécheur-surchauffeur (MSR) : ce sont les étapes
suivantes du projet.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from tespy.components import (
    Condenser,
    CycleCloser,
    Pump,
    SimpleHeatExchanger,
    Sink,
    Source,
    Turbine,
)
from tespy.connections import Connection
from tespy.networks import Network

from .echappement import LigneDetente, etat_echappement, section_annulaire
from .parametres import ParametresRankine

FLUIDE = {"water": 1.0}
TOLERANCE_POINT_FIXE_MW = 1e-4
ITERATIONS_POINT_FIXE_MAX = 50


@dataclass
class ResultatsRankine:
    debit_vapeur_kg_s: float
    debit_eau_refroidissement_kg_s: float
    T_eau_refroidissement_C: float
    T_sortie_eau_refroidissement_C: float
    p_admission_bar: float
    rendement_isentropique_turbine: float
    p_condenseur_mbar: float
    T_condenseur_C: float
    titre_sortie_turbine: float
    vitesse_annulaire_m_s: float
    echappement_bloque: bool
    p_blocage_mbar: float
    perte_echappement_MW: float
    puissance_thermique_MW: float
    puissance_turbine_MW: float
    puissance_pompe_MW: float
    puissance_condenseur_MW: float
    puissance_electrique_brute_MW: float
    puissance_electrique_nette_MW: float
    rendement_cycle: float
    rendement_net: float
    rendement_carnot: float


class RankineSimple:
    """Construit, résout et exploite le modèle TESPy."""

    def __init__(self, params: ParametresRankine | None = None):
        self.params = params or ParametresRankine()
        self.nw = Network(iterinfo=False)
        self.nw.units.set_defaults(
            temperature="degC",
            temperature_difference="delta_degC",
            pressure="bar",
            pressure_difference="bar",  # sinon dp reste en Pa
            enthalpy="kJ/kg",
            entropy="kJ/kg/K",
            power="MW",
            heat="MW",
        )
        self._construire()

    # ------------------------------------------------------------------ #
    def _construire(self) -> None:
        # Composants du circuit eau-vapeur
        self.fermeture = CycleCloser("fermeture de cycle")
        self.gv = SimpleHeatExchanger("generateur de vapeur")
        self.turbine = Turbine("turbine")
        self.pertes = SimpleHeatExchanger("pertes echappement")
        self.condenseur = Condenser("condenseur")
        self.pompe = Pump("pompe alimentaire")

        # Circuit de refroidissement
        self.source_froide = Source("prise eau de refroidissement")
        self.rejet = Sink("rejet eau de refroidissement")

        c = {}
        c["0"] = Connection(self.fermeture, "out1", self.gv, "in1", label="0")
        c["1"] = Connection(self.gv, "out1", self.turbine, "in1", label="1")
        c["2"] = Connection(self.turbine, "out1", self.pertes, "in1", label="2")
        c["2u"] = Connection(self.pertes, "out1", self.condenseur, "in1", label="2u")
        c["3"] = Connection(self.condenseur, "out1", self.pompe, "in1", label="3")
        c["4"] = Connection(self.pompe, "out1", self.fermeture, "in1", label="4")
        c["11"] = Connection(self.source_froide, "out1", self.condenseur, "in2", label="11")
        c["12"] = Connection(self.condenseur, "out2", self.rejet, "in1", label="12")
        self.nw.add_conns(*c.values())
        self.c = c

        self.appliquer_parametres()

    def appliquer_parametres(self) -> None:
        """(Ré)applique les paramètres : permet de modifier self.params puis
        de relancer self.resoudre() sans reconstruire le réseau."""
        p = self.params
        c = self.c

        # GV : puissance imposée, pertes de charge côté eau
        self.gv.set_attr(Q=p.puissance_thermique_MW, dp=p.dp_alimentation_bar)
        # Sortie GV : vapeur saturée à la pression d'admission
        c["1"].set_attr(fluid=FLUIDE, p=p.p_vapeur_bar, x=p.titre_vapeur)

        # Turbine : rendement isentropique (la pression de sortie est
        # imposée par le condenseur)
        self.turbine.set_attr(eta_s=p.rendement_isentropique_turbine)
        # Pertes d'échappement : puissance mise à jour par point fixe
        self.pertes.set_attr(Q=0.0, dp=0.0)
        self.section_annulaire_m2 = None

        # Condenseur : pas de perte de charge, pincement imposé.
        # La sortie côté chaud est du liquide saturé (imposé par le composant).
        self.condenseur.set_attr(
            dp1=0.0, dp2=0.0, ttd_u=p.pincement_condenseur_K
        )
        c["11"].set_attr(
            fluid=FLUIDE,
            T=p.T_eau_refroidissement_C,
            p=p.p_eau_refroidissement_bar,
        )
        c["12"].set_attr(
            T=p.T_eau_refroidissement_C + p.echauffement_eau_refroidissement_K
        )

        # Pompe alimentaire
        self.pompe.set_attr(eta_s=p.rendement_isentropique_pompe)

        self._declarer_offdesign()

    def _declarer_offdesign(self) -> None:
        """Indique à TESPy quelles grandeurs sont imposées seulement au
        dimensionnement (design) et quelles lois les remplacent en
        fonctionnement hors dimensionnement (offdesign).

        En offdesign, l'installation existe : on ne choisit plus le pincement
        du condenseur ni le débit d'eau de refroidissement, ils résultent de
        la surface d'échange et des pompes de circulation.
        """
        c = self.c
        # Condenseur : pincement -> coefficient d'échange global UA (corrigé selon les
        # débits par les caractéristiques par défaut de TESPy)
        self.condenseur.set_attr(design=["ttd_u"], offdesign=["UA_char"])
        # Eau de refroidissement : échauffement imposé -> débit imposé
        # (pompes de circulation à débit constant)
        c["12"].set_attr(design=["T"])
        c["11"].set_attr(offdesign=["m"])
        # Turbine : rendement fixe -> rendement fonction du débit volumique.
        # La pression vapeur reste imposée (72 bar) : sur un REP à puissance
        # nominale, la régulation maintient la température moyenne primaire,
        # donc T_sat (et p) au secondaire du GV. La loi du cône n'est pas
        # activée : les soupapes d'admission absorbent l'écart.
        self.turbine.set_attr(design=["eta_s"], offdesign=["eta_s_char"])
        # Pompe : rendement fonction du débit
        self.pompe.set_attr(design=["eta_s"], offdesign=["eta_s_char"])

    # ------------------------------------------------------------------ #
    def _solve(self, mode, design_path=None) -> None:
        self.nw.solve(mode, design_path=design_path)
        self.nw.assert_convergence()

    def _ligne_detente(self) -> LigneDetente:
        c1 = self.c["1"]
        return LigneDetente(c1.p.val_SI, c1.h.val_SI, self.turbine.eta_s.val)

    def _etat_echappement(self):
        ligne = self._ligne_detente()
        p_cond = self.c["2"].p.val_SI
        m = self.c["1"].m.val_SI
        if self.section_annulaire_m2 is None:  # point de design
            self.section_annulaire_m2 = section_annulaire(
                m, ligne, p_cond, self.params.vitesse_annulaire_design_m_s)
        return etat_echappement(m, ligne, p_cond, self.section_annulaire_m2,
                                self.params.vitesse_annulaire_blocage_m_s)

    def _resoudre_avec_pertes(self, mode, design_path=None) -> None:
        """Point fixe : la perte dépend de la pression condenseur, qui dépend
        elle-même de la chaleur à évacuer (donc de la perte)."""
        self._solve(mode, design_path)
        if not self.params.pertes_echappement:
            self.etat_ech = None
            return
        for _ in range(ITERATIONS_POINT_FIXE_MAX):
            if mode == "design":
                self.section_annulaire_m2 = None
            etat = self._etat_echappement()
            ecart = abs(etat.perte_MW - self.pertes.Q.val)
            if ecart < TOLERANCE_POINT_FIXE_MW:
                break
            self.pertes.set_attr(Q=etat.perte_MW)
            self._solve(mode, design_path)
        else:
            raise RuntimeError("Point fixe des pertes d'échappement non convergé")
        self.etat_ech = etat

    def resoudre(self) -> ResultatsRankine:
        """Calcul de dimensionnement (mode design)."""
        self._resoudre_avec_pertes("design")
        return self.resultats()

    def sauvegarder_design(self, chemin) -> None:
        """Sauvegarde le point de dimensionnement (référence de l'offdesign).
        La section annulaire BP, qui n'est pas un paramètre TESPy, est écrite
        dans un fichier voisin."""
        chemin = Path(chemin)
        self.nw.save(str(chemin))
        self._design_path = str(chemin)
        chemin.with_suffix(".echappement.json").write_text(
            json.dumps({"section_annulaire_m2": self.section_annulaire_m2}))

    def resoudre_offdesign(
        self, T_eau_refroidissement_C: float, design_path=None
    ) -> ResultatsRankine:
        """Installation dimensionnée fixée, on change la température de l'eau
        de refroidissement. La puissance thermique du réacteur reste imposée."""
        design_path = design_path or self._design_path
        self.params.T_eau_refroidissement_C = T_eau_refroidissement_C
        self.c["11"].set_attr(T=T_eau_refroidissement_C)
        if self.params.pertes_echappement:
            annexe = Path(design_path).with_suffix(".echappement.json")
            self.section_annulaire_m2 = json.loads(
                annexe.read_text())["section_annulaire_m2"]
        self._resoudre_avec_pertes("offdesign", design_path)
        return self.resultats()

    def resultats(self) -> ResultatsRankine:
        p = self.params
        c = self.c
        Q_gv = self.gv.Q.val
        # TESPy : puissance < 0 quand elle sort. On retire la perte
        # d'échappement, rendue au fluide par le bloc « pertes ».
        Q_ech = self.pertes.Q.val
        W_t = -self.turbine.P.val - Q_ech
        ech = getattr(self, "etat_ech", None)
        W_p = self.pompe.P.val
        Q_cond = -self.condenseur.Q.val

        P_brute = W_t * p.rendement_meca_alternateur
        P_nette = P_brute - W_p / p.rendement_moteur_pompe

        T_chaud = c["1"].T.val + 273.15
        T_froid = c["11"].T.val + 273.15

        return ResultatsRankine(
            debit_vapeur_kg_s=c["1"].m.val,
            debit_eau_refroidissement_kg_s=c["11"].m.val,
            T_eau_refroidissement_C=c["11"].T.val,
            T_sortie_eau_refroidissement_C=c["12"].T.val,
            p_admission_bar=c["1"].p.val,
            rendement_isentropique_turbine=self.turbine.eta_s.val,
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
        )

    def tableau_etats(self):
        """DataFrame des états thermodynamiques aux points du cycle."""
        df = self.nw.results["Connection"]
        return df[["m", "p", "T", "h", "s", "x"]]
