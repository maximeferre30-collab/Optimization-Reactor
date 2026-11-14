"""Construit le rapport HTML interactif à partir des résultats du modèle.

Usage :
    python scripts/figures_rapport.py   # calcule et écrit results/rapport_donnees.json
    python scripts/rapport_html.py      # écrit results/rapport.html

Ouvrir ensuite results/rapport.html dans un navigateur (double-clic).
"""

from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
MODELE = RACINE / "rapport" / "modele_rapport.html"
DONNEES = RACINE / "results" / "rapport_donnees.json"
SORTIE = RACINE / "results" / "rapport.html"

ENTETE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
"""


def main() -> None:
    gabarit = MODELE.read_text(encoding="utf-8")
    donnees = DONNEES.read_text(encoding="utf-8")
    marque = "/*__DONNEES__*/null"
    assert marque in gabarit, "marqueur de données absent du gabarit"
    corps = gabarit.replace(marque, donnees)
    # Le gabarit est un fragment (format des pages publiées) : on l'enveloppe
    # d'un squelette HTML complet pour l'ouvrir directement dans un navigateur.
    debut_corps = '<header class="hero">'
    assert debut_corps in corps, "début du corps de page introuvable dans le gabarit"
    SORTIE.write_text(ENTETE + corps.replace(debut_corps, "</head>\n<body>\n" + debut_corps, 1)
                      + "\n</body>\n</html>\n", encoding="utf-8")
    fragment = RACINE / "results" / "rapport_fragment.html"
    fragment.write_text(corps, encoding="utf-8")
    print(f"Rapport : {SORTIE}")


if __name__ == "__main__":
    main()
