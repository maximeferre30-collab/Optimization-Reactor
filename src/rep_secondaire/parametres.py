"""Paramètres de conception du circuit secondaire (palier N4, ordres de grandeur).

Toutes les valeurs sont regroupées ici pour pouvoir les faire varier facilement
(étude paramétrique sur la température de la source froide, etc.).

Sources des ordres de grandeur : caractéristiques publiques du palier N4
(Chooz B, Civaux) — 4 270 MWth, ~1 500 MWe brut, vapeur saturée ~72 bar en
sortie de générateur de vapeur (GV), condenseur à quelques dizaines de mbar.
"""

from dataclasses import asdict, dataclass, field


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

    pertes_echappement: bool = True
    """Prise en compte des pertes d'échappement BP (méthode SCC, voir
    echappement.py). False = turbine « idéale » de l'étape 1."""

    vitesse_annulaire_design_m_s: float = 250.0
    """Vitesse axiale de sortie au point de design. Elle fixe la section
    annulaire de sortie BP, qui reste ensuite constante en offdesign. Les
    constructeurs visent typiquement 200-300 m/s. On ne prend pas la section
    réelle d'Arabelle, car notre cycle sans soutirage envoie beaucoup plus de
    vapeur au condenseur que la vraie machine."""

    vitesse_annulaire_blocage_m_s: float = 400.0

    facteur_pertes_echappement: float = 1.0
    """Multiplie la courbe EL(V) générique (étude d'incertitude)."""
    """Vitesse de blocage (ordre de grandeur des courbes SCC)."""

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

    correction_UA_temperature: bool = True
    """En offdesign, corrige UA du condenseur selon la température de l'eau
    (voir condenseur.py). False = UA constant."""

    part_resistance_cote_eau: float = 0.45
    """Part de la résistance thermique totale située côté eau (tubes) au
    point de design. Hypothèse : ordre de grandeur 0,4-0,5 pour un
    condenseur propre ; c'est le paramètre le plus incertain de la
    correction."""

    p_eau_refroidissement_bar: float = 2.0
    """Pression de l'eau de refroidissement (sans influence sur le cycle)."""

    # --- Pompe d'alimentation ---
    rendement_isentropique_pompe: float = 0.80
    rendement_moteur_pompe: float = 0.95
    """La pompe est supposée entraînée électriquement (sur N4 les pompes
    alimentaires sont des turbopompes ; ce détail est ignoré ici)."""

    def as_dict(self) -> dict:
        return asdict(self)


def _soutirages_defaut() -> dict:
    return {"RHP2": 30.0, "RHP1": 18.0, "bache": 10.0, "RBP3": 4.0, "RBP2": 1.5, "RBP1": 0.4}


@dataclass
class ParametresN4(ParametresRankine):
    """Paramètres du cycle complet (cycle_n4.py). Hérite des paramètres du
    cycle simple (condenseur, échappement, rendements électromécaniques).

    Ordres de grandeur publics du palier N4 utilisés pour le calage :
    4 270 MWth, ~1 560 MWe brut / ~1 500 MWe net, eau alimentaire ~230 °C,
    vapeur saturée ~72 bar, turbine Arabelle (corps HP-MP, sécheurs-
    surchauffeurs, corps BP), températures primaires ~292 / 329 °C.
    """

    # Primaire (côté chaud du GV)
    p_primaire_bar: float = 155.0
    T_primaire_chaud_C: float = 329.0
    T_primaire_froid_C: float = 292.0

    # GV côté secondaire
    dp_gv_bar: float = 5.0
    """Perte de charge eau alimentaire -> vapeur dans le GV (ordre de grandeur)."""

    # Turbines
    rendement_isentropique_HP: float = 0.89
    rendement_isentropique_BP: float = 0.91
    """Rendements isentropiques « vapeur sèche » des tronçons. Le rendement
    effectif de chaque tronçon est réduit par la règle de Baumann."""

    coefficient_baumann: float = 1.0
    """Règle de Baumann : eta = eta_sec * (1 - a * y_moy), y_moy humidité
    moyenne du tronçon (fraction). a ≈ 1 (valeur classique)."""

    dp_admission_HP_bar: float = 3.0
    """Pertes de charge ligne vapeur + soupapes d'arrêt et de réglage HP."""

    dp_surchauffeur_bar: float = 0.4
    """Pertes de charge côté vapeur du sécheur-surchauffeur et du crossover."""

    # Soutirages : pression (bar) au point de prélèvement, par réchauffeur
    p_soutirages_bar: dict = field(default_factory=_soutirages_defaut)
    """RHP2 et RHP1 sur le corps HP ; « bache » = échappement HP (alimente la
    bâche et le sécheur-surchauffeur) ; RBP3, RBP2, RBP1 sur le corps BP.
    Choisies pour une eau alimentaire vers 230 °C et un échauffement réparti."""

    # Échangeurs du poste d'eau
    ttd_rechauffeurs_K: float = 3.0
    """T_sat(soutirage) - T_sortie eau des réchauffeurs fermés."""
    dp_rechauffeurs_HP_bar: float = 1.0
    dp_rechauffeurs_BP_bar: float = 0.5
    ttd_surchauffeur_K: float = 20.0
    """T_sat(vapeur vive) - T_sortie vapeur surchauffée."""
