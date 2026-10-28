#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Met à jour les bases Préfets et DDT/DDTM, puis produit une base commune.

Exemples :
    python maj_administrations.py
    python maj_administrations.py --mois 2
    python maj_administrations.py --sans-maj
    python maj_administrations.py --mois 48 --init-ddt
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
DOSSIER_COMMUN = RACINE / "commun" / "data"

# À adapter si votre fichier préfets a un autre nom.
SCRIPT_PREFETS = DOSSIER_PREFETS / "maj_base_prefets.py"
SCRIPT_DDT = DOSSIER_DDT / "maj_base_ddt.py"

FICHIER_PREFETS = DOSSIER_PREFETS / "data" / "base_prefets.csv"
FICHIER_DDT = DOSSIER_DDT / "data" / "base_ddt.csv"
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
    Écarte donc les lignes parasites éventuellement extraites dans base_prefets :
    'police', 'région', 'classe normale', etc.
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


# ---------------------------------------------------------------------------
# Indexation des deux bases
# ---------------------------------------------------------------------------

def indexer_prefets(lignes):
    """
    Retourne un dictionnaire {code_departement: ligne_prefet}.

    Seules les lignes correspondant à un préfet départemental sont retenues.
    Cela exclut les préfets de région et de zone, qui n'ont pas de département.
    """
    prefets = {}

    for ligne in lignes:
        code = nettoyer(ligne.get("departement"))

        # Le fichier comporte plusieurs rôles : région, zone, préfet départemental.
        if nettoyer(ligne.get("role")) != "Préfet(ète)":
            continue

        if not est_code_departement(code):
            continue

        # Si plusieurs lignes existent accidentellement pour un même département,
        # on conserve celle qui contient un titulaire.
        ancienne_ligne = prefets.get(code)

        if ancienne_ligne is None:
            prefets[code] = ligne
        else:
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
# Fusion
# ---------------------------------------------------------------------------

def creer_base_commune():
    print("\n🔗 Fusion des bases Préfets et DDT/DDTM...")

    lignes_prefets = lire_csv(FICHIER_PREFETS)
    lignes_ddt = lire_csv(FICHIER_DDT)

    prefets = indexer_prefets(lignes_prefets)
    ddts = indexer_ddt(lignes_ddt)

    # Union : aucun territoire n'est perdu si une source ne le contient pas.
    codes_departements = sorted(
        set(prefets) | set(ddts),
        key=cle_tri_departement
    )

    colonnes = [
        "departement",
        "territoire",

        "prefet_nom_complet",
        "prefet_sexe",
        "prefet_date_decision",
        "prefet_date_prise_fonction",
        "prefet_anciennete_jours",
        "prefet_titre_global",
        "prefet_texte_source",

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
    ]

    lignes_sortie = []

    for code in codes_departements:
        prefet = prefets.get(code, {})
        ddt = ddts.get(code, {})

        # En principe les deux sources utilisent le même nom de territoire.
        # La donnée Préfet est prioritaire, car son périmètre est plus large.
        territoire = (
            nettoyer(prefet.get("territoire"))
            or nettoyer(ddt.get("territoire"))
        )

        # Cas où une ligne DDT est réellement absente du fichier.
        # À distinguer de "non concerné par une DDT/DDTM", qui est une information.
        statut_ddt = nettoyer(ddt.get("statut"))
        message_ddt = nettoyer(ddt.get("message"))

        if not ddt:
            statut_ddt = "non renseigné"
            message_ddt = (
                "Aucune ligne correspondante dans la base DDT/DDTM"
            )

        lignes_sortie.append({
            "departement": code,
            "territoire": territoire,

            "prefet_nom_complet": nettoyer(
                prefet.get("titulaire_actuel_nom_complet")
            ),
            "prefet_sexe": nettoyer(prefet.get("titulaire_actuel_sexe")),
            "prefet_date_decision": nettoyer(prefet.get("date_decision")),
            "prefet_date_prise_fonction": nettoyer(
                prefet.get("date_prise_fonction")
            ),
            "prefet_anciennete_jours": nettoyer(
                prefet.get("anciennete_jours")
            ),
            "prefet_titre_global": nettoyer(prefet.get("titre_global")),
            "prefet_texte_source": nettoyer(prefet.get("texte_source")),

            "ddt_type_poste": nettoyer(ddt.get("type_poste")),
            "ddt_titulaire_nom_complet": nettoyer(
                ddt.get("titulaire_actuel_nom_complet")
            ),
            "ddt_titulaire_sexe": nettoyer(
                ddt.get("titulaire_actuel_sexe")
            ),
            "ddt_grade": nettoyer(ddt.get("grade")),
            "ddt_date_decision": nettoyer(ddt.get("date_decision")),
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
            "ddt_texte_source": nettoyer(ddt.get("texte_source")),
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


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Met à jour les bases Préfets et DDT/DDTM, "
            "puis génère la base commune des administrations."
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

    args = parser.parse_args()

    try:
        if not args.sans_maj:
            # Les deux scripts doivent accepter l'argument --mois.
            lancer_script(
                "Base des préfets",
                args.script_prefets.resolve(),
                args.script_prefets.resolve().parent,
                ["--mois", str(args.mois)]
            )

            arguments_ddt = ["--mois", str(args.mois)]

            if args.init_ddt:
                arguments_ddt.append("--init")

            lancer_script(
                "Base des DDT/DDTM",
                args.script_ddt.resolve(),
                args.script_ddt.resolve().parent,
                arguments_ddt
            )

        creer_base_commune()

    except subprocess.CalledProcessError as erreur:
        print(
            f"\n❌ Échec lors de l'exécution d'un script source "
            f"(code retour : {erreur.returncode})."
        )
        sys.exit(erreur.returncode)

    except (FileNotFoundError, OSError) as erreur:
        print(f"\n❌ Erreur : {erreur}")
        sys.exit(1)


if __name__ == "__main__":
    main()