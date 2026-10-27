#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Base nationale des postes préfectoraux en poste — mise à jour hebdomadaire.

Principe :
  1. Télécharge le flux XML des nominations du Journal Officiel (data.gouv.fr),
     filtré sur une fenêtre temporelle (--mois).
  2. Pour chaque décision concernant un poste préfectoral (préfet, préfet de
     région/zone, sous-préfet d'arrondissement, directeur de cabinet, chargé
     de mission auprès du préfet, secrétaire général de préfecture, SGAR),
     détermine l'action : prise de poste (nomination/renouvellement) ou
     cessation de fonction.
  3. Met à jour un fichier d'état persistant (etat_prefets.json) qui reflète,
     poste par poste, qui est actuellement en fonction.
  4. Exporte cet état dans un fichier CSV lisible (base_prefets.csv), trié par
     territoire, pour consultation directe.

Usage :
  Premier lancement (constitue l'historique) :
      python3 maj_base_prefets.py --mois 36 --init
  Lancements hebdomadaires suivants (cron) :
      python3 maj_base_prefets.py --mois 1

IMPORTANT — limites à connaître :
  - Le poste est déduit du texte libre du JO par expressions régulières
    (voir poste_prefectoral.py). Le texte brut ('texte_source') est TOUJOURS
    conservé dans l'état et dans l'export pour permettre une vérification
    manuelle. Les cas non reconnus tombent dans 'poste_texte_brut' plutôt
    que d'être classés à tort — mieux vaut être visible qu'être silencieux.
  - Le fichier d'état est cumulatif : ne pas le supprimer entre deux
    exécutions hebdomadaires, sinon l'historique antérieur à la fenêtre
    --mois est perdu.
"""

import requests
import xml.etree.ElementTree as ET
import csv
import json
import argparse
import os
from datetime import datetime, timedelta

from poste_prefectoral import classifier_postes, LIBELLES_ROLE

os.makedirs('data', exist_ok=True)  # Crée data/ si n'existe pas
URL_JO = "https://www.data.gouv.fr/api/1/datasets/r/1c5ac28d-92ca-4a19-aefb-63fbde4387a2"
FICHIER_ETAT = "data/etat_prefets.json"
FICHIER_CSV = "data/base_prefets.csv"



# ---------------------------------------------------------------------------
# 1. Téléchargement et extraction brute (repris/adapté de prefet_scrapper.py)
# ---------------------------------------------------------------------------

def parse_date(date_str):
    if not date_str or not date_str.strip():
        return None
    try:
        return datetime.strptime(date_str[:10], '%Y-%m-%d')
    except Exception:
        return None

def extraire_texte_concatene(element, tag):
    if element is None:
        return ""
    textes = [e.text.strip() for e in element.findall(tag) if e.text and e.text.strip()]
    return " | ".join(textes) if textes else ""

def extraire_evenement(result):
    donnees = {}
    donnees['type_decision'] = result.get('type_ordre', '')
    donnees['date_publication'] = parse_date(result.get('source_date', ''))
    donnees['date_effet'] = parse_date(result.get('date_debut', ''))
    donnees['source'] = result.get('source_name', '')
    donnees['source_id'] = result.get('source_id', '')

    person = result.find('person')
    if person is not None:
        name = person.find('name')
        if name is not None:
            donnees['nom'] = (name.get('nom', '') or '').upper()
            donnees['prenom'] = (name.get('prenom', '') or '').title()
            donnees['nom_complet'] = name.text.strip() if name.text else f"{donnees['prenom']} {donnees['nom']}"
        else:
            donnees['nom'], donnees['prenom'], donnees['nom_complet'] = '', '', ''
        donnees['sexe'] = person.get('sexe', result.get('sexe', ''))
    else:
        donnees['nom'], donnees['prenom'], donnees['nom_complet'] = '', '', ''
        donnees['sexe'] = result.get('sexe', '')

    obj = result.find('object')
    donnees['texte_poste'] = extraire_texte_concatene(obj, 'text') if obj is not None else ''
    donnees['texte_contexte'] = extraire_texte_concatene(person, 'text') if person is not None else ''

    return donnees

def telecharger_evenements(nb_mois_arriere):
    date_limite = datetime.now() - timedelta(days=nb_mois_arriere * 30)
    print(f"Téléchargement du JO (décisions depuis le {date_limite.strftime('%d/%m/%Y')})...")
    evenements = []
    response = requests.get(URL_JO, stream=True)
    response.raw.decode_content = True
    total, retenus = 0, 0
    for event, elem in ET.iterparse(response.raw, events=('end',)):
        if elem.tag == 'result':
            total += 1
            date_pub = parse_date(elem.get('source_date', ''))
            if date_pub and date_pub >= date_limite:
                evenements.append(extraire_evenement(elem))
                retenus += 1
                if retenus % 500 == 0:
                    print(f"   ... {retenus} décisions retenues ({total} analysées)")
            elem.clear()
    print(f"{retenus} décisions retenues sur {total} analysées.\n")
    return evenements


# ---------------------------------------------------------------------------
# 2. Mise à jour de l'état persistant
# ---------------------------------------------------------------------------

ACTIONS_PRISE_POSTE = {'nomination', 'renouvellement'}
ACTIONS_DEPART = {'cessation de fonction'}

# Champ d'application volontairement restreint : uniquement le titre de préfet(ète)
# lui-même (départemental, région, zone de défense). Les sous-préfets, directeurs
# de cabinet, SGAR, etc. sont exclus car le texte du JO y est plus composite et
# le risque d'erreur plus élevé (cf. décision du 16/09/2026).
ROLES_RETENUS = {'prefet', 'prefet_region', 'prefet_zone'}

def charger_etat():
    if os.path.exists(FICHIER_ETAT):
        with open(FICHIER_ETAT, encoding='utf-8') as f:
            return json.load(f)
    return {"postes": {}, "source_id_traites": [], "date_maj": None}

def sauvegarder_etat(etat):
    with open(FICHIER_ETAT, 'w', encoding='utf-8') as f:
        json.dump(etat, f, ensure_ascii=False, indent=2, default=str)

def cle_poste(role, territoire):
    return f"{role}|{territoire}"

def appliquer_evenements(etat, evenements):
    aujourd_hui = datetime.now()
    deja_traites = set(etat.get('source_id_traites', []))
    nouveaux_traites = []

    # traiter dans l'ordre chronologique (date d'effet si connue, sinon date de publication)
    def cle_tri(e):
        return e['date_effet'] or e['date_publication'] or datetime.min
    evenements_tries = sorted(evenements, key=cle_tri)

    for ev in evenements_tries:
        if ev['source_id'] and ev['source_id'] in deja_traites:
            continue
        texte = ev['texte_poste'] or ev['texte_contexte']
        postes = classifier_postes(texte)
        action = ev['type_decision']

        if not postes:
            nouveaux_traites.append(ev['source_id'])
            continue

        date_ref = ev['date_effet'] or ev['date_publication']
        titulaire = {
            'nom_complet': ev['nom_complet'],
            'nom': ev['nom'],
            'prenom': ev['prenom'],
            'sexe': ev['sexe'],
            'date_decision': ev['date_publication'].strftime('%d/%m/%Y') if ev['date_publication'] else '',
            'date_prise_fonction': date_ref.strftime('%d/%m/%Y') if date_ref else '',
            'source_id': ev['source_id'],
            'texte_source': texte,
        }

        for role, territoire in postes:
            if role not in ROLES_RETENUS:
                continue
            cle = cle_poste(role, territoire)
            poste = etat['postes'].setdefault(cle, {
                'role': role,
                'role_libelle': LIBELLES_ROLE.get(role, role),
                'territoire': territoire,
                'titulaire_actuel': None,
                'titulaire_designe': None,
                'historique': [],
            })

            if action in ACTIONS_PRISE_POSTE:
                est_future = bool(date_ref and date_ref > aujourd_hui)
                if est_future:
                    poste['titulaire_designe'] = titulaire
                else:
                    if poste['titulaire_actuel']:
                        poste['historique'].append({**poste['titulaire_actuel'], 'action': 'remplacé'})
                    poste['titulaire_actuel'] = titulaire
                    if poste['titulaire_designe'] and poste['titulaire_designe'].get('source_id') == titulaire['source_id']:
                        poste['titulaire_designe'] = None
            elif action in ACTIONS_DEPART:
                if poste['titulaire_actuel'] and poste['titulaire_actuel'].get('nom_complet') == titulaire['nom_complet']:
                    poste['historique'].append({**poste['titulaire_actuel'], 'action': 'cessation de fonction'})
                    poste['titulaire_actuel'] = None
                else:
                    poste['historique'].append({**titulaire, 'action': 'cessation de fonction (titulaire précédent non identifié en base)'})
            # autres types de décision (délégation de signature, etc.) : ignorés pour l'état

        nouveaux_traites.append(ev['source_id'])

    # promotion des désignations dont la date de prise de fonction est désormais atteinte
    for poste in etat['postes'].values():
        desig = poste.get('titulaire_designe')
        if desig and desig.get('date_prise_fonction'):
            try:
                d = datetime.strptime(desig['date_prise_fonction'], '%d/%m/%Y')
            except ValueError:
                d = None
            if d and d <= aujourd_hui:
                if poste['titulaire_actuel']:
                    poste['historique'].append({**poste['titulaire_actuel'], 'action': 'remplacé'})
                poste['titulaire_actuel'] = desig
                poste['titulaire_designe'] = None

    etat['source_id_traites'] = list(deja_traites | set(nouveaux_traites))
    etat['date_maj'] = aujourd_hui.strftime('%d/%m/%Y %H:%M')
    return etat


# ---------------------------------------------------------------------------
# 3. Export CSV lisible
# ---------------------------------------------------------------------------

ORDRE_ROLES = ['prefet_region', 'prefet_zone', 'prefet']

DEPARTEMENTS = {
    "Ain": "01",
    "Aisne": "02",
    "Allier": "03",
    "Alpes-de-Haute-Provence": "04",
    "Hautes-Alpes": "05",
    "Alpes-Maritimes": "06",
    "Ardèche": "07",
    "Ardennes": "08",
    "Ariège": "09",
    "Aube": "10",
    "Aude": "11",
    "Aveyron": "12",
    "Bouches-du-Rhône": "13",
    "Calvados": "14",
    "Cantal": "15",
    "Charente": "16",
    "Charente-Maritime": "17",
    "Cher": "18",
    "Corrèze": "19",
    "Corse-du-Sud": "2A",
    "Haute-Corse": "2B",
    "Côte-d'Or": "21",
    "Côtes-d'Armor": "22",
    "Creuse": "23",
    "Dordogne": "24",
    "Doubs": "25",
    "Drôme": "26",
    "Eure": "27",
    "Eure-et-Loir": "28",
    "Finistère": "29",
    "Gard": "30",
    "Haute-Garonne": "31",
    "Gers": "32",
    "Gironde": "33",
    "Hérault": "34",
    "Ille-et-Vilaine": "35",
    "Indre": "36",
    "Indre-et-Loire": "37",
    "Isère": "38",
    "Jura": "39",
    "Landes": "40",
    "Loir-et-Cher": "41",
    "Loire": "42",
    "Haute-Loire": "43",
    "Loire-Atlantique": "44",
    "Loiret": "45",
    "Lot": "46",
    "Lot-et-Garonne": "47",
    "Lozère": "48",
    "Maine-et-Loire": "49",
    "Manche": "50",
    "Marne": "51",
    "Haute-Marne": "52",
    "Mayenne": "53",
    "Meurthe-et-Moselle": "54",
    "Meuse": "55",
    "Morbihan": "56",
    "Moselle": "57",
    "Nièvre": "58",
    "Nord": "59",
    "Oise": "60",
    "Orne": "61",
    "Pas-de-Calais": "62",
    "Puy-de-Dôme": "63",
    "Pyrénées-Atlantiques": "64",
    "Hautes-Pyrénées": "65",
    "Pyrénées-Orientales": "66",
    "Bas-Rhin": "67",
    "Haut-Rhin": "68",
    "Rhône": "69",
    "Haute-Saône": "70",
    "Saône-et-Loire": "71",
    "Sarthe": "72",
    "Savoie": "73",
    "Haute-Savoie": "74",
    "Paris": "75",
    "Seine-Maritime": "76",
    "Seine-et-Marne": "77",
    "Yvelines": "78",
    "Deux-Sèvres": "79",
    "Somme": "80",
    "Tarn": "81",
    "Tarn-et-Garonne": "82",
    "Var": "83",
    "Vaucluse": "84",
    "Vendée": "85",
    "Vienne": "86",
    "Haute-Vienne": "87",
    "Vosges": "88",
    "Yonne": "89",
    "Territoire de Belfort": "90",
    "Essonne": "91",
    "Hauts-de-Seine": "92",
    "Seine-Saint-Denis": "93",
    "Val-de-Marne": "94",
    "Val-d'Oise": "95",

    # Outre-mer
    "Guadeloupe": "971",
    "Martinique": "972",
    "Guyane": "973",
    "La Réunion": "974",
    "Réunion": "974",
    "Mayotte": "976",
    "Saint-Pierre-et-Miquelon": "975",
    "collectivité territoriale de Saint-Pierre-et-Miquelon": "975",
}

TITRES_COMPLEMENTAIRES = {

    "Loiret": {
        "region": "Centre-Val de Loire",
        "bassin": "Loire-Bretagne",
    },

    "Rhône": {
        "region": "Auvergne-Rhône-Alpes",
        "zone": "Sud-Est",
        "bassin": "Rhône-Méditerranée",
    },

    "Gironde": {
        "region": "Nouvelle-Aquitaine",
        "zone": "Sud-Ouest",
        "bassin": "Adour-Garonne",
    },

    "Nord": {
        "region": "Hauts-de-France",
        "zone": "Nord",
		"bassin": "Artois-Picardie",
    },

    "Bas-Rhin": {
        "region": "Grand Est",
        "zone": "Est",
		"bassin": "Rhin-Meuse",
    },

    "Bouches-du-Rhône": {
        "region": "Provence-Alpes-Côte d'Azur",
        "zone": "Sud",
        "bassin": "Rhône-Méditerranée",
    },

    "Ille-et-Vilaine": {
        "region": "Bretagne",
        "zone": "Ouest",
    },
	
	"Côte-d'Or": {
        "region": "Bourgogne-Franche-Comté",
    },
	
	"Haute-Garonne": {
        "region": "Occitanie",
		"bassin": "Adour-Garonne",
    },
	
	"Loire-Atlantique": {
        "region": "Pays de la Loire",
    },

	"Paris": {
        "region": "Île-de-France",
        "zone":"Paris",
    },
	
	"Seine-Maritime": {
        "region": "Normandie",
    },
	
	"Guadeloupe": {
        "region": "Guadeloupe",
    },
	
	"Martinique": {
        "region": "Martinique",
    },
	
	"Guyane": {
        "region": "Guyane",
    },
	"Réunion": {
        "region": "Réunion",
    }
}


def titre_prefet_departement(territoire, sexe):

    prefixe = "Préfète" if sexe == "F" else "Préfet"

    # cas "des"
    if territoire.startswith((
        "Alpes-",
        "Hautes-",
        "Pyrénées-",
        "Bouches-du-",
        "Côtes-d'",
        "Deux-Sèvres",
        "Hauts-de-",
        "Yvelines",
        "Landes",
        "Vosges",
        "Ardennes"
    )):
        article = "des"

    # cas "du"
    elif territoire in {
        "Bas-Rhin",
        "Doubs",
        "Finistère",
        "Gard",
        "Gers",
        "Jura",
        "Loiret",
        "Lot",
        "Nord",
        "Pas-de-Calais",
        "Rhône",
        "Tarn",
        "Var",
        "Cantal",
        "Calvados",
        "Cher",
        "Morbihan",
        "Territoire de Belfort",
        "Val-d'Oise",
        "Puy-de-Dôme"
    }:
        article = "du"

    # cas sans article
    elif territoire in {
        "Loir-et-Cher",
        "Lot-et-Garonne",
        "Maine-et-Loire",
        "Saône-et-Loire",
        "Tarn-et-Garonne",
        "Vaucluse",
        "Mayotte",
        "Paris",
        "Eure-et-Loir",
        "Indre-et-Loire",
        "Meurthe-et-Moselle",
        "Seine-et-Marne",
        "Saint-Pierre-et-Miquelon",
        "collectivité territoriale de Saint-Pierre-et-Miquelon"
    }:
        article = "de"

    # cas voyelle / h muet
    elif territoire[0].lower() in "aeiouyhàâéèêëîïôöùûü":
        article = "de l'"

    else:
        article = "de la"

    if article == "de l'":
        return f"{prefixe} {article}{territoire}"

    return f"{prefixe} {article} {territoire}"

def construire_titre_global(territoire, sexe):

    prefixe = "Préfète" if sexe == "F" else "Préfet"

    titres = [
        titre_prefet_departement(territoire, sexe)
    ]

    infos = TITRES_COMPLEMENTAIRES.get(territoire)

    # si aucun titre complémentaire
    # on retourne juste "Préfet de ..."
    if not infos:
        return " | ".join(titres)

    if infos.get("region"):
        titres.append(
            f"{prefixe} de la région {infos['region']}"
        )

    if infos.get("zone"):
        titres.append(
            f"{prefixe} de la zone de défense et de sécurité {infos['zone']}"
        )

    if infos.get("bassin"):

        if sexe == "F":
            titres.append(
                f"Préfète coordonnatrice de bassin {infos['bassin']}"
            )
        else:
            titres.append(
                f"Préfet coordonnateur de bassin {infos['bassin']}"
            )

    return " | ".join(titres)
    
def exporter_csv(etat):
    colonnes = [
        'role',
        'territoire',
        'departement',
        'prefet_de_departement',
        'titulaire_actuel_nom_complet',
        'titulaire_actuel_sexe',
        'date_decision',
        'date_prise_fonction',
        'titulaire_designe_nom_complet',
        'titulaire_designe_date_prise_fonction',
        'texte_source',
        'titre_global',
        'anciennete_jours',
        'couleur_carte'
    ]

    lignes = []

    for poste in etat['postes'].values():
        ta = poste.get('titulaire_actuel') or {}
        td = poste.get('titulaire_designe') or {}

        est_prefet_departement = poste['role'] == 'prefet'

        code_departement = (
            DEPARTEMENTS.get(poste['territoire'], '')
            if est_prefet_departement
            else ''
        )
        
        titre_global = ""

        if est_prefet_departement:
            titre_global = construire_titre_global(
                poste['territoire'],
                ta.get('sexe', '')
            )
            
            
        anciennete_jours = ''

        couleur_carte = ''

        date_pf = ta.get('date_prise_fonction', '')

        if date_pf:
            try:
                d = datetime.strptime(date_pf, '%d/%m/%Y')
                anciennete_jours = (datetime.now() - d).days

                if anciennete_jours > 730:
                    couleur_carte = 'rouge'
                elif anciennete_jours > 365:
                    couleur_carte = 'orange'
                elif anciennete_jours > 180:
                    couleur_carte = 'jaune'
                elif anciennete_jours > 15:
                    couleur_carte = 'vert'
                else:
                    couleur_carte = 'bleu'

            except ValueError:
                pass

        lignes.append({
            'role': poste['role_libelle'],
            'territoire': poste['territoire'],
            'departement': code_departement,
            'prefet_de_departement': 'Oui' if est_prefet_departement else '',
            'titulaire_actuel_nom_complet': ta.get('nom_complet', ''),
            'titulaire_actuel_sexe': ta.get('sexe', ''),
            'date_decision': ta.get('date_decision', ''),
            'date_prise_fonction': ta.get('date_prise_fonction', ''),
            'titulaire_designe_nom_complet': td.get('nom_complet', ''),
            'titulaire_designe_date_prise_fonction': td.get('date_prise_fonction', ''),
            'texte_source': ta.get('texte_source', ''),
            'titre_global': titre_global,
            'anciennete_jours': anciennete_jours,
            'couleur_carte': couleur_carte
        })

    def cle_tri(ligne):
        try:
            i = ORDRE_ROLES.index(
                [r for r, l in LIBELLES_ROLE.items() if l == ligne['role']][0]
            )
        except (IndexError, ValueError):
            i = 999

        return (i, ligne['territoire'])

    lignes.sort(key=cle_tri)

    with open(FICHIER_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=colonnes, delimiter=';')
        writer.writeheader()
        writer.writerows(lignes)

    print(f"Export CSV : {FICHIER_CSV} ({len(lignes)} postes)")
    
def exporter_prefets_departements(etat):

    fichier = "data/prefets_departements.csv"

    colonnes = [
        'departement',
        'territoire',
        'nom_prefet',
        'sexe',
        'titre_global',
        'date_prise_fonction',
        'anciennete_jours',
        'couleur_carte'
    ]

    lignes = []

    for poste in etat['postes'].values():

        if poste['role'] != 'prefet':
            continue

        ta = poste.get('titulaire_actuel') or {}

        territoire = poste['territoire']

        code_departement = DEPARTEMENTS.get(territoire, '')
        
        if not code_departement:
            continue

        titre_global = construire_titre_global(
            territoire,
            ta.get('sexe', '')
        )

        anciennete_jours = ''
        couleur_carte = ''

        date_pf = ta.get('date_prise_fonction', '')

        if date_pf:
            try:
                d = datetime.strptime(date_pf, '%d/%m/%Y')
                anciennete_jours = (datetime.now() - d).days

                if anciennete_jours > 730:
                    couleur_carte = 'red'
                elif anciennete_jours > 365:
                    couleur_carte = 'orange'
                elif anciennete_jours > 180:
                    couleur_carte = 'yellow'
                elif anciennete_jours > 15:
                    couleur_carte = 'green'
                else:
                    couleur_carte = 'blue'

            except:
                pass

        lignes.append({
            'departement': code_departement,
            'territoire': territoire,
            'nom_prefet': ta.get('nom_complet', ''),
            'sexe': ta.get('sexe', ''),
            'titre_global': titre_global,
            'date_prise_fonction': ta.get('date_prise_fonction', ''),
            'anciennete_jours': anciennete_jours,
            'couleur_carte': couleur_carte
        })

    lignes.sort(key=lambda x: x['departement'])

    with open(fichier, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=colonnes, delimiter=';')
        writer.writeheader()
        writer.writerows(lignes)

    print(f"Export : {fichier}")


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Met à jour la base nationale des postes préfectoraux")
    parser.add_argument('--mois', type=int, default=1, help="Fenêtre de recherche en mois (défaut: 1)")
    parser.add_argument('--init', action='store_true', help="Repart d'un état vide (à utiliser uniquement pour le tout premier lancement)")
    args = parser.parse_args()

    if args.init and os.path.exists(FICHIER_ETAT):
        os.remove(FICHIER_ETAT)

    etat = charger_etat()
    evenements = telecharger_evenements(args.mois)
    etat = appliquer_evenements(etat, evenements)
    sauvegarder_etat(etat)
    exporter_csv(etat)
    exporter_prefets_departements(etat)
    print(f"\nÉtat sauvegardé dans {FICHIER_ETAT}, dernière mise à jour : {etat['date_maj']}")

if __name__ == "__main__":
    main()
