"""Étude d'incertitude (Monte-Carlo + tornade), calcul parallèle.

Usage :
    python scripts/incertitudes.py [nombre_de_tirages]     (64 par défaut)
Écrit results/incertitudes.json. Durée : ~15-25 min sur 8 cœurs.
"""

import json
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

from rep_secondaire.incertitudes import (
    PLAGES,
    TEMPERATURES,
    echantillons_mc,
    echantillons_tornade,
    evaluer,
)

RES = Path(__file__).resolve().parents[1] / "results"


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 64
    dossier = RES / "mc"
    dossier.mkdir(parents=True, exist_ok=True)
    mc = echantillons_mc(n)
    tor = echantillons_tornade()
    taches = [(i, s, str(dossier)) for i, s in enumerate(mc + tor)]
    t0 = time.time()
    resultats = []
    with Pool(processes=max(1, (os.cpu_count() or 2) - 1)) as pool:
        for r in pool.imap_unordered(evaluer, taches):
            resultats.append(r)
            print(f"{len(resultats)}/{len(taches)} terminés ({time.time() - t0:.0f} s)", flush=True)
    resultats.sort(key=lambda r: r["i"])
    sortie = {
        "temperatures": TEMPERATURES,
        "plages": PLAGES,
        "monte_carlo": resultats[:n],
        "tornade": resultats[n:],
        "duree_s": time.time() - t0,
    }
    (RES / "incertitudes.json").write_text(json.dumps(sortie, indent=1), encoding="utf-8")
    echecs = [r for r in resultats if "erreur" in r]
    print(f"Terminé en {time.time() - t0:.0f} s, {len(echecs)} échec(s)")


if __name__ == "__main__":
    main()
