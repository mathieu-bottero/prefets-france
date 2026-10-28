#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Met à jour les bases Préfets, DDT/DDTM et DDETS/DDPP/DDETSPP,
puis produit une base commune.

Exemples :
    python maj_administrations.py
    python maj_administrations.py --mois 2
    python maj_administrations.py --sans-maj
    python maj_administrations.py --mois 48 --init-ddt --init-ddetspp
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
DOSSIER_COMMUN = RACINE / "commun" / "data"

SCRIPT_PREFETS = DOSSIER_PREFETS / "maj_base_prefets.py"
SCRIPT_DDT = DOSSIER_DDT / "maj_base_ddt.py"
SCRIPT_DDETSPP = DOSSIER_DDETSPP / "maj_base_ddets_ddpp.py"

FICHIER_PREFETS = DOSSIER_PREFETS / "data" / "base_prefets.csv"
FICHIER_DDT = DOSSIER_DDT / "data" / "base_ddt.csv"
FICHIER_DDETSPP = DOSSIER_DDETSPP / "data" / "base_ddets_ddpp.csv"

FICHIER_SORTIE = DOSSIER_COMMUN / "base_administrations.csv"


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
    """Évite les None dans le CSV de sortie."""
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
# Indexation des bases
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

    Les lignes informatives sans DDT/DDTM (Paris, outre-mer...) sont conservées.
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
# Fusion des trois bases
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

    print(f"✅ {len(lignes_sortie)} administrations fusionnées.")
    print(f"💾 Fichier créé : {FICHIER_SORTIE}")


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
            "Met à jour les bases Préfets, DDT/DDTM et "
            "DDETS/DDPP/DDETSPP, puis génère la base commune "
            "des administrations."
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
            "Ne relance pas les scripts sources : fusionne seulement "
            "les CSV déjà existants."
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

    args = parser.parse_args()

    try:
        if not args.sans_maj:
            script_prefets = args.script_prefets.resolve()
            script_ddt = args.script_ddt.resolve()
            script_ddetspp = args.script_ddetspp.resolve()

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

        # 4. Fusion des CSV produits
        creer_base_commune()

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