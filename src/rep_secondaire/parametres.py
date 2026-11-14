"""Paramètres de conception du circuit secondaire (palier N4, ordres de grandeur).

Toutes les valeurs sont regroupées ici pour pouvoir les faire varier facilement
(étude paramétrique sur la température de la source froide, etc.).

Sources des ordres de grandeur : caractéristiques publiques du palier N4
(Chooz B, Civaux) — 4 270 MWth, ~1 500 MWe brut, vapeur saturée ~72 bar en
sortie de générateur de vapeur (GV), condenseur à quelques dizaines de mbar.
"""

from dataclasses import dataclass, asdict


@dataclass
class ParametresRankine:
    # --- Générateurs de vapeur (côté secondaire, 4 GV agrégés en un seul) ---
    puissance_thermique_MW: float = 4270.0
    """Puissance transmise au secondaire. Hypothèse : égale à la puissance
    thermique nominale du réacteur (on néglige l'apport des pompes primaires
    et les pertes thermiques)."""

    p_vapeur_bar: float = 72.0
    """Pression de la vapeur en sortie GV / admission turbine."""

    titre_vapeur: float = 1.0
    """Titre en sortie GV. Réel : ~0,9975 (0,25 % d'humidité résiduelle après
    les sécheurs internes du GV). On prend de la vapeur saturée sèche."""

    dp_alimentation_bar: float = 8.0
    """Pertes de charge agrégées ligne d'alimentation + GV côté eau
    (refoulement pompe = p_vapeur + dp)."""

    # --- Turbine (HP + BP en un seul corps, sans soutirage ni MSR) ---
    rendement_isentropique_turbine: float = 0.85
    """Rendement isentropique moyen de détente. Pour une détente très humide
    on serait plutôt vers 0,80-0,85 (règle de Baumann : ~1 % de perte par %
    d'humidité)."""

    rendement_meca_alternateur: float = 0.985
    """Rendement combiné mécanique (paliers) x alternateur."""

    # --- Condenseur et source froide ---
    T_eau_refroidissement_C: float = 15.0
    """Température d'entrée de l'eau de refroidissement (paramètre d'étude)."""

    echauffement_eau_refroidissement_K: float = 10.0
    """Échauffement de l'eau de refroidissement dans le condenseur."""

    pincement_condenseur_K: float = 4.0
    """Écart T_sat(condenseur) - T_sortie eau de refroidissement
    (« terminal temperature difference » côté chaud, ttd_u dans TESPy)."""

    p_eau_refroidissement_bar: float = 2.0
    """Pression de l'eau de refroidissement (sans influence sur le cycle)."""

    # --- Pompe d'alimentation ---
    rendement_isentropique_pompe: float = 0.80
    rendement_moteur_pompe: float = 0.95
    """La pompe est supposée entraînée électriquement (sur N4 les pompes
    alimentaires sont des turbopompes ; ce détail est ignoré ici)."""

    def as_dict(self) -> dict:
        return asdict(self)
