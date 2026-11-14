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

from .condenseur import facteur_UA
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
        # Condenseur : pincement imposé au design. En offdesign :
        # - avec correction en température : UA imposé explicitement
        #   (UA_design x facteur(T_eau), mis à jour par point fixe) ;
        # - sinon : UA_char de TESPy (UA corrigé selon les seuls débits).
        if self.params.correction_UA_temperature:
            self.condenseur.set_attr(design=["ttd_u"], offdesign=[])
        else:
            self.condenseur.set_attr(design=["ttd_u"], offdesign=["UA_char"])
        # Eau de refroidissement : échauffement imposé -> débit imposé
        # (pompes de circulation à débit constant)
        c["12"].set_attr(design=["T"])
        c["11"].set_attr(offdesign=["m"])
        # Turbine : rendement fixe -> rendement fonction du débit.
        # La pression vapeur reste imposée (72 bar) : sur un REP à puissance
        # nominale, la régulation maintient la température moyenne primaire,
        # donc T_sat (et p) au secondaire du GV. La loi du cône n'est pas
        # activée : les soupapes d'admission absorbent l'écart.
        self.turbine.set_attr(design=["eta_s"], offdesign=["eta_s_char"])
        # Pompe : rendement fonction du débit volumique
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
                                self.params.vitesse_annulaire_blocage_m_s,
                                self.params.facteur_pertes_echappement)

    def _T_moy_eau(self) -> float:
        return 0.5 * (self.c["11"].T.val + self.c["12"].T.val)

    def _UA_cible(self, T_moy_C: float) -> float:
        d = self.complements
        return d["UA_design_W_K"] * facteur_UA(
            T_moy_C, d["T_moy_eau_design_C"], self.params.part_resistance_cote_eau)

    def _point_fixe(self, mode, design_path=None) -> None:
        """Résout le réseau, puis met à jour par point fixe les grandeurs
        calculées hors de TESPy :
        - la perte d'échappement, qui dépend de la pression au condenseur,
          elle-même fonction de la chaleur à évacuer (donc de la perte) ;
        - en offdesign, le UA du condenseur, qui dépend de la température
          moyenne de l'eau, elle-même résultat du calcul.
        """
        p = self.params
        corriger_UA = mode == "offdesign" and p.correction_UA_temperature
        self._solve(mode, design_path)
        for _ in range(ITERATIONS_POINT_FIXE_MAX):
            a_change = False
            if p.pertes_echappement:
                if mode == "design":
                    self.section_annulaire_m2 = None
                etat = self._etat_echappement()
                if abs(etat.perte_MW - self.pertes.Q.val) > TOLERANCE_POINT_FIXE_MW:
                    self.pertes.set_attr(Q=etat.perte_MW)
                    a_change = True
            if corriger_UA:
                UA = self._UA_cible(self._T_moy_eau())
                if abs(UA / self.condenseur.UA.val_SI - 1.0) > 1e-7:
                    self.condenseur.set_attr(UA=UA)
                    a_change = True
            if not a_change:
                break
            self._solve(mode, design_path)
        else:
            raise RuntimeError("Point fixe (échappement / UA) non convergé")
        self.etat_ech = etat if p.pertes_echappement else None

    def resoudre(self) -> ResultatsRankine:
        """Calcul de dimensionnement (mode design)."""
        self.condenseur.set_attr(UA=None)
        self._point_fixe("design")
        self.complements = {
            "section_annulaire_m2": self.section_annulaire_m2,
            "UA_design_W_K": self.condenseur.UA.val_SI,
            "T_moy_eau_design_C": self._T_moy_eau(),
        }
        return self.resultats()

    def sauvegarder_design(self, chemin) -> None:
        """Sauvegarde le point de dimensionnement (référence de l'offdesign).
        Les grandeurs de design calculées hors de TESPy (section annulaire BP,
        UA et température moyenne d'eau du condenseur) sont écrites dans un
        fichier voisin."""
        chemin = Path(chemin)
        self.nw.save(str(chemin))
        self._design_path = str(chemin)
        chemin.with_suffix(".complements.json").write_text(
            json.dumps(self.complements, indent=2))

    def resoudre_offdesign(
        self, T_eau_refroidissement_C: float, design_path=None
    ) -> ResultatsRankine:
        """Installation dimensionnée fixée, on change la température de l'eau
        de refroidissement. La puissance thermique du réacteur reste imposée."""
        design_path = design_path or self._design_path
        self.params.T_eau_refroidissement_C = T_eau_refroidissement_C
        self.c["11"].set_attr(T=T_eau_refroidissement_C)
        self.complements = json.loads(
            Path(design_path).with_suffix(".complements.json").read_text())
        self.section_annulaire_m2 = self.complements["section_annulaire_m2"]
        if self.params.correction_UA_temperature:
            T_moy_estimee = (T_eau_refroidissement_C
                             + 0.5 * self.params.echauffement_eau_refroidissement_K)
            self.condenseur.set_attr(UA=self._UA_cible(T_moy_estimee))
        self._point_fixe("offdesign", design_path)
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
