#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Base nationale des directeurs départementaux des territoires (DDT/DDTM) 
en poste — mise à jour hebdomadaire.

Principe :
  1. Télécharge le flux XML des nominations du Journal Officiel
  2. Filtre les arrêtés concernant les DDT/DDTM
  3. Met à jour l'état persistant (etat_ddt.json)
  4. Exporte en CSV (base_ddt.csv)

Usage :
  Premier lancement (historique) :
      python3 maj_base_ddt.py --mois 48 --init
  Mises à jour hebdomadaires :
      python3 maj_base_ddt.py --mois 1
"""

import requests
import xml.etree.ElementTree as ET
import csv
import json
import time
import argparse
import os
from datetime import datetime, timedelta
from pathlib import Path
from urllib3.exceptions import ProtocolError, IncompleteRead as Urllib3IncompleteRead
from http.client import IncompleteRead as HttpIncompleteRead

from poste_ddt import classifier_poste_ddt, LIBELLES_TYPE

URL_JO = "https://www.data.gouv.fr/api/1/datasets/r/1c5ac28d-92ca-4a19-aefb-63fbde4387a2"


_RACINE_SCRIPT = Path(__file__).resolve().parent   # = .../prefets/
FICHIER_ETAT   = str(_RACINE_SCRIPT / "data" / "etat_ddt.json")
FICHIER_CSV    = str(_RACINE_SCRIPT / "data" / "base_ddt.csv")

FICHIER_XML_CACHE = str(_RACINE_SCRIPT / "data" / "jo_flux_cache.xml")

CHUNK_SIZE = 4 * 1024 * 1024   # 4 Mo par batch
NB_TENTATIVES = 5
DELAI_RETRY = 10

# Créer le dossier data s'il n'existe pas
os.makedirs("ddt/data", exist_ok=True)

# ---------------------------------------------------------------------------
# 1. Téléchargement et extraction
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
    """Extrait les données pertinentes d'un result XML"""
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

def telecharger_fichier_avec_reprise(url, chemin_local):
    """
    Télécharge un fichier volumineux par chunks de 4 Mo.
    Reprend automatiquement là où il s'est arrêté si le fichier
    existe déjà partiellement (header HTTP Range).
    """
    chemin = Path(chemin_local)
    chemin.parent.mkdir(parents=True, exist_ok=True)

    # Taille déjà téléchargée (reprise)
    debut = chemin.stat().st_size if chemin.exists() else 0

    if debut > 0:
        print(f"   ↩️  Reprise du téléchargement à partir de {debut / 1024**2:.1f} Mo...")

    for tentative in range(1, NB_TENTATIVES + 1):
        try:
            headers = {"Range": f"bytes={debut}-"} if debut > 0 else {}
            response = requests.get(url, headers=headers, stream=True, timeout=60)

            # 206 = Partial Content (reprise OK), 200 = début normal
            if response.status_code not in (200, 206):
                raise requests.exceptions.HTTPError(
                    f"Statut HTTP inattendu : {response.status_code}"
                )

            # Si le serveur ne supporte pas Range et renvoie 200,
            # on repart de zéro pour éviter un fichier corrompu.
            if response.status_code == 200 and debut > 0:
                print("   ⚠️  Le serveur ne supporte pas la reprise — redémarrage complet.")
                debut = 0
                chemin.unlink(missing_ok=True)

            mode = "ab" if debut > 0 else "wb"
            taille_totale = int(response.headers.get("Content-Length", 0)) + debut

            print(f"   📥 Téléchargement en cours "
                  f"({'reprise' if debut > 0 else 'démarrage'}, "
                  f"taille totale estimée : {taille_totale / 1024**2:.0f} Mo)...")

            with open(chemin, mode) as f:
                telecharge = debut
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
                        telecharge += len(chunk)
                        pct = (telecharge / taille_totale * 100) if taille_totale else 0
                        print(f"\r   {telecharge / 1024**2:.0f} Mo "
                              f"/ {taille_totale / 1024**2:.0f} Mo "
                              f"({pct:.1f} %)", end="", flush=True)

            print(f"\n   ✅ Téléchargement terminé : {telecharge / 1024**2:.0f} Mo")
            return  # succès

        except (
            ProtocolError,
            Urllib3IncompleteRead,
            HttpIncompleteRead,
            requests.exceptions.ChunkedEncodingError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as e:
            # Met à jour la position de reprise pour la prochaine tentative
            debut = chemin.stat().st_size if chemin.exists() else 0
            print(f"\n   ⚠️  Coupure réseau (tentative {tentative}/{NB_TENTATIVES}) "
                  f"après {debut / 1024**2:.1f} Mo : {e}")

            if tentative < NB_TENTATIVES:
                print(f"   ⏳ Nouvelle tentative dans {DELAI_RETRY}s...")
                time.sleep(DELAI_RETRY)
            else:
                print(f"\n   ❌ Échec après {NB_TENTATIVES} tentatives. "
                      f"Fichier partiel conservé pour la prochaine exécution.")
                raise  # On propage uniquement si toutes les tentatives ont échoué


def telecharger_evenements(nb_mois_arriere):
    """
    Parse le flux JO en streaming (sans télécharger le fichier complet).
    Ne conserve que les nominations DDT/DDTM.
    """
    date_limite = datetime.now() - timedelta(days=nb_mois_arriere * 30)
    print(f"\n📡 Connexion au flux JO (depuis le {date_limite.strftime('%d/%m/%Y')})...")

    MOTS_CLES = (
        'directeur départemental des territoires',
        'directrice départementale des territoires',
    )
    TYPES_RETENUS = {'nomination', 'renouvellement'}

    # ── Streaming direct depuis l'API ────────────────────────────────────
    print("🔍 Parsing en streaming (pas de téléchargement complet)...")
    
    evenements = []
    total, retenus = 0, 0
    
    try:
        response = requests.get(URL_JO, stream=True, timeout=120)
        response.raise_for_status()
        response.raw.decode_content = True
        
        # Parse XML au fur et à mesure (sans charger en mémoire)
        for event, elem in ET.iterparse(response.raw, events=('end',)):
            if elem.tag != 'result':
                continue

            total += 1
            
            # Afficher la progression tous les 100000 éléments
            if total % 100000 == 0:
                print(f"   📊 {total} nominations analysées, {retenus} DDT/DDTM retenues...")

            # ── filtre date ──────────────────────────────────────────────
            date_pub = parse_date(elem.get('source_date', ''))
            if not date_pub or date_pub < date_limite:
                elem.clear()
                continue

            # ── filtre type_ordre ────────────────────────────────────────
            if elem.get('type_ordre', '').lower() not in TYPES_RETENUS:
                elem.clear()
                continue

            # ── filtre textuel DDT (AVANT d'extraire tout le contenu) ────
            obj = elem.find('object')
            texte_poste = extraire_texte_concatene(obj, 'text') if obj is not None else ''
            if not any(mot in texte_poste.lower() for mot in MOTS_CLES):
                elem.clear()
                continue

            # ── extraction complète SEULEMENT si c'est un DDT/DDTM ───────
            donnees = extraire_evenement(elem)
            if not donnees.get('texte_poste'):
                donnees['texte_poste'] = texte_poste

            evenements.append(donnees)
            retenus += 1

            elem.clear()  # Libérer la mémoire
        
        print(f"✅ {retenus} nominations DDT/DDTM retenues sur {total} analysées.\n")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur de connexion : {e}")
        raise

    return evenements

# ---------------------------------------------------------------------------
# 2. Mise à jour de l'état persistant
# ---------------------------------------------------------------------------

ACTIONS_PRISE_POSTE = {'nomination', 'renouvellement'}
ACTIONS_DEPART = {'cessation de fonction', 'fin de détachement'}

def charger_etat():
    """Charge l'état persistant ou crée un nouvel état"""
    if os.path.exists(FICHIER_ETAT):
        with open(FICHIER_ETAT, encoding='utf-8') as f:
            return json.load(f)
    return {
        "postes": {},
        "source_id_traites": [],
        "date_maj": None,
        "statistiques": {
            "total_ddt": 0,
            "total_ddtm": 0
        }
    }

def sauvegarder_etat(etat):
    """Sauvegarde l'état persistant"""
    with open(FICHIER_ETAT, 'w', encoding='utf-8') as f:
        json.dump(etat, f, ensure_ascii=False, indent=2, default=str)

def cle_poste(type_poste, territoire):
    """
    Génère une clé unique pour un poste.

    Le type DDT/DDTM n'est volontairement pas dans la clé :
    une préfecture peut changer d'organisation (DDTM -> DDT)
    sans qu'il s'agisse d'un nouveau poste.
    """
    return territoire.strip()
    
    
def date_titulaire(poste):
    """Retourne une date comparable pour identifier l'état le plus récent."""
    titulaire = poste.get('titulaire_actuel') or poste.get('titulaire_designe') or {}
    valeur = titulaire.get('date_prise_fonction', '')

    try:
        return datetime.strptime(valeur, '%d/%m/%Y')
    except (TypeError, ValueError):
        return datetime.min


def migrer_postes_doublons(etat):
    """
    Fusionne les anciens postes ayant le même territoire mais des types
    différents, par exemple :
      ddtm|Corse-du-Sud
      ddt|Corse-du-Sud

    Le poste ayant la prise de fonction la plus récente est conservé.
    """
    groupes = {}

    for ancienne_cle, poste in etat.get('postes', {}).items():
        territoire = poste.get('territoire', '').strip()
        if territoire:
            groupes.setdefault(territoire, []).append((ancienne_cle, poste))

    postes_migres = {}
    nb_fusions = 0

    for territoire, elements in groupes.items():
        # Le plus récent devient le poste courant de référence.
        elements.sort(key=lambda item: date_titulaire(item[1]), reverse=True)

        cle_gagnante, poste_gagnant = elements[0]
        nouvelle_cle = cle_poste(
            poste_gagnant.get('type', ''),
            territoire
        )

        poste_gagnant.setdefault('historique', [])

        # Les autres versions du même poste rejoignent l'historique.
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
                        'action': 'ancien type de poste',
                        'date_fin': (
                            (poste_gagnant.get('titulaire_actuel') or {})
                            .get('date_prise_fonction', '')
                        )
                    })

        postes_migres[nouvelle_cle] = poste_gagnant

    etat['postes'] = postes_migres

    if nb_fusions:
        print(f"🔧 Migration : {nb_fusions} ancien(s) poste(s) DDT/DDTM fusionné(s).")

    return etat

def appliquer_evenements(etat, evenements):
    """Applique les événements à l'état"""
    aujourd_hui = datetime.now()
    deja_traites = set(etat.get('source_id_traites', []))
    nouveaux_traites = []

    # Trier par date (effet puis publication)
    def cle_tri(e):
        return e['date_effet'] or e['date_publication'] or datetime.min
    evenements_tries = sorted(evenements, key=cle_tri)

    print("📝 Application des événements...\n")
    modifications = 0

    for ev in evenements_tries:
        # Éviter les doublons
        if ev['source_id'] and ev['source_id'] in deja_traites:
            continue

        # Parser le poste
        texte = ev['texte_poste'] or ev['texte_contexte']
        resultat = classifier_poste_ddt(texte)
        
        if not resultat:
            nouveaux_traites.append(ev['source_id'])
            continue

        type_poste, territoire, grade = resultat
        action = ev['type_decision']

        date_ref = ev['date_effet'] or ev['date_publication']
        
        titulaire = {
            'nom_complet': ev['nom_complet'],
            'nom': ev['nom'],
            'prenom': ev['prenom'],
            'sexe': ev['sexe'],
            'grade': grade,
            'date_decision': ev['date_publication'].strftime('%d/%m/%Y') if ev['date_publication'] else '',
            'date_prise_fonction': date_ref.strftime('%d/%m/%Y') if date_ref else '',
            'source_id': ev['source_id'],
            'texte_source': texte,
        }

        cle = cle_poste(type_poste, territoire)
        
        # Initialiser le poste s'il n'existe pas
        if cle not in etat['postes']:
            etat['postes'][cle] = {
                'type': type_poste,
                'type_libelle': LIBELLES_TYPE.get(type_poste, type_poste),
                'territoire': territoire,
                'titulaire_actuel': None,
                'titulaire_designe': None,
                'historique': [],
            }

        poste = etat['postes'][cle]
        
        # Le territoire peut changer d'organisation :
        # DDTM -> DDT ou, plus rarement, DDT -> DDTM.
        # On garde le même poste mais on actualise son type.
        poste['type'] = type_poste
        poste['type_libelle'] = LIBELLES_TYPE.get(type_poste, type_poste)

        # Gestion des prises de poste
        if action in ACTIONS_PRISE_POSTE:
            est_future = bool(date_ref and date_ref > aujourd_hui)
            
            if est_future:
                poste['titulaire_designe'] = titulaire
                print(f"   🔜 {territoire} : {ev['nom_complet']} (désigné pour le {date_ref.strftime('%d/%m/%Y')})")
            else:
                if poste['titulaire_actuel']:
                    poste['historique'].append({
                        **poste['titulaire_actuel'],
                        'action': 'remplacé',
                        'date_fin': date_ref.strftime('%d/%m/%Y') if date_ref else ''
                    })
                poste['titulaire_actuel'] = titulaire
                poste['titulaire_designe'] = None
                print(f"   ✅ {territoire} : {ev['nom_complet']} (depuis le {date_ref.strftime('%d/%m/%Y')})")
                modifications += 1

        # Gestion des départs
        elif action in ACTIONS_DEPART:
            if poste['titulaire_actuel']:
                poste['historique'].append({
                    **poste['titulaire_actuel'],
                    'action': 'cessation de fonction',
                    'date_fin': date_ref.strftime('%d/%m/%Y') if date_ref else ''
                })
                print(f"   ⏹️  {territoire} : {poste['titulaire_actuel']['nom_complet']} (fin de fonction)")
                poste['titulaire_actuel'] = None
                modifications += 1

        nouveaux_traites.append(ev['source_id'])

    # Promouvoir les désignations futures devenues effectives
    for cle, poste in etat['postes'].items():
        desig = poste.get('titulaire_designe')
        if desig and desig.get('date_prise_fonction'):
            try:
                d = datetime.strptime(desig['date_prise_fonction'], '%d/%m/%Y')
                if d <= aujourd_hui:
                    if poste['titulaire_actuel']:
                        poste['historique'].append({
                            **poste['titulaire_actuel'],
                            'action': 'remplacé',
                            'date_fin': d.strftime('%d/%m/%Y')
                        })
                    poste['titulaire_actuel'] = desig
                    poste['titulaire_designe'] = None
                    print(f"   🔄 {poste['territoire']} : {desig['nom_complet']} (promotion automatique)")
                    modifications += 1
            except ValueError:
                pass

    etat['source_id_traites'] = list(deja_traites | set(nouveaux_traites))
    etat['date_maj'] = aujourd_hui.strftime('%d/%m/%Y %H:%M')
    
    # Mettre à jour les statistiques
    etat['statistiques']['total_ddt'] = sum(1 for p in etat['postes'].values() 
                                             if p['type'] == 'ddt' and p['titulaire_actuel'])
    etat['statistiques']['total_ddtm'] = sum(1 for p in etat['postes'].values() 
                                              if p['type'] == 'ddtm' and p['titulaire_actuel'])
    
    print(f"\n✅ {modifications} modifications appliquées")
    return etat

# ---------------------------------------------------------------------------
# 3. Export CSV
# ---------------------------------------------------------------------------

DEPARTEMENTS = {
    "Ain": "01", "Aisne": "02", "Allier": "03", "Alpes-de-Haute-Provence": "04",
    "Hautes-Alpes": "05", "Alpes-Maritimes": "06", "Ardèche": "07", "Ardennes": "08",
    "Ariège": "09", "Aube": "10", "Aude": "11", "Aveyron": "12", "Bouches-du-Rhône": "13",
    "Calvados": "14", "Cantal": "15", "Charente": "16", "Charente-Maritime": "17",
    "Cher": "18", "Corrèze": "19", "Corse-du-Sud": "2A", "Haute-Corse": "2B",
    "Côte-d'Or": "21", "Côtes-d'Armor": "22", "Creuse": "23", "Dordogne": "24",
    "Doubs": "25", "Drôme": "26", "Eure": "27", "Eure-et-Loir": "28", "Finistère": "29",
    "Gard": "30", "Haute-Garonne": "31", "Gers": "32", "Gironde": "33", "Hérault": "34",
    "Ille-et-Vilaine": "35", "Indre": "36", "Indre-et-Loire": "37", "Isère": "38",
    "Jura": "39", "Landes": "40", "Loir-et-Cher": "41", "Loire": "42", "Haute-Loire": "43",
    "Loire-Atlantique": "44", "Loiret": "45", "Lot": "46", "Lot-et-Garonne": "47",
    "Lozère": "48", "Maine-et-Loire": "49", "Manche": "50", "Marne": "51",
    "Haute-Marne": "52", "Mayenne": "53", "Meurthe-et-Moselle": "54", "Meuse": "55",
    "Morbihan": "56", "Moselle": "57", "Nièvre": "58", "Nord": "59", "Oise": "60",
    "Orne": "61", "Pas-de-Calais": "62", "Puy-de-Dôme": "63", "Pyrénées-Atlantiques": "64",
    "Hautes-Pyrénées": "65", "Pyrénées-Orientales": "66", "Bas-Rhin": "67",
    "Haut-Rhin": "68", "Rhône": "69", "Haute-Saône": "70", "Saône-et-Loire": "71",
    "Sarthe": "72", "Savoie": "73", "Haute-Savoie": "74", "Paris": "75",
    "Seine-Maritime": "76", "Seine-et-Marne": "77", "Yvelines": "78", "Deux-Sèvres": "79",
    "Somme": "80", "Tarn": "81", "Tarn-et-Garonne": "82", "Var": "83", "Vaucluse": "84",
    "Vendée": "85", "Vienne": "86", "Haute-Vienne": "87", "Vosges": "88", "Yonne": "89",
    "Territoire de Belfort": "90", "Essonne": "91", "Hauts-de-Seine": "92",
    "Seine-Saint-Denis": "93", "Val-de-Marne": "94", "Val-d'Oise": "95",
    "Guadeloupe": "971", "Martinique": "972", "Guyane": "973", "Réunion": "974",
    "Mayotte": "976", "Saint-Pierre-et-Miquelon": "975",
}


# Territoires ne disposant pas d'une DDT/DDTM au sens du flux étudié.
# Une ligne informative sera ajoutée au CSV si aucun poste réel n'est trouvé.
TERRITOIRES_SANS_DDT_DDTM = {
    "Paris": "75",
    "Hauts-de-Seine": "92",
    "Seine-Saint-Denis": "93",
    "Val-de-Marne": "94",
    "Guadeloupe": "971",
    "Martinique": "972",
    "Guyane": "973",
    "Réunion": "974",
    "Saint-Pierre-et-Miquelon": "975",
    "Mayotte": "976",
}

MESSAGE_SANS_DDT_DDTM = (
    "Pas de DDT/DDTM : organisation territoriale spécifique"
)

def exporter_csv(etat):
    """Exporte l'état en CSV lisible"""
    colonnes = [
        'departement',
        'territoire',
        'type_poste',
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
        'message',
    ]

    lignes = []

    for poste in etat['postes'].values():
        ta = poste.get('titulaire_actuel') or {}
        td = poste.get('titulaire_designe') or {}

        code_dept = DEPARTEMENTS.get(poste['territoire'], '')

        # Calculer l'ancienneté
        anciennete_jours = ''
        date_pf = ta.get('date_prise_fonction', '')
        if date_pf:
            try:
                d = datetime.strptime(date_pf, '%d/%m/%Y')
                anciennete_jours = (datetime.now() - d).days
            except ValueError:
                pass

        lignes.append({
            'departement': code_dept,
            'territoire': poste['territoire'],
            'type_poste': poste['type_libelle'],
            'titulaire_actuel_nom_complet': ta.get('nom_complet', ''),
            'titulaire_actuel_sexe': ta.get('sexe', ''),
            'grade': ta.get('grade', ''),
            'date_decision': ta.get('date_decision', ''),
            'date_prise_fonction': ta.get('date_prise_fonction', ''),
            'anciennete_jours': anciennete_jours,
            'titulaire_designe_nom_complet': td.get('nom_complet', ''),
            'titulaire_designe_date_prise_fonction': td.get('date_prise_fonction', ''),
            'texte_source': ta.get('texte_source', ''),
            'statut': 'poste recensé' if ta else 'poste vacant ou inconnu',
            'message': '',
        })


    # Ajouter les territoires sans DDT/DDTM lorsque le flux n'a fourni
    # aucun poste réel pour eux.
    territoires_deja_exportes = {
        poste.get('territoire', '').strip()
        for poste in etat['postes'].values()
    }

    for territoire, code_dept in TERRITOIRES_SANS_DDT_DDTM.items():
        if territoire not in territoires_deja_exportes:
            lignes.append({
                'departement': code_dept,
                'territoire': territoire,
                'type_poste': '',
                'titulaire_actuel_nom_complet': '',
                'titulaire_actuel_sexe': '',
                'grade': '',
                'date_decision': '',
                'date_prise_fonction': '',
                'anciennete_jours': '',
                'titulaire_designe_nom_complet': '',
                'titulaire_designe_date_prise_fonction': '',
                'texte_source': '',
                'statut': 'non concerné par une DDT/DDTM',
                'message': MESSAGE_SANS_DDT_DDTM,
            })
            
    # Tri par département
    lignes.sort(key=lambda x: x['departement'])

    with open(FICHIER_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=colonnes, delimiter=';')
        writer.writeheader()
        writer.writerows(lignes)

    print(f"\n💾 Export CSV : {FICHIER_CSV} ({len(lignes)} postes)")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Met à jour la base nationale des DDT/DDTM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python3 maj_base_ddt.py --mois 48 --init    # Premier lancement (4 ans d'historique)
  python3 maj_base_ddt.py --mois 1            # Mise à jour hebdomadaire
        """
    )
    parser.add_argument('--mois', type=int, default=1, 
                        help="Fenêtre de recherche en mois (défaut: 1)")
    parser.add_argument('--init', action='store_true', 
                        help="Repart d'un état vide (premier lancement uniquement)")
    args = parser.parse_args()

    print("""
╔════════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║              BASE NATIONALE DDT/DDTM - MISE À JOUR                         ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝
    """)

    # Supprimer l'état si --init
    if args.init and os.path.exists(FICHIER_ETAT):
        os.remove(FICHIER_ETAT)
        print("🗑️  État précédent supprimé (mode --init)\n")

    # Charger l'état
    etat = charger_etat()
    
    # Corrige les clés de l'ancien modèle : type|territoire.
    etat = migrer_postes_doublons(etat)
    
    # Télécharger les événements
    evenements = telecharger_evenements(args.mois)
    
    # Appliquer les événements
    etat = appliquer_evenements(etat, evenements)
    
    # Sauvegarder
    sauvegarder_etat(etat)
    print(f"💾 État sauvegardé : {FICHIER_ETAT}")
    
    # Exporter CSV
    exporter_csv(etat)
    
    # Statistiques finales
    stats = etat['statistiques']
    print(f"""
╔════════════════════════════════════════════════════════════════════════════╗
║STATISTIQUES                                                                ║
╠════════════════════════════════════════════════════════════════════════════╣
║  DDT en poste  : {stats['total_ddt']:3d}                                   ║
║  DDTM en poste : {stats['total_ddtm']:3d}                                  ║
║  TOTAL         : {stats['total_ddt'] + stats['total_ddtm']:3d}             ║
║                                                                            ║
║  Dernière MAJ  : {etat['date_maj']}                                        ║
╚════════════════════════════════════════════════════════════════════════════╝
    """)

if __name__ == "__main__":
    main()