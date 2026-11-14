# Circuit secondaire d'un REP N4 avec TESPy

Le but du projet est de modéliser le circuit secondaire (eau-vapeur) d'un réacteur
à eau pressurisée du palier N4 (Chooz B, Civaux : 4 270 MWth) et d'étudier
l'effet de la **température de l'eau de refroidissement** sur la puissance électrique.

- **Étape 1** : cycle de Rankine simple, sans soutirages ni sécheur-surchauffeur (MSR).
- **Étape 2** : étude offdesign de la sensibilité à la température de l'eau froide.
- **Étape 3 (actuelle)** : pertes d'échappement de la turbine BP (méthode Spencer-Cotton-Cannon).

## Installation

```bash
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e ".[dev]"
```

`requirements.txt` fige les versions exactes testées (TESPy 0.12.0, CoolProp 8.0).
`pyproject.toml` déclare le paquet `rep_secondaire` et ses dépendances minimales.

## Utilisation

```bash
python scripts/run_rankine_simple.py      # point de dimensionnement
python scripts/etude_source_froide.py     # balayage 0-35 °C -> results/
pytest
```

## Arborescence

```
src/rep_secondaire/
    parametres.py       # tous les paramètres de conception (dataclass)
    rankine_simple.py   # construction et résolution du réseau TESPy (design + offdesign)
    echappement.py      # pertes d'échappement BP (courbe SCC, blocage)
    etude_source_froide.py  # balayage en température de l'eau de refroidissement
scripts/
    run_rankine_simple.py  # affiche états, bilan et rendements
    etude_source_froide.py # CSV + figure de l'étude de sensibilité
tests/                  # contrôles : bilan d'énergie, ordres de grandeur, tendance
results/                # sorties (CSV, figures), non versionnées
```

## Le modèle

```
 (0) ──► [GV] ──(1)──► [Turbine] ──(2)──► [Pertes échappement] ──(2u)──► [Condenseur] ──(3)──► [Pompe] ──(4)──► [Fermeture] ──► (0)
                                                                          ▲   │
                                                    eau froide (11) ──────┘   └──── (12) rejet
```

| Composant | Classe TESPy | Ce qu'on impose |
|---|---|---|
| Générateur de vapeur (4 GV agrégés) | `SimpleHeatExchanger` | Q = 4 270 MW, Δp = 8 bar ; sortie : 72 bar, x = 1 |
| Turbine (HP + BP en un seul corps) | `Turbine` | η_is = 0,85 (ligne de détente) |
| Pertes d'échappement BP | `SimpleHeatExchanger` | Q = perte SCC, calculée par point fixe |
| Condenseur | `Condenser` | pincement T_sat − T_sortie eau = 4 K, Δp = 0 |
| Eau de refroidissement | `Source` / `Sink` | entrée 15 °C, sortie 25 °C |
| Pompe alimentaire | `Pump` | η_is = 0,80 |
| Fermeture de cycle | `CycleCloser` | (outil numérique, voir plus bas) |

Le solveur calcule le reste : le débit de vapeur (pour absorber 4 270 MW), la
pression au condenseur (via le pincement), le titre en sortie turbine, le débit
d'eau de refroidissement, et toutes les puissances.

### Hypothèses

- **Puissance au secondaire égale à la puissance du réacteur.** On néglige les
  ~20 MW apportés par les pompes primaires et les pertes thermiques.
- **Vapeur saturée sèche à 72 bar.** En réalité le titre en sortie GV est d'environ
  0,9975. Les pertes de charge de la ligne vapeur ne sont pas modélisées.
- **Δp de 8 bar côté alimentation.** Ce chiffre regroupe les pertes de la ligne
  d'eau alimentaire et du GV. La pompe refoule donc à 80 bar.
- **Une seule détente, η_is = 0,85.** Sans MSR, la vapeur sort de la turbine à
  x ≈ 0,73, soit environ 27 % d'humidité. Une vraie turbine ne le supporterait pas
  (érosion des aubages, et environ −1 % de rendement par % d'humidité selon la
  règle de Baumann). Le MSR sert justement à corriger ça.
- **Condenseur dimensionné par son pincement.** Avec 15 °C + 10 K + 4 K, on obtient
  T_sat = 29 °C, soit p ≈ 40 mbar, ce qui correspond à l'ordre de grandeur N4.
  Le sous-refroidissement est nul (liquide saturé en sortie).
- **Rendement mécanique × alternateur = 0,985, moteur de pompe = 0,95.** On suppose
  la pompe entraînée électriquement. Sur N4, ce sont des turbopompes. Les
  auxiliaires ne sont pas comptés.
- **Calcul en mode *design*.** On fixe ΔT et le pincement, et le débit d'eau de
  refroidissement en découle. L'étude de sensibilité, elle, se fait en
  *offdesign* (voir plus bas).

### Rôle du `CycleCloser`

TESPy résout un système d'équations. Dans une boucle fermée, la conservation de
la masse et de l'énergie rend une équation redondante. Le `CycleCloser` coupe
numériquement la boucle pour supprimer cette redondance. Il n'a aucun sens
physique.

## Pertes d'échappement BP

Toute l'énergie disponible en fin de détente n'est pas convertie en travail
au dernier étage BP. On utilise la méthode de Spencer-Cotton-Cannon (SCC),
employée par les constructeurs pour les bilans de turbines à vapeur :

- **ELEP** (*expansion line end point*, point (2)) : sortie de la ligne de détente, calculée par TESPy avec η_is.
- **UEEP** (*used energy end point*, point (2u)) : état réellement envoyé au condenseur.
- h_UEEP = h_ELEP + EL(V) · 0,87 · (1 − 0,01 Y) · (1 − 0,0065 Y), avec Y l'humidité en %.
- V est la vitesse axiale dans la section annulaire de sortie : V = ṁ · v / A.

La courbe EL(V) a trois zones :

- **Faible vitesse** (eau chaude, pression élevée) : des pertes de décollement et de recirculation apparaissent dans le dernier étage (*turn-up*).
- **Vitesse moyenne** : la perte passe par un minimum, vers 150-200 m/s.
- **Grande vitesse** (eau froide, vide poussé) : la perte d'énergie cinétique croît en V². À partir de **400 m/s, l'écoulement est bloqué**. Abaisser la pression au condenseur sous la pression de blocage p* ne produit alors plus de travail. Le travail de détente entre p* et p_cond est compté comme perdu.

Choix de modélisation :

- **Section annulaire.** On la fixe pour obtenir 250 m/s au point de design, puis on la garde constante en offdesign. On n'a pas repris la section réelle d'Arabelle : sans soutirages, notre cycle envoie au condenseur beaucoup plus de vapeur que la vraie machine.
- **Courbe EL(V) générique.** Elle reproduit la forme des courbes SCC, mais elle n'est pas calée sur la turbine du N4, dont les courbes ne sont pas publiques.
- **Couplage avec TESPy.** La perte est retirée de la puissance de la turbine et rendue au fluide par un bloc `SimpleHeatExchanger`. Elle augmente donc la chaleur à évacuer au condenseur, ce qui modifie la pression au condenseur, qui modifie à son tour la perte. On résout cette boucle par **point fixe**. Le bilan d'énergie reste exactement fermé.
- `ParametresRankine(pertes_echappement=False)` retrouve le modèle des étapes 1 et 2.

## Résultats au point de design (15 °C)

| Grandeur | Avec pertes d'échappement | Sans (étape 1) |
|---|---|---|
| Débit vapeur | 1 618 kg/s | 1 618 kg/s |
| Pression / température condenseur | 40,1 mbar / 29,0 °C | 40,1 mbar / 29,0 °C |
| Titre sortie turbine | 0,738 | 0,731 |
| Vitesse annulaire (section 164 m²) | 250 m/s | — |
| Perte d'échappement | 26 MW | — |
| Puissance turbine | 1 382 MW | 1 408 MW |
| Puissance pompe | 16 MW | 16 MW |
| Chaleur rejetée | 2 904 MW | 2 878 MW |
| Puissance électrique nette | 1 345 MWe | 1 370 MWe |
| **Rendement du cycle** | **32,0 %** | 32,6 % |
| Rendement net électrique | 31,5 % | 32,1 % |
| Rendement de Carnot (288 °C / 15 °C) | 48,6 % | 48,6 % |

Le N4 réel atteint environ 34-35 % brut. On s'attend à combler l'écart avec les
soutirages (eau alimentaire réchauffée à ~230 °C) et le MSR.

## Étude offdesign : effet de la température de l'eau de refroidissement

On fait d'abord le dimensionnement à 15 °C, puis on fige l'installation. On fait
ensuite varier la seule température d'entrée de l'eau, de 0 à 35 °C.

| Grandeur | Design (15 °C) | Offdesign |
|---|---|---|
| Condenseur | pincement 4 K | UA fixé (corrigé selon les débits par `UA_char`) |
| Eau de refroidissement | ΔT = 10 K | débit fixé (pompes de circulation à débit constant) |
| Turbine | η_is = 0,85 | η_is selon le débit (`eta_s_char`) |
| Pompe | η_is = 0,80 | η_is selon le débit (`eta_s_char`) |
| Puissance réacteur, p vapeur | 4 270 MW, 72 bar | inchangées |

Pourquoi la pression vapeur reste fixée : à puissance nominale, la régulation du
primaire maintient la température moyenne de l'eau. La température de
saturation au GV, donc sa pression, ne bouge presque pas. Pour cette raison, la
loi du cône de Stodola n'est pas activée.

Pour faire converger le solveur de Newton, on se déplace par pas d'au plus 1 K
à partir du point de dimensionnement. Chaque calcul part de la solution
précédente.

### Résultats

| T eau (°C) | p cond (mbar) | V annulaire (m/s) | Perte éch. (MW) | P nette (MWe) | P nette sans pertes (MWe) |
|---|---|---|---|---|---|
| 0 | 16,1 | 400 (bloqué) | 120 | 1 328 | 1 449 |
| 5 | 22,0 | 400 (bloqué) | 85 | 1 338 | 1 423 |
| 10 | 29,8 | 326 | 45 | 1 351 | 1 396 |
| **15** | **40,1** | **250** | **26** | **1 345** | **1 370** |
| 20 | 53,5 | 193 | 20 | 1 324 | 1 344 |
| 25 | 70,8 | 150 | 20 | 1 298 | 1 317 |
| 30 | 92,9 | 118 | 26 | 1 266 | 1 291 |
| 35 | 120,7 | 94 | 35 | 1 230 | 1 265 |

Résultats principaux :

- **La puissance passe par un optimum : 1 351 MWe vers 11 °C.** Sans les pertes d'échappement, la puissance augmentait indéfiniment quand l'eau refroidissait.
- **Au-dessus de 15 °C, la sensibilité vaut −5,8 MWe/°C, soit −0,43 %/°C.** C'est un peu plus que sans les pertes (−5,3 MWe/°C), à cause du *turn-up* aux faibles vitesses.
- **En dessous de 7 °C, l'échappement est bloqué** (p* ≈ 23,5 mbar).

![Étude source froide](results/etude_source_froide.png)

Lecture physique :

- **Eau chaude.** La vapeur condense plus chaud, donc la pression au condenseur augmente et la détente est plus courte : on récupère moins de travail. La pression de saturation croît à peu près exponentiellement avec la température, mais la perte de puissance reste presque linéaire, car le travail récupéré dépend de la température de condensation et non de la pression.
- **Eau froide, jusqu'au blocage.** La vapeur gagne en volume spécifique, donc la vitesse de sortie augmente et l'énergie cinétique perdue grandit. Le gain de détente est en partie mangé.
- **Eau froide, au-delà du blocage.** La turbine ne profite plus du vide supplémentaire. La puissance baisse même un peu : le condensat plus froid doit être davantage réchauffé dans le GV, donc pour une même puissance thermique le débit de vapeur diminue. Avec des soutirages, cet effet serait en grande partie compensé.
- **Conséquence pratique.** Pour un condenseur et une turbine donnés, il existe une température d'eau, et donc un vide, optimale. Pousser le vide au-delà ne sert à rien. C'est pour cette raison que la section d'échappement BP, c'est-à-dire la longueur de la dernière ailette, se choisit en fonction du climat du site.

### Limites

- **Courbe d'échappement générique.** La position de l'optimum (11 °C) dépend
  directement de la vitesse annulaire choisie au design (250 m/s) et de la
  vitesse de blocage (400 m/s). Les deux sont des paramètres à faire varier.
- **Rejet thermique non contraint.** À 35 °C, l'eau ressort à 45 °C. Les
  arrêtés de rejet imposent des limites (température aval, échauffement), et
  ce sont elles qui provoquent les baisses de production en été, plus que le
  rendement lui-même.
- **Caractéristiques par défaut de TESPy.** Les lois `UA_char` et `eta_s_char`
  ne sont pas calées sur des données constructeur.
- Le cycle reste simple : sans MSR ni soutirages, la sensibilité réelle sera
  différente.

## Étapes suivantes

1. Sécheur-surchauffeur entre les corps HP et BP.
2. Soutirages et réchauffeurs BP/HP, bâche alimentaire.
3. Contraintes réglementaires de rejet thermique (température aval, échauffement).
