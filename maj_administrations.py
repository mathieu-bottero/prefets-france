#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Met à jour les bases :

- Préfets ;
- DDT / DDTM ;
- DDETS / DDPP / DDETSPP ;
- DREAL / DEAL / DRIEAT / DRIHL / DTAM / DGTM ;
- DREETS.

Puis produit deux fichiers communs :

- commun/data/base_administrations.csv
  Base des administrations départementales ;

- commun/data/base_administrations_regionales.csv
  Base des administrations régionales et assimilées.

Exemples :
    python maj_administrations.py
    python maj_administrations.py --mois 2
    python maj_administrations.py --sans-maj
    python maj_administrations.py --mois 48 --init-ddt --init-ddetspp
    python maj_administrations.py --mois 120 --init-dreal --init-dreets
    python maj_administrations.py --mois 120 --init-ddt --init-ddetspp --init-dreal --init-dreets
"""

import argparse
import csv
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Chemins du projet
# ---------------------------------------------------------------------------

RACINE = Path(__file__).resolve().parent

DOSSIER_PREFETS = RACINE / "prefets"
DOSSIER_DDT = RACINE / "ddt"
DOSSIER_DDETSPP = RACINE / "ddetspp"
DOSSIER_DREAL = RACINE / "dreal"
DOSSIER_DREETS = RACINE / "dreets"
DOSSIER_COMMUN = RACINE / "commun" / "data"

SCRIPT_PREFETS = DOSSIER_PREFETS / "maj_base_prefets.py"
SCRIPT_DDT = DOSSIER_DDT / "maj_base_ddt.py"
SCRIPT_DDETSPP = DOSSIER_DDETSPP / "maj_base_ddets_ddpp.py"
SCRIPT_DREAL = DOSSIER_DREAL / "maj_base_dreal.py"
SCRIPT_DREETS = DOSSIER_DREETS / "maj_base_dreets.py"

FICHIER_PREFETS = DOSSIER_PREFETS / "data" / "base_prefets.csv"
FICHIER_DDT = DOSSIER_DDT / "data" / "base_ddt.csv"
FICHIER_DDETSPP = DOSSIER_DDETSPP / "data" / "base_ddets_ddpp.csv"
FICHIER_DREAL = DOSSIER_DREAL / "data" / "base_dreal.csv"
FICHIER_DREETS = DOSSIER_DREETS / "data" / "base_dreets.csv"

FICHIER_SORTIE = DOSSIER_COMMUN / "base_administrations.csv"

FICHIER_SORTIE_REGIONALES = (
    DOSSIER_COMMUN / "base_administrations_regionales.csv"
)


# ---------------------------------------------------------------------------
# Utilitaires CSV
# ---------------------------------------------------------------------------

def lire_csv(chemin):
    """Lit un CSV séparé par ;, encodé UTF-8 avec ou sans BOM."""
    if not chemin.exists():
        raise FileNotFoundError(f"Fichier introuvable : {chemin}")

    with open(chemin, "r", encoding="utf-8-sig", newline="") as fichier:
        return list(csv.DictReader(fichier, delimiter=";"))


def nettoyer(valeur):
    """Évite les None et les espaces superflus dans le CSV de sortie."""
    return (valeur or "").strip()


def est_code_departement(code):
    """
    Ne conserve que les départements français métropolitains, Corse et outre-mer.

    Écarte les lignes parasites éventuellement présentes dans les sources :
    région, zone, police, classe normale, etc.
    """
    code = nettoyer(code)

    if code in {"2A", "2B"}:
        return True

    if code.isdigit():
        numero = int(code)

        return (
            1 <= numero <= 95
            or code in {"971", "972", "973", "974", "975", "976"}
        )

    return False


def cle_tri_departement(code):
    """Tri cohérent : 01..95, 2A/2B, puis 971..976."""
    if code == "2A":
        return (20, 1)

    if code == "2B":
        return (20, 2)

    try:
        return (int(code), 0)
    except ValueError:
        return (9999, 0)


# ---------------------------------------------------------------------------
# Indexation des bases départementales
# ---------------------------------------------------------------------------

def indexer_prefets(lignes):
    """
    Retourne un dictionnaire {code_departement: ligne_prefet}.

    Seules les lignes correspondant à un préfet départemental sont retenues.
    Les préfets de région ou de zone sont donc exclus.
    """
    prefets = {}

    for ligne in lignes:
        code = nettoyer(ligne.get("departement"))

        if nettoyer(ligne.get("role")) != "Préfet(ète)":
            continue

        if not est_code_departement(code):
            continue

        # En cas de doublon, privilégier la ligne avec un titulaire.
        ancienne_ligne = prefets.get(code)

        if ancienne_ligne is None:
            prefets[code] = ligne
            continue

        ancien_titulaire = nettoyer(
            ancienne_ligne.get("titulaire_actuel_nom_complet")
        )
        nouveau_titulaire = nettoyer(
            ligne.get("titulaire_actuel_nom_complet")
        )

        if not ancien_titulaire and nouveau_titulaire:
            prefets[code] = ligne

    return prefets


def indexer_ddt(lignes):
    """
    Retourne un dictionnaire {code_departement: ligne_ddt}.

    Les lignes informatives sans DDT/DDTM
    (Paris, outre-mer, organisation spécifique...) sont conservées.
    """
    ddts = {}

    for ligne in lignes:
        code = nettoyer(ligne.get("departement"))

        if not est_code_departement(code):
            continue

        ddts[code] = ligne

    return ddts


def indexer_ddetspp(lignes):
    """
    Retourne un dictionnaire {code_departement: ligne_ddetspp}.

    Une ligne du fichier base_ddets_ddpp.csv correspond à un département.
    Les lignes décrivant une organisation spécifique sont également conservées.
    """
    ddetspp = {}

    for ligne in lignes:
        code = nettoyer(ligne.get("departement"))

        if not est_code_departement(code):
            continue

        ddetspp[code] = ligne

    return ddetspp


# ---------------------------------------------------------------------------
# Fusion des bases départementales
# ---------------------------------------------------------------------------

def creer_base_commune():
    """Fusionne les bases Préfets, DDT/DDTM et DDETS/DDPP/DDETSPP."""
    print("\n🔗 Fusion des bases Préfets, DDT/DDTM et DDETS/DDPP/DDETSPP...")

    lignes_prefets = lire_csv(FICHIER_PREFETS)
    lignes_ddt = lire_csv(FICHIER_DDT)
    lignes_ddetspp = lire_csv(FICHIER_DDETSPP)

    prefets_par_departement = indexer_prefets(lignes_prefets)
    ddts_par_departement = indexer_ddt(lignes_ddt)
    ddetspp_par_departement = indexer_ddetspp(lignes_ddetspp)

    # Union : aucun département n'est perdu si une source est incomplète.
    codes_departements = sorted(
        set(prefets_par_departement)
        | set(ddts_par_departement)
        | set(ddetspp_par_departement),
        key=cle_tri_departement
    )

    colonnes = [
        # Identification
        "departement",
        "territoire",

        # Préfets
        "prefet_nom_complet",
        "prefet_sexe",
        "prefet_date_decision",
        "prefet_date_prise_fonction",
        "prefet_anciennete_jours",
        "prefet_titre_global",
        "prefet_texte_source",

        # DDT / DDTM
        "ddt_type_poste",
        "ddt_titulaire_nom_complet",
        "ddt_titulaire_sexe",
        "ddt_grade",
        "ddt_date_decision",
        "ddt_date_prise_fonction",
        "ddt_anciennete_jours",
        "ddt_titulaire_designe_nom_complet",
        "ddt_titulaire_designe_date_prise_fonction",
        "ddt_statut",
        "ddt_message",
        "ddt_texte_source",

        # Organisation DDETS / DDPP / DDETSPP
        "ddetspp_type_organisation",
        "ddetspp_population_estimee",

        # Directeur / directrice DDETS
        "ddetspp_directeur_ddets_nom_complet",
        "ddetspp_directeur_ddets_sexe",
        "ddetspp_directeur_ddets_grade",
        "ddetspp_directeur_ddets_date_decision",
        "ddetspp_directeur_ddets_date_prise_fonction",
        "ddetspp_directeur_ddets_anciennete_jours",
        "ddetspp_directeur_ddets_designe_nom",
        "ddetspp_directeur_ddets_designe_date",

        # Directeur / directrice DDPP
        "ddetspp_directeur_ddpp_nom_complet",
        "ddetspp_directeur_ddpp_sexe",
        "ddetspp_directeur_ddpp_grade",
        "ddetspp_directeur_ddpp_date_decision",
        "ddetspp_directeur_ddpp_date_prise_fonction",
        "ddetspp_directeur_ddpp_anciennete_jours",
        "ddetspp_directeur_ddpp_designe_nom",
        "ddetspp_directeur_ddpp_designe_date",

        # Directeur / directrice DDETSPP
        "ddetspp_directeur_ddetspp_nom_complet",
        "ddetspp_directeur_ddetspp_sexe",
        "ddetspp_directeur_ddetspp_grade",
        "ddetspp_directeur_ddetspp_date_decision",
        "ddetspp_directeur_ddetspp_date_prise_fonction",
        "ddetspp_directeur_ddetspp_anciennete_jours",
        "ddetspp_directeur_ddetspp_designe_nom",
        "ddetspp_directeur_ddetspp_designe_date",

        # Statut général de la source DDETS/DDPP/DDETSPP
        "ddetspp_statut",
        "ddetspp_message",
    ]

    lignes_sortie = []

    for code in codes_departements:
        prefet = prefets_par_departement.get(code, {})
        ddt = ddts_par_departement.get(code, {})
        ddetspp = ddetspp_par_departement.get(code, {})

        # Priorité au territoire de la base préfets, puis DDT, puis DDETS/DDPP.
        territoire = (
            nettoyer(prefet.get("territoire"))
            or nettoyer(ddt.get("territoire"))
            or nettoyer(ddetspp.get("territoire"))
        )

        # Statut DDT : distinguer l'absence d'une ligne de l'information
        # « non concerné / organisation spécifique » portée dans la ligne.
        statut_ddt = nettoyer(ddt.get("statut"))
        message_ddt = nettoyer(ddt.get("message"))

        if not ddt:
            statut_ddt = "non renseigné"
            message_ddt = (
                "Aucune ligne correspondante dans la base DDT/DDTM"
            )

        # Même logique pour la base DDETS / DDPP / DDETSPP.
        statut_ddetspp = nettoyer(ddetspp.get("statut"))
        message_ddetspp = nettoyer(ddetspp.get("message"))

        if not ddetspp:
            statut_ddetspp = "non renseigné"
            message_ddetspp = (
                "Aucune ligne correspondante dans la base "
                "DDETS/DDPP/DDETSPP"
            )

        lignes_sortie.append({
            # Identification
            "departement": code,
            "territoire": territoire,

            # Préfets
            "prefet_nom_complet": nettoyer(
                prefet.get("titulaire_actuel_nom_complet")
            ),
            "prefet_sexe": nettoyer(
                prefet.get("titulaire_actuel_sexe")
            ),
            "prefet_date_decision": nettoyer(
                prefet.get("date_decision")
            ),
            "prefet_date_prise_fonction": nettoyer(
                prefet.get("date_prise_fonction")
            ),
            "prefet_anciennete_jours": nettoyer(
                prefet.get("anciennete_jours")
            ),
            "prefet_titre_global": nettoyer(
                prefet.get("titre_global")
            ),
            "prefet_texte_source": nettoyer(
                prefet.get("texte_source")
            ),

            # DDT / DDTM
            "ddt_type_poste": nettoyer(ddt.get("type_poste")),
            "ddt_titulaire_nom_complet": nettoyer(
                ddt.get("titulaire_actuel_nom_complet")
            ),
            "ddt_titulaire_sexe": nettoyer(
                ddt.get("titulaire_actuel_sexe")
            ),
            "ddt_grade": nettoyer(ddt.get("grade")),
            "ddt_date_decision": nettoyer(
                ddt.get("date_decision")
            ),
            "ddt_date_prise_fonction": nettoyer(
                ddt.get("date_prise_fonction")
            ),
            "ddt_anciennete_jours": nettoyer(
                ddt.get("anciennete_jours")
            ),
            "ddt_titulaire_designe_nom_complet": nettoyer(
                ddt.get("titulaire_designe_nom_complet")
            ),
            "ddt_titulaire_designe_date_prise_fonction": nettoyer(
                ddt.get("titulaire_designe_date_prise_fonction")
            ),
            "ddt_statut": statut_ddt,
            "ddt_message": message_ddt,
            "ddt_texte_source": nettoyer(
                ddt.get("texte_source")
            ),

            # Organisation DDETS / DDPP / DDETSPP
            "ddetspp_type_organisation": nettoyer(
                ddetspp.get("type_organisation")
            ),
            "ddetspp_population_estimee": nettoyer(
                ddetspp.get("population_estimee")
            ),

            # DDETS
            "ddetspp_directeur_ddets_nom_complet": nettoyer(
                ddetspp.get("directeur_ddets_nom_complet")
            ),
            "ddetspp_directeur_ddets_sexe": nettoyer(
                ddetspp.get("directeur_ddets_sexe")
            ),
            "ddetspp_directeur_ddets_grade": nettoyer(
                ddetspp.get("directeur_ddets_grade")
            ),
            "ddetspp_directeur_ddets_date_decision": nettoyer(
                ddetspp.get("directeur_ddets_date_decision")
            ),
            "ddetspp_directeur_ddets_date_prise_fonction": nettoyer(
                ddetspp.get("directeur_ddets_date_prise_fonction")
            ),
            "ddetspp_directeur_ddets_anciennete_jours": nettoyer(
                ddetspp.get("directeur_ddets_anciennete_jours")
            ),
            "ddetspp_directeur_ddets_designe_nom": nettoyer(
                ddetspp.get("directeur_ddets_designe_nom")
            ),
            "ddetspp_directeur_ddets_designe_date": nettoyer(
                ddetspp.get("directeur_ddets_designe_date")
            ),

            # DDPP
            "ddetspp_directeur_ddpp_nom_complet": nettoyer(
                ddetspp.get("directeur_ddpp_nom_complet")
            ),
            "ddetspp_directeur_ddpp_sexe": nettoyer(
                ddetspp.get("directeur_ddpp_sexe")
            ),
            "ddetspp_directeur_ddpp_grade": nettoyer(
                ddetspp.get("directeur_ddpp_grade")
            ),
            "ddetspp_directeur_ddpp_date_decision": nettoyer(
                ddetspp.get("directeur_ddpp_date_decision")
            ),
            "ddetspp_directeur_ddpp_date_prise_fonction": nettoyer(
                ddetspp.get("directeur_ddpp_date_prise_fonction")
            ),
            "ddetspp_directeur_ddpp_anciennete_jours": nettoyer(
                ddetspp.get("directeur_ddpp_anciennete_jours")
            ),
            "ddetspp_directeur_ddpp_designe_nom": nettoyer(
                ddetspp.get("directeur_ddpp_designe_nom")
            ),
            "ddetspp_directeur_ddpp_designe_date": nettoyer(
                ddetspp.get("directeur_ddpp_designe_date")
            ),

            # DDETSPP
            "ddetspp_directeur_ddetspp_nom_complet": nettoyer(
                ddetspp.get("directeur_ddetspp_nom_complet")
            ),
            "ddetspp_directeur_ddetspp_sexe": nettoyer(
                ddetspp.get("directeur_ddetspp_sexe")
            ),
            "ddetspp_directeur_ddetspp_grade": nettoyer(
                ddetspp.get("directeur_ddetspp_grade")
            ),
            "ddetspp_directeur_ddetspp_date_decision": nettoyer(
                ddetspp.get("directeur_ddetspp_date_decision")
            ),
            "ddetspp_directeur_ddetspp_date_prise_fonction": nettoyer(
                ddetspp.get("directeur_ddetspp_date_prise_fonction")
            ),
            "ddetspp_directeur_ddetspp_anciennete_jours": nettoyer(
                ddetspp.get("directeur_ddetspp_anciennete_jours")
            ),
            "ddetspp_directeur_ddetspp_designe_nom": nettoyer(
                ddetspp.get("directeur_ddetspp_designe_nom")
            ),
            "ddetspp_directeur_ddetspp_designe_date": nettoyer(
                ddetspp.get("directeur_ddetspp_designe_date")
            ),

            # Statut DDETS / DDPP / DDETSPP
            "ddetspp_statut": statut_ddetspp,
            "ddetspp_message": message_ddetspp,
        })

    DOSSIER_COMMUN.mkdir(parents=True, exist_ok=True)

    with open(
        FICHIER_SORTIE,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as fichier:
        writer = csv.DictWriter(
            fichier,
            fieldnames=colonnes,
            delimiter=";"
        )
        writer.writeheader()
        writer.writerows(lignes_sortie)

    print(f"✅ {len(lignes_sortie)} administrations départementales fusionnées.")
    print(f"💾 Fichier créé : {FICHIER_SORTIE}")


# ---------------------------------------------------------------------------
# Export de la base des administrations régionales
# ---------------------------------------------------------------------------

COLONNES_REGIONALES_BASE = [
    "code_region",
    "region",
    "type_poste",
    "departements_couverts",
    "titulaire_actuel_nom_complet",
    "titulaire_actuel_sexe",
    "grade",
    "date_decision",
    "date_prise_fonction",
    "anciennete_jours",
    "titulaire_designe_nom_complet",
    "titulaire_designe_date_prise_fonction",
    "texte_source",
    "statut",
]

# Ces colonnes sont utilisées uniquement pour la DRIHL.
# Sur la ligne Île-de-France, les colonnes standards correspondent à la DRIEAT.
COLONNES_DRIHL = [
    "drihl_type_poste",
    "drihl_titulaire_actuel_nom_complet",
    "drihl_titulaire_actuel_sexe",
    "drihl_grade",
    "drihl_date_decision",
    "drihl_date_prise_fonction",
    "drihl_anciennete_jours",
    "drihl_titulaire_designe_nom_complet",
    "drihl_titulaire_designe_date_prise_fonction",
    "drihl_texte_source",
    "drihl_statut",
]

# Ces colonnes sont utilisées pour la DREETS.
COLONNES_DREETS = [
    "dreets_type_poste",
    "dreets_titulaire_actuel_nom_complet",
    "dreets_titulaire_actuel_sexe",
    "dreets_grade",
    "dreets_date_decision",
    "dreets_date_prise_fonction",
    "dreets_anciennete_jours",
    "dreets_titulaire_designe_nom_complet",
    "dreets_titulaire_designe_date_prise_fonction",
    "dreets_texte_source",
    "dreets_statut",
]

COLONNES_REGIONALES = COLONNES_REGIONALES_BASE + COLONNES_DRIHL + COLONNES_DREETS


def cle_tri_regionale(ligne):
    """Tri par code région puis intitulé de direction."""
    code_region = nettoyer(ligne.get("code_region"))

    try:
        ordre_code = int(code_region)
    except ValueError:
        ordre_code = 9999

    return (
        ordre_code,
        nettoyer(ligne.get("region")),
        nettoyer(ligne.get("type_poste")),
    )


def ligne_drihl(drihl):
    """
    Transforme une ligne DRIHL technique en colonnes DRIHL destinées
    à être ajoutées à la ligne DRIEAT Île-de-France.
    """
    if not drihl:
        return {
            colonne: ""
            for colonne in COLONNES_DRIHL
        }

    return {
        "drihl_type_poste": nettoyer(drihl.get("type_poste")),
        "drihl_titulaire_actuel_nom_complet": nettoyer(
            drihl.get("titulaire_actuel_nom_complet")
        ),
        "drihl_titulaire_actuel_sexe": nettoyer(
            drihl.get("titulaire_actuel_sexe")
        ),
        "drihl_grade": nettoyer(drihl.get("grade")),
        "drihl_date_decision": nettoyer(
            drihl.get("date_decision")
        ),
        "drihl_date_prise_fonction": nettoyer(
            drihl.get("date_prise_fonction")
        ),
        "drihl_anciennete_jours": nettoyer(
            drihl.get("anciennete_jours")
        ),
        "drihl_titulaire_designe_nom_complet": nettoyer(
            drihl.get("titulaire_designe_nom_complet")
        ),
        "drihl_titulaire_designe_date_prise_fonction": nettoyer(
            drihl.get("titulaire_designe_date_prise_fonction")
        ),
        "drihl_texte_source": nettoyer(
            drihl.get("texte_source")
        ),
        "drihl_statut": nettoyer(drihl.get("statut")),
    }


def ligne_dreets_vide():
    """Retourne un dictionnaire avec toutes les colonnes DREETS vides."""
    return {
        colonne: ""
        for colonne in COLONNES_DREETS
    }


def creer_base_administrations_regionales():
    """
    Crée commun/data/base_administrations_regionales.csv à partir de
    dreal/data/base_dreal.csv et dreets/data/base_dreets.csv.

    Règles particulières :
      - l'ancienne DEAL Guyane est exclue ;
      - DRIEAT et DRIHL sont regroupées sur une même ligne Île-de-France ;
      - les colonnes classiques de cette ligne correspondent à la DRIEAT ;
      - la DRIHL est renseignée dans les colonnes drihl_* ;
      - les DREETS sont fusionnées par code région avec les DREAL ;
      - les colonnes principales (type_poste, titulaire, etc.) correspondent
        à la DREAL/DRIEAT/DEAL/etc. ;
      - les informations DREETS sont dans les colonnes dreets_*.
    """
    print("\n🔗 Création de la base des administrations régionales...")

    lignes_dreal = lire_csv(FICHIER_DREAL)
    lignes_dreets = lire_csv(FICHIER_DREETS)

    # Indexer les DREETS par code région
    dreets_par_region = {}
    for ligne in lignes_dreets:
        code_region = nettoyer(ligne.get("code_region"))
        if code_region:
            dreets_par_region[code_region] = ligne

    lignes_sortie = []
    drihl_ile_de_france = None
    drieat_ile_de_france = None

    for ligne in lignes_dreal:
        region = nettoyer(ligne.get("region"))
        type_poste = nettoyer(ligne.get("type_poste"))
        code_region = nettoyer(ligne.get("code_region"))

        if not region or not type_poste:
            continue

        type_poste_minuscule = type_poste.lower()

        # Sécurité supplémentaire : même si une ancienne DEAL Guyane
        # demeure dans le fichier source, elle ne sort jamais dans
        # la base régionale consolidée.
        if (
            region == "Guyane"
            and "environnement" in type_poste_minuscule
            and "logement" in type_poste_minuscule
        ):
            continue

        est_drihl = (
            region == "Île-de-France"
            and "hébergement et du logement" in type_poste_minuscule
        )

        est_drieat = (
            region == "Île-de-France"
            and "environnement" in type_poste_minuscule
            and "transports" in type_poste_minuscule
        )

        if est_drihl:
            drihl_ile_de_france = ligne
            continue

        if est_drieat:
            drieat_ile_de_france = ligne
            continue

        ligne_sortie = {
            colonne: nettoyer(ligne.get(colonne))
            for colonne in COLONNES_REGIONALES_BASE
        }

        ligne_sortie.update(ligne_drihl(None))

        # Ajouter les informations DREETS si disponibles
        dreets = dreets_par_region.get(code_region)
        if dreets:
            ligne_sortie.update({
                "dreets_type_poste": nettoyer(dreets.get("type_poste")),
                "dreets_titulaire_actuel_nom_complet": nettoyer(
                    dreets.get("titulaire_actuel_nom_complet")
                ),
                "dreets_titulaire_actuel_sexe": nettoyer(
                    dreets.get("titulaire_actuel_sexe")
                ),
                "dreets_grade": nettoyer(dreets.get("grade")),
                "dreets_date_decision": nettoyer(
                    dreets.get("date_decision")
                ),
                "dreets_date_prise_fonction": nettoyer(
                    dreets.get("date_prise_fonction")
                ),
                "dreets_anciennete_jours": nettoyer(
                    dreets.get("anciennete_jours")
                ),
                "dreets_titulaire_designe_nom_complet": nettoyer(
                    dreets.get("titulaire_designe_nom_complet")
                ),
                "dreets_titulaire_designe_date_prise_fonction": nettoyer(
                    dreets.get("titulaire_designe_date_prise_fonction")
                ),
                "dreets_texte_source": nettoyer(
                    dreets.get("texte_source")
                ),
                "dreets_statut": nettoyer(dreets.get("statut")),
            })
        else:
            ligne_sortie.update(ligne_dreets_vide())

        lignes_sortie.append(ligne_sortie)

    # Cas normal : création d'une ligne unique DRIEAT + DRIHL.
    if drieat_ile_de_france:
        ligne_idf = {
            colonne: nettoyer(drieat_ile_de_france.get(colonne))
            for colonne in COLONNES_REGIONALES_BASE
        }

        ligne_idf.update(ligne_drihl(drihl_ile_de_france))
        
        # Ajouter DREETS Île-de-France
        code_region_idf = nettoyer(drieat_ile_de_france.get("code_region"))
        dreets_idf = dreets_par_region.get(code_region_idf)
        if dreets_idf:
            ligne_idf.update({
                "dreets_type_poste": nettoyer(dreets_idf.get("type_poste")),
                "dreets_titulaire_actuel_nom_complet": nettoyer(
                    dreets_idf.get("titulaire_actuel_nom_complet")
                ),
                "dreets_titulaire_actuel_sexe": nettoyer(
                    dreets_idf.get("titulaire_actuel_sexe")
                ),
                "dreets_grade": nettoyer(dreets_idf.get("grade")),
                "dreets_date_decision": nettoyer(
                    dreets_idf.get("date_decision")
                ),
                "dreets_date_prise_fonction": nettoyer(
                    dreets_idf.get("date_prise_fonction")
                ),
                "dreets_anciennete_jours": nettoyer(
                    dreets_idf.get("anciennete_jours")
                ),
                "dreets_titulaire_designe_nom_complet": nettoyer(
                    dreets_idf.get("titulaire_designe_nom_complet")
                ),
                "dreets_titulaire_designe_date_prise_fonction": nettoyer(
                    dreets_idf.get("titulaire_designe_date_prise_fonction")
                ),
                "dreets_texte_source": nettoyer(
                    dreets_idf.get("texte_source")
                ),
                "dreets_statut": nettoyer(dreets_idf.get("statut")),
            })
        else:
            ligne_idf.update(ligne_dreets_vide())

        lignes_sortie.append(ligne_idf)

    # Cas de sécurité : si la DRIHL existe mais que la DRIEAT est absente,
    # on ne perd pas l'information. Elle sort alors seule.
    elif drihl_ile_de_france:
        ligne_idf = {
            colonne: ""
            for colonne in COLONNES_REGIONALES_BASE
        }

        ligne_idf["code_region"] = nettoyer(
            drihl_ile_de_france.get("code_region")
        )
        ligne_idf["region"] = nettoyer(
            drihl_ile_de_france.get("region")
        )
        ligne_idf["departements_couverts"] = nettoyer(
            drihl_ile_de_france.get("departements_couverts")
        )

        ligne_idf.update(ligne_drihl(drihl_ile_de_france))
        
        # Ajouter DREETS Île-de-France même dans ce cas
        code_region_idf = nettoyer(drihl_ile_de_france.get("code_region"))
        dreets_idf = dreets_par_region.get(code_region_idf)
        if dreets_idf:
            ligne_idf.update({
                "dreets_type_poste": nettoyer(dreets_idf.get("type_poste")),
                "dreets_titulaire_actuel_nom_complet": nettoyer(
                    dreets_idf.get("titulaire_actuel_nom_complet")
                ),
                "dreets_titulaire_actuel_sexe": nettoyer(
                    dreets_idf.get("titulaire_actuel_sexe")
                ),
                "dreets_grade": nettoyer(dreets_idf.get("grade")),
                "dreets_date_decision": nettoyer(
                    dreets_idf.get("date_decision")
                ),
                "dreets_date_prise_fonction": nettoyer(
                    dreets_idf.get("date_prise_fonction")
                ),
                "dreets_anciennete_jours": nettoyer(
                    dreets_idf.get("anciennete_jours")
                ),
                "dreets_titulaire_designe_nom_complet": nettoyer(
                    dreets_idf.get("titulaire_designe_nom_complet")
                ),
                "dreets_titulaire_designe_date_prise_fonction": nettoyer(
                    dreets_idf.get("titulaire_designe_date_prise_fonction")
                ),
                "dreets_texte_source": nettoyer(
                    dreets_idf.get("texte_source")
                ),
                "dreets_statut": nettoyer(dreets_idf.get("statut")),
            })
        else:
            ligne_idf.update(ligne_dreets_vide())

        lignes_sortie.append(ligne_idf)

    lignes_sortie.sort(key=cle_tri_regionale)

    DOSSIER_COMMUN.mkdir(parents=True, exist_ok=True)

    with open(
        FICHIER_SORTIE_REGIONALES,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as fichier:
        writer = csv.DictWriter(
            fichier,
            fieldnames=COLONNES_REGIONALES,
            delimiter=";"
        )
        writer.writeheader()
        writer.writerows(lignes_sortie)

    print(
        f"✅ {len(lignes_sortie)} administrations régionales exportées."
    )
    print(f"💾 Fichier créé : {FICHIER_SORTIE_REGIONALES}")


# ---------------------------------------------------------------------------
# Exécution des scripts de mise à jour
# ---------------------------------------------------------------------------

def lancer_script(nom, script, dossier, arguments):
    """Lance un script Python dans son propre dossier."""
    if not script.exists():
        raise FileNotFoundError(
            f"Le script {nom} est introuvable : {script}"
        )

    commande = [sys.executable, script.name] + arguments

    print(f"\n{'=' * 78}")
    print(f"🚀 Mise à jour : {nom}")
    print(f"{'=' * 78}")

    subprocess.run(
        commande,
        cwd=dossier,
        check=True
    )


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Met à jour les bases Préfets, DDT/DDTM, "
            "DDETS/DDPP/DDETSPP, "
            "DREAL/DEAL/DRIEAT/DRIHL/DTAM/DGTM et DREETS, "
            "puis génère les bases communes départementale et régionale."
        )
    )

    parser.add_argument(
        "--mois",
        type=int,
        default=1,
        help="Nombre de mois à analyser pour les mises à jour (défaut : 1)."
    )

    parser.add_argument(
        "--sans-maj",
        action="store_true",
        help=(
            "Ne relance pas les scripts sources : régénère seulement "
            "les CSV communs à partir des bases existantes."
        )
    )

    parser.add_argument(
        "--init-ddt",
        action="store_true",
        help=(
            "Transmet --init au script DDT. "
            "À utiliser uniquement lors d'une reconstruction complète."
        )
    )

    parser.add_argument(
        "--init-ddetspp",
        action="store_true",
        help=(
            "Transmet --init au script DDETS/DDPP/DDETSPP. "
            "À utiliser uniquement lors d'une reconstruction complète."
        )
    )

    parser.add_argument(
        "--init-dreal",
        action="store_true",
        help=(
            "Transmet --init au script "
            "DREAL/DEAL/DRIEAT/DRIHL/DTAM/DGTM. "
            "À utiliser uniquement lors d'une reconstruction complète."
        )
    )

    parser.add_argument(
        "--init-dreets",
        action="store_true",
        help=(
            "Transmet --init au script DREETS. "
            "À utiliser uniquement lors d'une reconstruction complète."
        )
    )

    parser.add_argument(
        "--script-prefets",
        type=Path,
        default=SCRIPT_PREFETS,
        help="Chemin du script de mise à jour des préfets."
    )

    parser.add_argument(
        "--script-ddt",
        type=Path,
        default=SCRIPT_DDT,
        help="Chemin du script de mise à jour des DDT/DDTM."
    )

    parser.add_argument(
        "--script-ddetspp",
        type=Path,
        default=SCRIPT_DDETSPP,
        help="Chemin du script de mise à jour des DDETS/DDPP/DDETSPP."
    )

    parser.add_argument(
        "--script-dreal",
        type=Path,
        default=SCRIPT_DREAL,
        help=(
            "Chemin du script de mise à jour des "
            "DREAL/DEAL/DRIEAT/DRIHL/DTAM/DGTM."
        )
    )

    parser.add_argument(
        "--script-dreets",
        type=Path,
        default=SCRIPT_DREETS,
        help="Chemin du script de mise à jour des DREETS."
    )

    args = parser.parse_args()

    try:
        if not args.sans_maj:
            script_prefets = args.script_prefets.resolve()
            script_ddt = args.script_ddt.resolve()
            script_ddetspp = args.script_ddetspp.resolve()
            script_dreal = args.script_dreal.resolve()
            script_dreets = args.script_dreets.resolve()

            # 1. Préfets
            lancer_script(
                "Base des préfets",
                script_prefets,
                script_prefets.parent,
                ["--mois", str(args.mois)]
            )

            # 2. DDT / DDTM
            arguments_ddt = ["--mois", str(args.mois)]

            if args.init_ddt:
                arguments_ddt.append("--init")

            lancer_script(
                "Base des DDT/DDTM",
                script_ddt,
                script_ddt.parent,
                arguments_ddt
            )

            # 3. DDETS / DDPP / DDETSPP
            arguments_ddetspp = ["--mois", str(args.mois)]

            if args.init_ddetspp:
                arguments_ddetspp.append("--init")

            lancer_script(
                "Base des DDETS/DDPP/DDETSPP",
                script_ddetspp,
                script_ddetspp.parent,
                arguments_ddetspp
            )

            # 4. DREAL / DEAL / DRIEAT / DRIHL / DTAM / DGTM
            arguments_dreal = ["--mois", str(args.mois)]

            if args.init_dreal:
                arguments_dreal.append("--init")

            lancer_script(
                "Base des DREAL/DEAL/DRIEAT/DRIHL/DTAM/DGTM",
                script_dreal,
                script_dreal.parent,
                arguments_dreal
            )

            # 5. DREETS
            arguments_dreets = ["--mois", str(args.mois)]

            if args.init_dreets:
                arguments_dreets.append("--init")

            lancer_script(
                "Base des DREETS",
                script_dreets,
                script_dreets.parent,
                arguments_dreets
            )

        # 6. Création de la base départementale commune.
        # Cette étape est aussi réalisée avec --sans-maj.
        creer_base_commune()

        # 7. Création de la base régionale commune (avec DREETS).
        # Cette étape est aussi réalisée avec --sans-maj.
        creer_base_administrations_regionales()

    except subprocess.CalledProcessError as erreur:
        print(
            "\n❌ Échec lors de l'exécution d'un script source "
            f"(code retour : {erreur.returncode})."
        )
        sys.exit(erreur.returncode)

    except (FileNotFoundError, OSError) as erreur:
        print(f"\n❌ Erreur : {erreur}")
        sys.exit(1)


if __name__ == "__main__":
    main()