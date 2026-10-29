#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Base nationale des directeurs régionaux DREAL / DEAL / DRIEAT / DTAM / DGTM
en poste — mise à jour hebdomadaire.
"""

import requests
import xml.etree.ElementTree as ET
import csv
import json
import time
import argparse
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib3.exceptions import ProtocolError, IncompleteRead as Urllib3IncompleteRead
from http.client import IncompleteRead as HttpIncompleteRead

from poste_dreal import classifier_poste_dreal, LIBELLES_TYPE

URL_JO = "https://www.data.gouv.fr/api/1/datasets/r/1c5ac28d-92ca-4a19-aefb-63fbde4387a2"

_RACINE_SCRIPT = Path(__file__).resolve().parent
FICHIER_ETAT   = str(_RACINE_SCRIPT / "data" / "etat_dreal.json")
FICHIER_CSV    = str(_RACINE_SCRIPT / "data" / "base_dreal.csv")

CHUNK_SIZE    = 4 * 1024 * 1024
NB_TENTATIVES = 5
DELAI_RETRY   = 10

os.makedirs(_RACINE_SCRIPT / "data", exist_ok=True)


MOIS_FR = {
    "janvier": 1,
    "février": 2,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
    "decembre": 12,
}


def extraire_date_effet_texte(texte):
    """Extrait une date telle que « à compter du 1er octobre 2025 ». """
    match = re.search(
        r"\bà\s+compter\s+du\s+(\d{1,2})(?:er)?\s+"
        r"(janvier|février|fevrier|mars|avril|mai|juin|juillet|"
        r"août|aout|septembre|octobre|novembre|décembre|decembre)\s+"
        r"(\d{4})\b",
        texte,
        re.IGNORECASE
    )
    if not match:
        return None

    jour = int(match.group(1))
    mois = MOIS_FR[match.group(2).lower()]
    annee = int(match.group(3))
    return datetime(annee, mois, jour)
    
# ── Mapping code région → nom canonique ──────────────────────────────────────

REGIONS = {
    "84": "Auvergne-Rhône-Alpes",
    "27": "Bourgogne-Franche-Comté",
    "53": "Bretagne",
    "24": "Centre-Val de Loire",
    "94": "Corse",
    "44": "Grand Est",
    "32": "Hauts-de-France",
    "11": "Île-de-France",
    "28": "Normandie",
    "76": "Occitanie",
    "52": "Pays de la Loire",
    "75": "Nouvelle-Aquitaine",
    "93": "Provence-Alpes-Côte d'Azur",
    # DOM
    "01": "Guadeloupe",
    "02": "Martinique",
    "03": "Guyane",
    "04": "Réunion",
    "06": "Mayotte",
    # Collectivité sui generis
    "05": "Saint-Pierre-et-Miquelon",
}

NOM_VERS_CODE = {v: k for k, v in REGIONS.items()}

DEPTS_PAR_REGION = {
    "84": ["01", "03", "07", "15", "26", "38", "42", "43", "63", "69", "73", "74"],
    "27": ["21", "25", "39", "58", "70", "71", "89", "90"],
    "53": ["22", "29", "35", "56"],
    "24": ["18", "28", "36", "37", "41", "45"],
    "94": ["2A", "2B"],
    "44": ["08", "10", "51", "52", "54", "55", "57", "67", "68", "88"],
    "32": ["02", "59", "60", "62", "80"],
    "11": ["75", "77", "78", "91", "92", "93", "94", "95"],
    "28": ["14", "27", "50", "61", "76"],
    "76": ["09", "11", "12", "30", "31", "32", "34", "46", "48", "65", "66", "81", "82"],
    "52": ["44", "49", "53", "72", "85"],
    "75": ["16", "17", "19", "23", "24", "33", "40", "47", "64", "79", "86", "87"],
    "93": ["04", "05", "06", "13", "83", "84"],
    "01": ["971"],
    "02": ["972"],
    "03": ["973"],
    "04": ["974"],
    "06": ["976"],
    "05": ["975"],
}


# ---------------------------------------------------------------------------
# 1. Utilitaires XML
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
    textes = [e.text.strip() for e in element.findall(tag)
              if e.text and e.text.strip()]
    return " | ".join(textes) if textes else ""


def extraire_evenement(result):
    donnees = {}
    donnees['type_decision']    = result.get('type_ordre', '')
    donnees['date_publication'] = parse_date(result.get('source_date', ''))
    donnees['date_effet']       = parse_date(result.get('date_debut', ''))
    donnees['source']           = result.get('source_name', '')
    donnees['source_id']        = result.get('source_id', '')

    person = result.find('person')
    if person is not None:
        name = person.find('name')
        if name is not None:
            donnees['nom']         = (name.get('nom', '') or '').upper()
            donnees['prenom']      = (name.get('prenom', '') or '').title()
            donnees['nom_complet'] = (name.text.strip()
                                     if name.text
                                     else f"{donnees['prenom']} {donnees['nom']}")
        else:
            donnees['nom'] = donnees['prenom'] = donnees['nom_complet'] = ''
        donnees['sexe'] = person.get('sexe', result.get('sexe', ''))
    else:
        donnees['nom'] = donnees['prenom'] = donnees['nom_complet'] = ''
        donnees['sexe'] = result.get('sexe', '')

    obj = result.find('object')
    donnees['texte_poste'] = (
        extraire_texte_concatene(obj, 'text') if obj is not None else ''
    )
    donnees['texte_contexte'] = (
        extraire_texte_concatene(person, 'text') if person is not None else ''
    )

    # Repli : le flux XML peut ne pas fournir date_debut,
    # alors que l'arrêté la précise dans son texte.
    if not donnees['date_effet']:
        donnees['date_effet'] = extraire_date_effet_texte(
            donnees['texte_poste']
        )

    return donnees


# ---------------------------------------------------------------------------
# 2. Téléchargement / streaming
# ---------------------------------------------------------------------------

def telecharger_evenements(nb_mois_arriere):
    date_limite = datetime.now() - timedelta(days=nb_mois_arriere * 30)
    print(f"\n📡 Connexion au flux JO (depuis le {date_limite.strftime('%d/%m/%Y')})...")

    MOTS_CLES = (
        "directeur régional de l'environnement",
        "directrice régionale de l'environnement",
        "directeur de l'environnement, de l'aménagement",
        "directrice de l'environnement, de l'aménagement",
        "directeur régional et interdépartemental de l'environnement",
        "directrice régionale et interdépartementale de l'environnement",

        "directeur régional et interdépartemental de l'hébergement et du logement",
        "directrice régionale et interdépartementale de l'hébergement et du logement",

        "directeur des territoires, de l'alimentation et de la mer",
        "directrice des territoires, de l'alimentation et de la mer",
        "directeur général des territoires et de la mer",
        "directrice générale des territoires et de la mer",
    )
    TYPES_RETENUS = {'nomination', 'renouvellement', 'charge'}

    print("🔍 Parsing en streaming (pas de téléchargement complet)...")

    evenements = []
    total, retenus = 0, 0

    for tentative in range(1, NB_TENTATIVES + 1):
        try:
            response = requests.get(URL_JO, stream=True, timeout=120)
            response.raise_for_status()
            response.raw.decode_content = True

            for event, elem in ET.iterparse(response.raw, events=('end',)):
                if elem.tag != 'result':
                    continue

                total += 1
                if total % 100_000 == 0:
                    print(f"   📊 {total} nominations analysées, "
                          f"{retenus} DREAL/DEAL/DRIEAT/DTAM/DGTM retenues...")

                date_pub = parse_date(elem.get('source_date', ''))
                if not date_pub or date_pub < date_limite:
                    elem.clear()
                    continue

                if elem.get('type_ordre', '').lower() not in TYPES_RETENUS:
                    elem.clear()
                    continue

                obj = elem.find('object')
                texte_poste = extraire_texte_concatene(obj, 'text') if obj is not None else ''
                texte_lower = texte_poste.lower()

                if not any(mot in texte_lower for mot in MOTS_CLES):
                    elem.clear()
                    continue

                donnees = extraire_evenement(elem)
                if not donnees.get('texte_poste'):
                    donnees['texte_poste'] = texte_poste

                evenements.append(donnees)
                retenus += 1
                elem.clear()

            print(f"✅ {retenus} nominations DREAL/DEAL/DRIEAT/DTAM/DGTM "
                  f"retenues sur {total} analysées.\n")
            return evenements

        except (
            ProtocolError,
            Urllib3IncompleteRead,
            HttpIncompleteRead,
            requests.exceptions.ChunkedEncodingError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as e:
            print(f"\n   ⚠️  Coupure réseau (tentative {tentative}/{NB_TENTATIVES}) : {e}")
            if tentative < NB_TENTATIVES:
                print(f"   ⏳ Nouvelle tentative dans {DELAI_RETRY}s...")
                time.sleep(DELAI_RETRY)
            else:
                print(f"\n   ❌ Échec après {NB_TENTATIVES} tentatives.")
                raise

    return evenements


# ---------------------------------------------------------------------------
# 3. Gestion de l'état persistant
# ---------------------------------------------------------------------------

ACTIONS_PRISE_POSTE = {'nomination', 'renouvellement', 'charge'}
ACTIONS_DEPART      = {'cessation de fonction', 'fin de détachement'}


def charger_etat():
    if os.path.exists(FICHIER_ETAT):
        with open(FICHIER_ETAT, encoding='utf-8') as f:
            return json.load(f)
    return {
        "postes": {},
        "source_id_traites": [],
        "date_maj": None,
        "statistiques": {
            "total_dreal":  0,
            "total_deal":   0,
            "total_drieat": 0,
            "total_drihl":  0,
            "total_dtam":   0,
            "total_dgtm":   0,
        }
    }


def sauvegarder_etat(etat):
    with open(FICHIER_ETAT, 'w', encoding='utf-8') as f:
        json.dump(etat, f, ensure_ascii=False, indent=2, default=str)


def cle_poste(type_poste, territoire):
    """
    Identifie une direction de façon unique.

    L'Île-de-France comporte notamment :
      - la DRIEAT ;
      - la DRIHL.

    Le territoire seul ne peut donc pas être une clé de poste.
    """
    return f"{type_poste.strip().lower()}::{territoire.strip()}"


def date_titulaire(poste):
    titulaire = poste.get('titulaire_actuel') or poste.get('titulaire_designe') or {}
    valeur = titulaire.get('date_prise_fonction', '')
    try:
        return datetime.strptime(valeur, '%d/%m/%Y')
    except (TypeError, ValueError):
        return datetime.min


def migrer_postes_doublons(etat):
    """
    Migration des anciennes clés historiques.

    Ancien format :
        Île-de-France

    Nouveau format :
        drieat::Île-de-France
        drihl::Île-de-France

    Les fusions éventuelles ne doivent donc s'opérer que pour un même
    couple (type de direction, territoire).
    """
    groupes = {}

    for ancienne_cle, poste in etat.get('postes', {}).items():
        type_poste = poste.get('type', '').strip().lower()
        territoire = poste.get('territoire', '').strip()
        
        # Nettoyage des anciennes entrées DEAL Guyane conservées dans
        # etat_dreal.json avant la création de la DGTM.
        if type_poste == 'deal' and territoire == 'Guyane':
            print(
                "🧹 Ancienne DEAL Guyane retirée : "
                "la direction compétente est désormais la DGTM."
            )
            continue

        if not type_poste or not territoire:
            print(
                f"⚠️ Poste ignoré durant la migration : "
                f"clé={ancienne_cle!r}, type={type_poste!r}, "
                f"territoire={territoire!r}"
            )
            continue

        nouvelle_cle = cle_poste(type_poste, territoire)
        groupes.setdefault(nouvelle_cle, []).append((ancienne_cle, poste))

    postes_migres = {}
    nb_fusions = 0

    for nouvelle_cle, elements in groupes.items():
        # Le plus récent est conservé comme état actif.
        elements.sort(
            key=lambda item: date_titulaire(item[1]),
            reverse=True
        )

        _, poste_gagnant = elements[0]
        poste_gagnant.setdefault('historique', [])

        for _, ancien_poste in elements[1:]:
            nb_fusions += 1

            poste_gagnant['historique'].extend(
                ancien_poste.get('historique', [])
            )

            ancien_titulaire = ancien_poste.get('titulaire_actuel')
            if ancien_titulaire:
                deja_present = any(
                    h.get('source_id') == ancien_titulaire.get('source_id')
                    for h in poste_gagnant['historique']
                )

                if not deja_present:
                    poste_gagnant['historique'].append({
                        **ancien_titulaire,
                        'action': 'doublon historique fusionné',
                        'date_fin': (
                            (poste_gagnant.get('titulaire_actuel') or {})
                            .get('date_prise_fonction', '')
                        ),
                    })

        postes_migres[nouvelle_cle] = poste_gagnant

    etat['postes'] = postes_migres

    if nb_fusions:
        print(f"🔧 Migration : {nb_fusions} ancien(s) poste(s) fusionné(s).")

    return etat


def appliquer_evenements(etat, evenements):
    aujourd_hui = datetime.now()
    deja_traites = set(etat.get('source_id_traites', []))
    nouveaux_traites = []

    def cle_tri(e):
        return e['date_effet'] or e['date_publication'] or datetime.min

    evenements_tries = sorted(evenements, key=cle_tri)
    print("📝 Application des événements...\n")
    modifications = 0

    for ev in evenements_tries:
        if ev['source_id'] and ev['source_id'] in deja_traites:
            continue

        texte    = ev['texte_poste'] or ev['texte_contexte']
        resultat = classifier_poste_dreal(texte)

        if not resultat:
            nouveaux_traites.append(ev['source_id'])
            continue

        type_poste, territoire, grade = resultat
        # L'ancienne DEAL Guyane n'existe plus : elle est remplacée par la DGTM.
        # On marque toutefois l'événement comme traité pour ne pas le revoir
        # à chaque exécution.
        if type_poste == 'obsolete_deal_guyane':
            nouveaux_traites.append(ev['source_id'])
            continue
            
        action   = ev['type_decision']
        date_ref = ev['date_effet'] or ev['date_publication']

        # ── Détection des intérimaires ─────────────────────────────────────
        est_interimaire = bool(re.search(r'\bpar\s+int[eé]rim\b', texte, re.IGNORECASE))
        
        titulaire = {
            'nom_complet':         ev['nom_complet'],
            'nom':                 ev['nom'],
            'prenom':              ev['prenom'],
            'sexe':                ev['sexe'],
            'grade':               grade,
            'date_decision':       ev['date_publication'].strftime('%d/%m/%Y') if ev['date_publication'] else '',
            'date_prise_fonction': date_ref.strftime('%d/%m/%Y') if date_ref else '',
            'source_id':           ev['source_id'],
            'texte_source':        texte,
            'interimaire':         est_interimaire,
        }

        cle = cle_poste(type_poste, territoire)

        if cle not in etat['postes']:
            etat['postes'][cle] = {
                'type':              type_poste,
                'type_libelle':      LIBELLES_TYPE.get(type_poste, type_poste),
                'territoire':        territoire,
                'code_region':       NOM_VERS_CODE.get(territoire, ''),
                'titulaire_actuel':  None,
                'titulaire_designe': None,
                'historique':        [],
            }

        poste = etat['postes'][cle]
        poste['type']         = type_poste
        poste['type_libelle'] = LIBELLES_TYPE.get(type_poste, type_poste)
        poste['code_region']  = NOM_VERS_CODE.get(territoire, poste.get('code_region', ''))

        if action in ACTIONS_PRISE_POSTE:
            est_future = bool(date_ref and date_ref > aujourd_hui)

            if est_future:
                # Une nomination future définitive a priorité sur tout
                if not est_interimaire:
                    poste['titulaire_designe'] = titulaire
                    print(f"   🔜 {territoire} : {ev['nom_complet']} "
                          f"(désigné pour le {date_ref.strftime('%d/%m/%Y')})")
                else:
                    # Un intérimaire futur : on le note seulement s'il n'y a pas déjà un titulaire désigné
                    if not poste.get('titulaire_designe'):
                        poste['titulaire_designe'] = titulaire
                        print(f"   🔜 {territoire} : {ev['nom_complet']} "
                              f"(par intérim, désigné pour le {date_ref.strftime('%d/%m/%Y')})")
                    else:
                        print(f"   ⏸️  {territoire} : {ev['nom_complet']} "
                              f"(intérimaire ignoré, titulaire désigné : "
                              f"{poste['titulaire_designe']['nom_complet']})")
            else:
                # Nomination passée ou actuelle
                if est_interimaire:
                    # C'est un intérimaire
                    titulaire_designe = poste.get('titulaire_designe')
                    
                    if titulaire_designe:
                        # Il y a un titulaire désigné : l'intérimaire ne devient actuel QUE si sa date est avant celle du désigné
                        try:
                            date_designe = datetime.strptime(titulaire_designe['date_prise_fonction'], '%d/%m/%Y')
                            if date_ref < date_designe:
                                # L'intérimaire prend le poste en attendant le titulaire
                                if poste['titulaire_actuel']:
                                    poste['historique'].append({
                                        **poste['titulaire_actuel'],
                                        'action': 'remplacé',
                                        'date_fin': date_ref.strftime('%d/%m/%Y') if date_ref else ''
                                    })
                                poste['titulaire_actuel'] = titulaire
                                print(f"   ⏰ {territoire} : {ev['nom_complet']} "
                                      f"(par intérim jusqu'au {date_designe.strftime('%d/%m/%Y')}, "
                                      f"en attente de {titulaire_designe['nom_complet']})")
                                modifications += 1
                            else:
                                # L'intérimaire est postérieur au titulaire désigné : on l'ignore
                                print(f"   ⏸️  {territoire} : {ev['nom_complet']} "
                                      f"(intérimaire ignoré, remplacé par {titulaire_designe['nom_complet']} "
                                      f"le {date_designe.strftime('%d/%m/%Y')})")
                        except ValueError:
                            # Problème de parsing de date, on prend l'intérimaire par défaut
                            if poste['titulaire_actuel']:
                                poste['historique'].append({
                                    **poste['titulaire_actuel'],
                                    'action': 'remplacé',
                                    'date_fin': date_ref.strftime('%d/%m/%Y') if date_ref else ''
                                })
                            poste['titulaire_actuel'] = titulaire
                            print(f"   ✅ {territoire} : {ev['nom_complet']} "
                                  f"(par intérim depuis le {date_ref.strftime('%d/%m/%Y')})")
                            modifications += 1
                    else:
                        # Pas de titulaire désigné, l'intérimaire prend le poste
                        if poste['titulaire_actuel']:
                            poste['historique'].append({
                                **poste['titulaire_actuel'],
                                'action': 'remplacé',
                                'date_fin': date_ref.strftime('%d/%m/%Y') if date_ref else ''
                            })
                        poste['titulaire_actuel'] = titulaire
                        print(f"   ✅ {territoire} : {ev['nom_complet']} "
                              f"(par intérim depuis le {date_ref.strftime('%d/%m/%Y')})")
                        modifications += 1
                else:
                    # C'est une nomination définitive
                    if poste['titulaire_actuel']:
                        poste['historique'].append({
                            **poste['titulaire_actuel'],
                            'action': 'remplacé',
                            'date_fin': date_ref.strftime('%d/%m/%Y') if date_ref else ''
                        })
                    poste['titulaire_actuel']  = titulaire
                    poste['titulaire_designe'] = None  # On efface le titulaire désigné car il est maintenant en poste
                    print(f"   ✅ {territoire} : {ev['nom_complet']} "
                          f"(depuis le {date_ref.strftime('%d/%m/%Y')})")
                    modifications += 1

        elif action in ACTIONS_DEPART:
            if poste['titulaire_actuel']:
                poste['historique'].append({
                    **poste['titulaire_actuel'],
                    'action': 'cessation de fonction',
                    'date_fin': date_ref.strftime('%d/%m/%Y') if date_ref else ''
                })
                print(f"   ⏹️  {territoire} : "
                      f"{poste['titulaire_actuel']['nom_complet']} (fin de fonction)")
                poste['titulaire_actuel'] = None
                modifications += 1

        nouveaux_traites.append(ev['source_id'])

    # Promotion automatique des désignés dont la date est passée
    for _, poste in etat['postes'].items():
        desig = poste.get('titulaire_designe')
        if desig and desig.get('date_prise_fonction'):
            try:
                d = datetime.strptime(desig['date_prise_fonction'], '%d/%m/%Y')
                if d <= aujourd_hui:
                    # Le titulaire désigné prend officiellement son poste
                    actuel = poste.get('titulaire_actuel')
                    if actuel:
                        poste['historique'].append({
                            **actuel,
                            'action': 'fin intérim' if actuel.get('interimaire') else 'remplacé',
                            'date_fin': d.strftime('%d/%m/%Y')
                        })
                    poste['titulaire_actuel']  = desig
                    poste['titulaire_designe'] = None
                    print(f"   🔄 {poste['territoire']} : "
                          f"{desig['nom_complet']} (prise de fonction effective)")
                    modifications += 1
            except ValueError:
                pass

    etat['source_id_traites'] = list(deja_traites | set(nouveaux_traites))
    etat['date_maj'] = aujourd_hui.strftime('%d/%m/%Y %H:%M')

    # ── Mise à jour des statistiques ────────────────────────────────────────
    etat['statistiques']['total_dreal']  = sum(
        1 for p in etat['postes'].values()
        if p['type'] == 'dreal' and p['titulaire_actuel']
    )
    etat['statistiques']['total_deal']   = sum(
        1 for p in etat['postes'].values()
        if p['type'] == 'deal' and p['titulaire_actuel']
    )
    etat['statistiques']['total_drieat'] = sum(
        1 for p in etat['postes'].values()
        if p['type'] == 'drieat' and p['titulaire_actuel']
    )
    etat['statistiques']['total_drihl'] = sum(
        1 for p in etat['postes'].values()
        if p['type'] == 'drihl' and p['titulaire_actuel']
    )
    etat['statistiques']['total_dtam']   = sum(
        1 for p in etat['postes'].values()
        if p['type'] == 'dtam' and p['titulaire_actuel']
    )
    etat['statistiques']['total_dgtm']   = sum(
        1 for p in etat['postes'].values()
        if p['type'] == 'dgtm' and p['titulaire_actuel']
    )

    print(f"\n✅ {modifications} modifications appliquées")
    return etat


# ---------------------------------------------------------------------------
# 4. Export CSV
# ---------------------------------------------------------------------------

COLONNES = [
    'code_region',
    'region',
    'type_poste',
    'departements_couverts',
    'titulaire_actuel_nom_complet',
    'titulaire_actuel_sexe',
    'grade',
    'date_decision',
    'date_prise_fonction',
    'anciennete_jours',
    'titulaire_designe_nom_complet',
    'titulaire_designe_date_prise_fonction',
    'texte_source',
    'statut',
]


def exporter_csv(etat):
    lignes = []

    for poste in etat['postes'].values():
        ta = poste.get('titulaire_actuel') or {}
        td = poste.get('titulaire_designe') or {}

        code_region = poste.get('code_region') or NOM_VERS_CODE.get(poste['territoire'], '')
        depts = DEPTS_PAR_REGION.get(code_region, [])

        anciennete_jours = ''
        date_pf = ta.get('date_prise_fonction', '')
        if date_pf:
            try:
                d = datetime.strptime(date_pf, '%d/%m/%Y')
                anciennete_jours = (datetime.now() - d).days
            except ValueError:
                pass

        lignes.append({
            'code_region':                           code_region,
            'region':                                poste['territoire'],
            'type_poste':                            poste['type_libelle'],
            'departements_couverts':                 ', '.join(depts),
            'titulaire_actuel_nom_complet':          ta.get('nom_complet', ''),
            'titulaire_actuel_sexe':                 ta.get('sexe', ''),
            'grade':                                 ta.get('grade', ''),
            'date_decision':                         ta.get('date_decision', ''),
            'date_prise_fonction':                   ta.get('date_prise_fonction', ''),
            'anciennete_jours':                      anciennete_jours,
            'titulaire_designe_nom_complet':         td.get('nom_complet', ''),
            'titulaire_designe_date_prise_fonction': td.get('date_prise_fonction', ''),
            'texte_source':                          ta.get('texte_source', ''),
            'statut': 'poste recensé' if ta else 'poste vacant ou inconnu',
        })

    lignes.sort(key=lambda x: x['code_region'])

    with open(FICHIER_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLONNES, delimiter=';')
        writer.writeheader()
        writer.writerows(lignes)

    print(f"\n💾 Export CSV : {FICHIER_CSV} ({len(lignes)} postes)")


# ---------------------------------------------------------------------------
# 5. Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Met à jour la base nationale des DREAL/DEAL/DRIEAT/DTAM/DGTM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python3 maj_base_dreal.py --mois 120 --init   # Premier lancement (10 ans d'historique)
  python3 maj_base_dreal.py --mois 1            # Mise à jour hebdomadaire
        """
    )
    parser.add_argument('--mois', type=int, default=1,
                        help="Fenêtre de recherche en mois (défaut: 1)")
    parser.add_argument('--init', action='store_true',
                        help="Repart d'un état vide (premier lancement uniquement)")
    args = parser.parse_args()

    print("""
╔════════════════════════════════════════════════════════════════════════════════════╗
║                                                                                    ║
║      BASE NATIONALE DREAL / DEAL / DRIEAT / DRIHL / DTAM / DGTM — MISE À JOUR      ║
║                                                                                    ║
╚════════════════════════════════════════════════════════════════════════════════════╝
    """)

    if args.init and os.path.exists(FICHIER_ETAT):
        os.remove(FICHIER_ETAT)
        print("🗑️  État précédent supprimé (mode --init)\n")

    # ── Chargement ──────────────────────────────────────────────────────────
    etat = charger_etat()
    etat = migrer_postes_doublons(etat)

    # ── Téléchargement ──────────────────────────────────────────────────────
    evenements = telecharger_evenements(args.mois)

    # ── Application ─────────────────────────────────────────────────────────
    etat = appliquer_evenements(etat, evenements)

    # ── Sauvegarde ──────────────────────────────────────────────────────────
    sauvegarder_etat(etat)
    print(f"💾 État sauvegardé : {FICHIER_ETAT}")

    # ── Export CSV ──────────────────────────────────────────────────────────
    exporter_csv(etat)

    # ── Statistiques ────────────────────────────────────────────────────────
    stats = etat['statistiques']
    total = (stats['total_dreal'] + stats['total_deal']
           + stats['total_drieat'] + stats['total_drihl']
           + stats['total_dtam'] + stats['total_dgtm'])

    print(f"""
╔════════════════════════════════════════════════════════════════════════════╗
║ STATISTIQUES                                                               ║
╠════════════════════════════════════════════════════════════════════════════╣
║  DREAL en poste  : {stats['total_dreal']:3d}                               ║
║  DEAL en poste   : {stats['total_deal']:3d}                                ║
║  DRIEAT en poste : {stats['total_drieat']:3d}                              ║
║  DRIHL en poste  : {stats['total_drihl']:3d}                               ║
║  DTAM en poste   : {stats['total_dtam']:3d}                                ║
║  DGTM en poste   : {stats['total_dgtm']:3d}                                ║
║  TOTAL           : {total:3d}                                              ║
║                                                                            ║
║  Dernière MAJ    : {etat['date_maj']}                                      ║
╚════════════════════════════════════════════════════════════════════════════╝
    """)


if __name__ == "__main__":
    main()