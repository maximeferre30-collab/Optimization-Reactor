# Préparer la présentation du projet

Ce document sert à pouvoir défendre chaque résultat face à un recruteur ou un jury
technique. Pour chaque question : la réponse courte, puis où la retrouver dans le
code ou le rapport. Le bon test est de savoir répondre **sans regarder**.

## 1. Le projet en 30 secondes

« J'ai modélisé le circuit eau-vapeur d'une tranche N4 avec TESPy pour mesurer l'effet
de la température de la source froide sur la puissance. Chaque degré au-dessus de 15 °C
coûte environ 6,7 MWe, soit 0,43 %. Il existe un optimum vers 9 °C, à cause des pertes
d'échappement de la turbine BP. J'ai validé le modèle contre les données publiques
(+1,9 % sur la puissance brute, sans calage). J'ai aussi redémontré la sensibilité à
la main par Clapeyron, à 2 % près. Enfin, je l'ai appliqué à dix ans de météo réelle
avec un modèle de tour aéroréfrigérante. »

## 2. Thermodynamique : les questions probables

**Pourquoi la puissance baisse-t-elle quand l'eau est plus chaude ?**
La vapeur condense plus chaud, donc la pression au condenseur augmente et la détente
dans la turbine est plus courte. Ordre de grandeur : dW/dT_c ≈ −η·Q_lat/T_c ≈
−0,81 × 2 595 MW / 302 K ≈ −7 MW/K. → `analyse_thermo.py`, onglet Thermodynamique §1.

**D'où vient cette formule ?**
De la relation de Gibbs à entropie constante, dh = v dp, et de Clapeyron,
dp/dT = h_fg / (T(v_g − v_f)). Avec v_sortie ≈ x·v_g, le produit ṁ·x·h_fg est la
chaleur latente cédée au condenseur.

**Pourquoi le modèle donne-t-il moins que Clapeyron près du design (−4,9 contre −6,9) ?**
Pour deux raisons :
1. Le crédit de régénération (+0,7 MW/K) : un condensat plus chaud demande moins de
   soutirage au réchauffeur RBP1, et cette vapeur se détend jusqu'au bout.
2. La baisse des pertes d'échappement (+1,1 MW/K) : quand l'eau se réchauffe, la
   pression d'échappement monte, la vapeur sort moins vite et l'énergie cinétique
   perdue diminue.

**Pourquoi y a-t-il un optimum ?**
Le vide croît quand l'eau refroidit. Le volume massique de la vapeur d'échappement
augmente, et donc sa vitesse dans la section de sortie : la perte d'énergie cinétique
croît en V². Au-delà d'environ 400 m/s, l'écoulement est bloqué et plus aucun gain
n'est possible.

**Pourquoi les soutirages améliorent-ils le rendement ?**
Ils élèvent la température moyenne d'apport de chaleur, T̄ = Δh/Δs : 283 °C contre
218 °C pour le cycle simple. Le rendement endoréversible passe de 38,5 % à 45,7 %.
La fraction de ce rendement atteinte reste la même (≈ 82 %) : le gain vient de T̄,
pas de machines plus efficaces.

**À quoi sert le sécheur-surchauffeur ?**
À réduire l'humidité dans la turbine BP (de 26 % à 14 % en sortie), donc l'érosion
des aubages et les pertes de Baumann. Il gagne aussi un peu de travail.

**Qu'est-ce que la règle de Baumann ?**
Chaque % d'humidité moyenne dans un étage coûte environ 1 % de rendement isentropique :
les gouttes freinent le rotor et frappent les aubes. → `cycle_n4.py`, `_appliquer_baumann`.

**Pourquoi la turbine BP détruit-elle plus d'exergie que le GV ?**
À cause de l'humidité et du grand débit volumique en fin de détente. Le GV transfère la
chaleur avec un écart de température modéré (pincement de 7,6 K). Le condenseur, lui,
détruit peu d'exergie : sa chaleur est rejetée à 29 °C, presque à la température ambiante.

**Que vaut dp/dT à saturation vers 30 °C ?**
Environ 230 Pa/K, soit 2,3 mbar de plus par degré.

## 3. Modélisation et numérique

**Différence entre design et offdesign ?**
Le design dimensionne : on impose des performances (pincement, rendements) et on obtient
les surfaces UA. L'offdesign fige l'installation : UA et sections sont fixés, et les
performances deviennent des résultats.

**Pourquoi le solveur signalait-il une équation de trop ?**
La pression vapeur était fixée deux fois : par le UA du GV et par la loi du cône de la
turbine HP. Sur une vraie tranche, ce sont les soupapes de réglage HP qui absorbent cet
écart. Leur perte de charge doit donc rester libre en offdesign.

**Comment as-tu validé le modèle ?**
- Calcul indépendant du cycle simple (CoolProp seul), écart inférieur à 10⁻⁵.
- Bilans d'énergie, de matière et d'exergie fermés.
- Aucune création d'entropie négative, composant par composant.
- Comparaison aux données publiques du N4.
- Démonstration à la main par Clapeyron.

En tout, 30 tests automatiques.

**Le modèle est-il calé ?**
Non, et c'est volontaire. Le premier résultat dépassait la valeur publiée de 5,5 %.
J'ai ajouté la physique manquante (Baumann, pertes de charge) au lieu d'ajuster les
rendements.

**Quelles sont les limites ?**
- La courbe de pertes d'échappement est générique (les courbes de la turbine Arabelle
  ne sont pas publiques).
- La tour ignore le vent et la recirculation de panache.
- Les limites de rejet sont illustratives.
- Le rendement est supposé constant à charge partielle.

**Quelle confiance accorder à l'optimum à 9 °C ?**
Faible. Le Monte-Carlo le place entre 4 et 12 °C, et la tornade montre qu'il dépend
surtout de la vitesse d'échappement retenue au design. La pente au-dessus de 15 °C est
en revanche robuste : entre −7,2 et −6,2 MWe/°C.

## 4. Tour et météo

**Pourquoi la température humide et pas la température sèche ?**
Une tour refroidit surtout par évaporation. La limite théorique de l'eau froide est donc
la température humide de l'air, pas sa température sèche.

**Pourquoi le débit d'air chute-t-il par temps chaud et sec ?**
Le tirage naturel vient de la différence de densité entre l'air chaud et humide de la
cheminée et l'air ambiant. Quand l'air ambiant est chaud et sec, cette différence se
réduit.

## 5. Sur l'usage de l'IA

Réponse honnête et simple : « J'ai utilisé un assistant d'IA comme aide à la programmation.
J'ai piloté les choix de modélisation, j'ai vérifié chaque résultat par une méthode
indépendante, et je peux refaire chaque raisonnement au tableau. »

Ce n'est crédible que si c'est vrai. Avant un entretien :
1. Refaire à la main la démonstration de Clapeyron, sans regarder.
2. Savoir expliquer chaque étape de l'onglet Démarche avec tes propres mots, et la
   réécrire si besoin.
3. Savoir modifier un paramètre (par exemple la pression d'un soutirage) et prédire le
   sens de l'effet avant de lancer le calcul.
