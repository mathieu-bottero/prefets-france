#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Base nationale des directeurs départementaux DDETS/DDPP/DDETSPP 
en poste — mise à jour hebdomadaire.

Organisation :
  - Départements > 400 000 hab : DDETS + DDPP (2 directeurs distincts)
  - Départements < 400 000 hab : DDETSPP (1 directeur fusionné)

Principe :
  1. Télécharge le flux XML des nominations du Journal Officiel
  2. Filtre les arrêtés concernant les DDETS/DDPP/DDETSPP
  3. Met à jour l'état persistant (etat_ddets_ddpp.json)
  4. Exporte en CSV (base_ddets_ddpp.csv)

Usage :
  Premier lancement (historique depuis création en 2021) :
      python3 maj_base_ddets_ddpp.py --mois 48 --init
  Mises à jour hebdomadaires :
      python3 maj_base_ddets_ddpp.py --mois 1
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

from poste_ddets_ddpp import (
    classifier_poste_ddets_ddpp,
    LIBELLES_TYPE,
    DEPARTEMENTS,
    POPULATION_DEPARTEMENTS,
    get_type_organisation,
    TERRITOIRES_ORGANISATION_SPECIFIQUE,
    MESSAGE_ORGANISATION_SPECIFIQUE,
    TERRITOIRES_SANS_DDETS,
)

URL_JO = "https://www.data.gouv.fr/api/1/datasets/r/1c5ac28d-92ca-4a19-aefb-63fbde4387a2"

_RACINE_SCRIPT = Path(__file__).resolve().parent
FICHIER_ETAT   = str(_RACINE_SCRIPT / "data" / "etat_ddets_ddpp.json")
FICHIER_CSV    = str(_RACINE_SCRIPT / "data" / "base_ddets_ddpp.csv")

CHUNK_SIZE = 4 * 1024 * 1024
NB_TENTATIVES = 5
DELAI_RETRY = 10

# Créer le dossier data s'il n'existe pas
os.makedirs(_RACINE_SCRIPT / "data", exist_ok=True)

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

def telecharger_evenements(nb_mois_arriere):
    """
    Parse le flux JO en streaming.
    Ne conserve que les nominations DDETS/DDPP/DDETSPP.
    """
    date_limite = datetime.now() - timedelta(days=nb_mois_arriere * 30)
    
    # Ne pas chercher avant la création des DDETS (1er avril 2021)
    date_creation_ddets = datetime(2020, 10, 1)
    if date_limite < date_creation_ddets:
        date_limite = date_creation_ddets
    
    print(f"\n📡 Connexion au flux JO (depuis le {date_limite.strftime('%d/%m/%Y')})...")

    MOTS_CLES = (
        "directeur départemental de l'emploi, du travail et des solidarités",
        "directrice départementale de l'emploi, du travail et des solidarités",
        "directeur départemental de l'emploi, du travail, des solidarités et de la protection",
        "directrice départementale de l'emploi, du travail, des solidarités et de la protection",
        "directeur départemental de la protection des populations",
        "directrice départementale de la protection des populations",
    )
    TYPES_RETENUS = {'nomination', 'renouvellement'}

    print("🔍 Parsing en streaming (pas de téléchargement complet)...")
    
    evenements = []
    total, retenus = 0, 0
    
    try:
        response = requests.get(URL_JO, stream=True, timeout=120)
        response.raise_for_status()
        response.raw.decode_content = True
        
        for event, elem in ET.iterparse(response.raw, events=('end',)):
            if elem.tag != 'result':
                continue

            total += 1
            
            if total % 100000 == 0:
                print(f"   📊 {total} nominations analysées, {retenus} DDETS/DDPP/DDETSPP retenues...")

            # Filtre date
            date_pub = parse_date(elem.get('source_date', ''))
            if not date_pub or date_pub < date_limite:
                elem.clear()
                continue

            # Filtre type_ordre
            if elem.get('type_ordre', '').lower() not in TYPES_RETENUS:
                elem.clear()
                continue

            # ── filtre textuel (chercher dans object ET person) ────
            obj = elem.find('object')
            person = elem.find('person')

            texte_objet = extraire_texte_concatene(obj, 'text') if obj is not None else ''
            texte_person = extraire_texte_concatene(person, 'text') if person is not None else ''
            texte_complet = f"{texte_objet} {texte_person}".lower()

            if not any(mot in texte_complet for mot in MOTS_CLES):
                elem.clear()
                continue

            # Extraction complète
            donnees = extraire_evenement(elem)

            # S'assurer que texte_poste contient le texte complet (objet + personne)
            if not donnees.get('texte_poste'):
                donnees['texte_poste'] = texte_objet
            if not donnees.get('texte_contexte'):
                donnees['texte_contexte'] = texte_person

            # Concaténer les deux pour classifier
            texte_complet_pour_classif = f"{donnees.get('texte_poste', '')} {donnees.get('texte_contexte', '')}"
            donnees['texte_complet_brut'] = texte_complet_pour_classif

            evenements.append(donnees)
            retenus += 1

            elem.clear()
        
        print(f"✅ {retenus} nominations DDETS/DDPP/DDETSPP retenues sur {total} analysées.\n")
        
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
        "departements": {},
        "source_id_traites": [],
        "date_maj": None,
        "statistiques": {
            "total_departements_ddets_ddpp": 0,
            "total_departements_ddetspp": 0,
            "total_directeurs_ddets": 0,
            "total_directeurs_ddpp": 0,
            "total_directeurs_ddetspp": 0
        }
    }

def sauvegarder_etat(etat):
    """Sauvegarde l'état persistant"""
    with open(FICHIER_ETAT, 'w', encoding='utf-8') as f:
        json.dump(etat, f, ensure_ascii=False, indent=2, default=str)

def cle_departement(territoire):
    """Génère une clé unique pour un département"""
    return territoire.strip()

def appliquer_evenements(etat, evenements):
    """Applique les événements à l'état"""
    aujourd_hui = datetime.now()
    deja_traites = set(etat.get('source_id_traites', []))
    nouveaux_traites = []

    # Trier par date
    def cle_tri(e):
        return e['date_effet'] or e['date_publication'] or datetime.min
    evenements_tries = sorted(evenements, key=cle_tri)

    print("📝 Application des événements...\n")
    modifications = 0

    for ev in evenements_tries:
        # Éviter les doublons
        if ev['source_id'] and ev['source_id'] in deja_traites:
            continue

        # Le libellé du poste peut être dans <object> ou dans <person>.
        # Il faut impérativement classifier le texte concaténé.
        texte = ev.get('texte_complet_brut') or " ".join(
            part for part in (
                ev.get('texte_poste', ''),
                ev.get('texte_contexte', '')
            )
            if part
        )

        resultat = classifier_poste_ddets_ddpp(texte)

        if not resultat:
            print(
                f"   ⚠️ Poste non classifié : "
                f"{ev['nom_complet']} [{ev['source_id']}]"
            )
            print(f"      {texte}")

            # Important : ne pas marquer l'arrêté comme traité.
            # Ainsi, il pourra être repris après une amélioration du classifieur.
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

        cle = cle_departement(territoire)
        
        # Initialiser le département s'il n'existe pas
        if cle not in etat['departements']:
            type_org = get_type_organisation(territoire)
            etat['departements'][cle] = {
                'territoire': territoire,
                'code_dept': DEPARTEMENTS.get(territoire, ''),
                'type_organisation': type_org,
                'population_estimee': POPULATION_DEPARTEMENTS.get(territoire, 0),
            }
            
            # Initialiser les postes selon le type d'organisation
            if type_org in ('ddets_ddpp_separees', 'organisation_locale_specifique'):
                etat['departements'][cle]['poste_ddets'] = {
                    'titulaire_actuel': None,
                    'titulaire_designe': None,
                    'historique': []
                }
                etat['departements'][cle]['poste_ddpp'] = {
                    'titulaire_actuel': None,
                    'titulaire_designe': None,
                    'historique': []
                }
            else:
                etat['departements'][cle]['poste_ddetspp'] = {
                    'titulaire_actuel': None,
                    'titulaire_designe': None,
                    'historique': []
                }

        dept = etat['departements'][cle]
        
        # Déterminer le poste concerné
        if type_poste == 'ddets':
            if 'poste_ddets' not in dept:
                dept['poste_ddets'] = {
                    'titulaire_actuel': None,
                    'titulaire_designe': None,
                    'historique': []
                }
            poste = dept['poste_ddets']
            libelle_poste = "DDETS"
        elif type_poste == 'ddpp':
            if 'poste_ddpp' not in dept:
                dept['poste_ddpp'] = {
                    'titulaire_actuel': None,
                    'titulaire_designe': None,
                    'historique': []
                }
            poste = dept['poste_ddpp']
            libelle_poste = "DDPP"
        else:  # ddetspp
            if 'poste_ddetspp' not in dept:
                dept['poste_ddetspp'] = {
                    'titulaire_actuel': None,
                    'titulaire_designe': None,
                    'historique': []
                }
            poste = dept['poste_ddetspp']
            libelle_poste = "DDETSPP"

        # Gestion des prises de poste
        if action in ACTIONS_PRISE_POSTE:
            est_future = bool(date_ref and date_ref > aujourd_hui)
            
            if est_future:
                poste['titulaire_designe'] = titulaire
                print(f"   🔜 {territoire} ({libelle_poste}) : {ev['nom_complet']} (désigné pour le {date_ref.strftime('%d/%m/%Y')})")
            else:
                if poste['titulaire_actuel']:
                    poste['historique'].append({
                        **poste['titulaire_actuel'],
                        'action': 'remplacé',
                        'date_fin': date_ref.strftime('%d/%m/%Y') if date_ref else ''
                    })
                poste['titulaire_actuel'] = titulaire
                poste['titulaire_designe'] = None
                print(f"   ✅ {territoire} ({libelle_poste}) : {ev['nom_complet']} (depuis le {date_ref.strftime('%d/%m/%Y')})")
                modifications += 1

        # Gestion des départs
        elif action in ACTIONS_DEPART:
            if poste['titulaire_actuel']:
                poste['historique'].append({
                    **poste['titulaire_actuel'],
                    'action': 'cessation de fonction',
                    'date_fin': date_ref.strftime('%d/%m/%Y') if date_ref else ''
                })
                print(f"   ⏹️  {territoire} ({libelle_poste}) : {poste['titulaire_actuel']['nom_complet']} (fin de fonction)")
                poste['titulaire_actuel'] = None
                modifications += 1

        nouveaux_traites.append(ev['source_id'])

    # Promouvoir les désignations futures devenues effectives
    for cle, dept in etat['departements'].items():
        for cle_poste in ['poste_ddets', 'poste_ddpp', 'poste_ddetspp']:
            if cle_poste not in dept:
                continue
            
            poste = dept[cle_poste]
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
                        print(f"   🔄 {dept['territoire']} ({cle_poste.replace('poste_', '').upper()}) : {desig['nom_complet']} (promotion automatique)")
                        modifications += 1
                except ValueError:
                    pass

    etat['source_id_traites'] = list(deja_traites | set(nouveaux_traites))
    etat['date_maj'] = aujourd_hui.strftime('%d/%m/%Y %H:%M')
    
    # Mettre à jour les statistiques
    stats = etat['statistiques']
    stats['total_departements_ddets_ddpp'] = sum(
        1 for d in etat['departements'].values() 
        if d.get('type_organisation') == 'ddets_ddpp_separees'
    )
    stats['total_departements_ddetspp'] = sum(
        1 for d in etat['departements'].values() 
        if d.get('type_organisation') == 'ddetspp_fusionnee'
    )
    stats['total_directeurs_ddets'] = sum(
        1 for d in etat['departements'].values() 
        if d.get('poste_ddets', {}).get('titulaire_actuel')
    )
    stats['total_directeurs_ddpp'] = sum(
        1 for d in etat['departements'].values() 
        if d.get('poste_ddpp', {}).get('titulaire_actuel')
    )
    stats['total_directeurs_ddetspp'] = sum(
        1 for d in etat['departements'].values() 
        if d.get('poste_ddetspp', {}).get('titulaire_actuel')
    )
    
    print(f"\n✅ {modifications} modifications appliquées")
    return etat

# ---------------------------------------------------------------------------
# 3. Export CSV
# ---------------------------------------------------------------------------

def exporter_csv(etat):
    """Exporte l'état en CSV lisible (une ligne par département)"""
    colonnes = [
        'departement',
        'territoire',
        'type_organisation',
        'population_estimee',
        
        # DDETS
        'directeur_ddets_nom_complet',
        'directeur_ddets_sexe',
        'directeur_ddets_grade',
        'directeur_ddets_date_decision',
        'directeur_ddets_date_prise_fonction',
        'directeur_ddets_anciennete_jours',
        'directeur_ddets_designe_nom',
        'directeur_ddets_designe_date',
        
        # DDPP
        'directeur_ddpp_nom_complet',
        'directeur_ddpp_sexe',
        'directeur_ddpp_grade',
        'directeur_ddpp_date_decision',
        'directeur_ddpp_date_prise_fonction',
        'directeur_ddpp_anciennete_jours',
        'directeur_ddpp_designe_nom',
        'directeur_ddpp_designe_date',
        
        # DDETSPP
        'directeur_ddetspp_nom_complet',
        'directeur_ddetspp_sexe',
        'directeur_ddetspp_grade',
        'directeur_ddetspp_date_decision',
        'directeur_ddetspp_date_prise_fonction',
        'directeur_ddetspp_anciennete_jours',
        'directeur_ddetspp_designe_nom',
        'directeur_ddetspp_designe_date',
        
        'statut',
        'message',
    ]

    lignes = []

    for dept in etat['departements'].values():
        ligne = {
            'departement': dept.get('code_dept', ''),
            'territoire': dept['territoire'],
            'type_organisation': dept.get('type_organisation', ''),
            'population_estimee': dept.get('population_estimee', ''),
            'statut': '',
            'message': '',
        }
        
        # Fonction helper pour calculer l'ancienneté
        def calculer_anciennete(date_str):
            if not date_str:
                return ''
            try:
                d = datetime.strptime(date_str, '%d/%m/%Y')
                return (datetime.now() - d).days
            except ValueError:
                return ''
        
        # DDETS
        poste_ddets = dept.get('poste_ddets', {})
        ta_ddets = poste_ddets.get('titulaire_actuel') or {}
        td_ddets = poste_ddets.get('titulaire_designe') or {}
        
        ligne['directeur_ddets_nom_complet'] = ta_ddets.get('nom_complet', '')
        ligne['directeur_ddets_sexe'] = ta_ddets.get('sexe', '')
        ligne['directeur_ddets_grade'] = ta_ddets.get('grade', '')
        ligne['directeur_ddets_date_decision'] = ta_ddets.get('date_decision', '')
        ligne['directeur_ddets_date_prise_fonction'] = ta_ddets.get('date_prise_fonction', '')
        ligne['directeur_ddets_anciennete_jours'] = calculer_anciennete(ta_ddets.get('date_prise_fonction', ''))
        ligne['directeur_ddets_designe_nom'] = td_ddets.get('nom_complet', '')
        ligne['directeur_ddets_designe_date'] = td_ddets.get('date_prise_fonction', '')
        
        # DDPP
        poste_ddpp = dept.get('poste_ddpp', {})
        ta_ddpp = poste_ddpp.get('titulaire_actuel') or {}
        td_ddpp = poste_ddpp.get('titulaire_designe') or {}
        
        ligne['directeur_ddpp_nom_complet'] = ta_ddpp.get('nom_complet', '')
        ligne['directeur_ddpp_sexe'] = ta_ddpp.get('sexe', '')
        ligne['directeur_ddpp_grade'] = ta_ddpp.get('grade', '')
        ligne['directeur_ddpp_date_decision'] = ta_ddpp.get('date_decision', '')
        ligne['directeur_ddpp_date_prise_fonction'] = ta_ddpp.get('date_prise_fonction', '')
        ligne['directeur_ddpp_anciennete_jours'] = calculer_anciennete(ta_ddpp.get('date_prise_fonction', ''))
        ligne['directeur_ddpp_designe_nom'] = td_ddpp.get('nom_complet', '')
        ligne['directeur_ddpp_designe_date'] = td_ddpp.get('date_prise_fonction', '')
        
        # DDETSPP
        poste_ddetspp = dept.get('poste_ddetspp', {})
        ta_ddetspp = poste_ddetspp.get('titulaire_actuel') or {}
        td_ddetspp = poste_ddetspp.get('titulaire_designe') or {}
        
        ligne['directeur_ddetspp_nom_complet'] = ta_ddetspp.get('nom_complet', '')
        ligne['directeur_ddetspp_sexe'] = ta_ddetspp.get('sexe', '')
        ligne['directeur_ddetspp_grade'] = ta_ddetspp.get('grade', '')
        ligne['directeur_ddetspp_date_decision'] = ta_ddetspp.get('date_decision', '')
        ligne['directeur_ddetspp_date_prise_fonction'] = ta_ddetspp.get('date_prise_fonction', '')
        ligne['directeur_ddetspp_anciennete_jours'] = calculer_anciennete(ta_ddetspp.get('date_prise_fonction', ''))
        ligne['directeur_ddetspp_designe_nom'] = td_ddetspp.get('nom_complet', '')
        ligne['directeur_ddetspp_designe_date'] = td_ddetspp.get('date_prise_fonction', '')
        
        # Statut
        type_org = dept.get('type_organisation')
        territoire = dept.get('territoire', '')

        if type_org == 'organisation_locale_specifique':
            # Aucun poste DDETS ne doit être qualifié de vacant dans ces territoires.
            ligne['message'] = TERRITOIRES_SANS_DDETS.get(
                territoire,
                "Pas de DDETS : organisation locale spécifique."
            )

            if ta_ddpp:
                ligne['statut'] = 'DDPP recensée — pas de DDETS'
            else:
                ligne['statut'] = 'Pas de DDETS : organisation locale spécifique'

        elif type_org == 'ddets_ddpp_separees':
            if ta_ddets and ta_ddpp:
                ligne['statut'] = 'postes DDETS et DDPP recensés'
            elif ta_ddets or ta_ddpp:
                ligne['statut'] = 'un poste recensé, un poste vacant'
            else:
                ligne['statut'] = 'postes vacants ou inconnus'

        else:
            if ta_ddetspp:
                ligne['statut'] = 'poste DDETSPP recensé'
            else:
                ligne['statut'] = 'poste vacant ou inconnu'
        
        lignes.append(ligne)

    # Ajouter les territoires avec organisation spécifique
    territoires_deja_exportes = {
        dept.get('territoire', '').strip()
        for dept in etat['departements'].values()
    }

    for territoire, code_dept in TERRITOIRES_ORGANISATION_SPECIFIQUE.items():
        if territoire not in territoires_deja_exportes:
            ligne = {col: '' for col in colonnes}
            ligne['departement'] = code_dept
            ligne['territoire'] = territoire
            ligne['statut'] = 'organisation spécifique'
            ligne['message'] = MESSAGE_ORGANISATION_SPECIFIQUE
            lignes.append(ligne)
    
    # Tri par département
    lignes.sort(key=lambda x: x['departement'])

    with open(FICHIER_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=colonnes, delimiter=';')
        writer.writeheader()
        writer.writerows(lignes)

    print(f"\n💾 Export CSV : {FICHIER_CSV} ({len(lignes)} départements)")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Met à jour la base nationale des DDETS/DDPP/DDETSPP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python3 maj_base_ddets_ddpp.py --mois 48 --init    # Premier lancement
  python3 maj_base_ddets_ddpp.py --mois 1            # Mise à jour hebdomadaire
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
║         BASE NATIONALE DDETS/DDPP/DDETSPP - MISE À JOUR                    ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝
    """)

    # Supprimer l'état si --init
    if args.init and os.path.exists(FICHIER_ETAT):
        os.remove(FICHIER_ETAT)
        print("🗑️  État précédent supprimé (mode --init)\n")

    # Charger l'état
    etat = charger_etat()
    
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
║ STATISTIQUES                                                               ║
╠════════════════════════════════════════════════════════════════════════════╣
║  Départements DDETS+DDPP : {stats['total_departements_ddets_ddpp']:3d}                                  ║
║  Départements DDETSPP    : {stats['total_departements_ddetspp']:3d}                                  ║
║                                                                            ║
║  Directeurs DDETS        : {stats['total_directeurs_ddets']:3d}                                  ║
║  Directeurs DDPP         : {stats['total_directeurs_ddpp']:3d}                                  ║
║  Directeurs DDETSPP      : {stats['total_directeurs_ddetspp']:3d}                                  ║
║                                                                            ║
║  Dernière MAJ            : {etat['date_maj']}                              ║
╚════════════════════════════════════════════════════════════════════════════╝
    """)

if __name__ == "__main__":
    main()