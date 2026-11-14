"""Production sur météo réelle : chaîne air -> tour -> condenseur -> puissance.

1. Courbes de la centrale (balayage offdesign) : P_nette(T_eau_froide) et
   échauffement au condenseur R(T_eau_froide).
2. Tour à tirage naturel couplée à la centrale, tabulée sur une grille
   (température sèche, humidité relative) -> T_eau_froide.
3. Interpolation bilinéaire heure par heure sur la série météo, puis
   agrégation (énergie annuelle, profils mensuels, carte jour x année).

Hypothèses : réacteur à pleine puissance toutes les heures (pas
d'indisponibilité, pas de suivi de charge) ; pression atmosphérique égale à
la moyenne du site ; eau froide bornée à la plage du balayage (0-35 °C),
ce qui représente en hiver les dispositifs antigel de la tour.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.interpolate import RegularGridInterpolator

from .tour import TourNaturelle, couplage_centrale

GRILLE_T = np.arange(-22.0, 43.0, 1.0)
GRILLE_HR = np.arange(0.05, 1.0001, 0.05)


@dataclass
class CourbesCentrale:
    T: np.ndarray
    P_nette: np.ndarray
    plage: np.ndarray

    @classmethod
    def depuis_balayage(cls, df: pd.DataFrame) -> "CourbesCentrale":
        T = df.index.values.astype(float)
        plage = (df["T_sortie_eau_refroidissement_C"] - df["T_eau_refroidissement_C"]).values
        return cls(T, df["puissance_electrique_nette_MW"].values, plage)

    def borne(self, T):
        return np.clip(T, self.T.min(), self.T.max())

    def P(self, T):
        return np.interp(self.borne(T), self.T, self.P_nette)

    def R(self, T):
        return np.interp(self.borne(T), self.T, self.plage)


def table_tour(tour: TourNaturelle, courbes: CourbesCentrale, P_Pa: float) -> RegularGridInterpolator:
    """T_eau_froide(T_sèche, HR) pour la tour couplée à la centrale."""
    Z = np.empty((len(GRILLE_T), len(GRILLE_HR)))
    for i, Ts in enumerate(GRILLE_T):
        for j, hr in enumerate(GRILLE_HR):
            Z[i, j] = couplage_centrale(tour, float(Ts), float(hr), courbes.R, P_Pa)["T_eau_froide_C"]
    return RegularGridInterpolator((GRILLE_T, GRILLE_HR), Z, bounds_error=False, fill_value=None)


def production(meteo: pd.DataFrame, table, courbes: CourbesCentrale, dT_climat: float = 0.0) -> pd.DataFrame:
    """Puissance horaire. dT_climat décale la température sèche à humidité
    relative constante (hypothèse usuelle des scénarios simples)."""
    Ts = np.clip(meteo["T_seche_C"].values + dT_climat, GRILLE_T[0], GRILLE_T[-1])
    hr = np.clip(meteo["HR_pourcent"].values / 100.0, GRILLE_HR[0], GRILLE_HR[-1])
    Tf = table(np.column_stack([Ts, hr]))
    out = pd.DataFrame({
        "temps_utc": meteo["temps_utc"].values,
        "T_seche_C": Ts, "HR": hr,
        "T_eau_froide_C": Tf,
        "P_nette_MW": courbes.P(Tf),
    })
    return out


def synthese(prod: pd.DataFrame, P_ref_MW: float) -> dict:
    t = pd.to_datetime(prod["temps_utc"])
    par_an = prod.groupby(t.dt.year)["P_nette_MW"].agg(["sum", "count"])
    E_an_TWh = par_an["sum"] / 1e6
    # Écart à une centrale qui produirait P_ref toute l'année
    ecart_TWh = (par_an["sum"] - P_ref_MW * par_an["count"]) / 1e6
    mensuel = prod.groupby(t.dt.month).agg(P=("P_nette_MW", "mean"),
                                            P_min=("P_nette_MW", lambda s: s.quantile(0.05)),
                                            P_max=("P_nette_MW", lambda s: s.quantile(0.95)),
                                            Tf=("T_eau_froide_C", "mean"))
    return {
        "energie_annuelle_TWh": E_an_TWh.to_dict(),
        "energie_moyenne_TWh": float(E_an_TWh.mean()),
        "ecart_vs_design_TWh": ecart_TWh.to_dict(),
        "facteur_rendement_moyen": float(prod["P_nette_MW"].mean() / P_ref_MW),
        "P_moyenne_MW": float(prod["P_nette_MW"].mean()),
        "P_min_MW": float(prod["P_nette_MW"].min()),
        "P_max_MW": float(prod["P_nette_MW"].max()),
        "mensuel": mensuel.reset_index().rename(columns={"temps_utc": "mois"}).to_dict(orient="list"),
    }


def carte_journaliere(prod: pd.DataFrame) -> pd.DataFrame:
    """Puissance moyenne journalière : lignes = années, colonnes = jour de l'année."""
    t = pd.to_datetime(prod["temps_utc"])
    j = prod.assign(annee=t.dt.year, jour=t.dt.dayofyear).groupby(["annee", "jour"])["P_nette_MW"].mean()
    return j.unstack("jour")
