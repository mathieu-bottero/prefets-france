#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script pour convertir le XML du Journal Officiel en CSV propre
avec filtre temporel et parsing en streaming optimisé
"""

import requests
import xml.etree.ElementTree as ET
import csv
from datetime import datetime, timedelta
import argparse

def formater_date(date_str):
    """Formate une date ISO en format français"""
    if not date_str or not date_str.strip():
        return ""
    try:
        date = datetime.strptime(date_str[:10], '%Y-%m-%d')
        return date.strftime('%d/%m/%Y')
    except:
        return date_str

def parse_date(date_str):
    """Convertit une date ISO en objet datetime"""
    if not date_str or not date_str.strip():
        return None
    try:
        return datetime.strptime(date_str[:10], '%Y-%m-%d')
    except:
        return None

def extraire_texte_concatene(element, tag):
    """Extrait et concatène tous les textes d'un tag"""
    if element is None:
        return ""
    textes = [e.text.strip() for e in element.findall(tag) if e.text and e.text.strip()]
    return " | ".join(textes) if textes else ""

def extraire_donnees_result(result):
    """Extrait toutes les données importantes d'un result"""
    
    donnees = {}
    
    # Informations générales
    donnees['type_decision'] = result.get('type_ordre', '')
    donnees['date_publication'] = formater_date(result.get('source_date', ''))
    donnees['date_effet'] = formater_date(result.get('date_debut', ''))
    donnees['source'] = result.get('source_name', '')
    donnees['source_id'] = result.get('source_id', '')
    
    # Personne concernée
    person = result.find('person')
    if person is not None:
        name = person.find('name')
        if name is not None:
            donnees['nom'] = name.get('nom', '').upper()
            donnees['prenom'] = name.get('prenom', '').title()
            donnees['nom_complet'] = name.text.strip() if name.text else f"{donnees['prenom']} {donnees['nom']}"
        else:
            donnees['nom'] = ''
            donnees['prenom'] = ''
            donnees['nom_complet'] = ''
        
        donnees['fonction_actuelle'] = extraire_texte_concatene(person, 'text')
        donnees['sexe'] = person.get('sexe', result.get('sexe', ''))
    else:
        donnees['nom'] = ''
        donnees['prenom'] = ''
        donnees['nom_complet'] = ''
        donnees['fonction_actuelle'] = ''
        donnees['sexe'] = result.get('sexe', '')
    
    # Nouvelle fonction / Objet
    obj = result.find('object')
    if obj is not None:
        donnees['nouvelle_fonction'] = extraire_texte_concatene(obj, 'text')
        orgs = [e.text.strip() for e in obj.findall('organization') if e.text and e.text.strip()]
        donnees['organisation'] = " | ".join(orgs) if orgs else ""
    else:
        donnees['nouvelle_fonction'] = ''
        donnees['organisation'] = ''
    
    # Département
    donnees['departement'] = extraire_departement(
        donnees.get('nouvelle_fonction', '') + ' ' + 
        donnees.get('fonction_actuelle', '') + ' ' + 
        donnees.get('organisation', '')
    )
    
    # Informations complémentaires
    donnees['parlement'] = result.get('parlement', '')
    donnees['commission'] = result.get('commission_parlementaire', '')
    donnees['cabinet'] = result.get('cabinet', '')
    donnees['grade'] = result.get('grade', '')
    donnees['duree_mandat'] = result.get('duree', '')
    donnees['est_suppleant'] = 'Oui' if result.get('suppleant') == 'true' else ''
    donnees['depart_retraite'] = 'Oui' if result.get('depart_retraite') == 'true' else ''
    
    # Remplacement
    remplacement = result.find('remplacement')
    if remplacement is not None:
        remp_person = remplacement.find('person')
        if remp_person is not None:
            remp_name = remp_person.find('name')
            if remp_name is not None:
                nom_remp = remp_name.get('nom', '')
                prenom_remp = remp_name.get('prenom', '')
                if prenom_remp:
                    donnees['remplace'] = f"{prenom_remp.title()} {nom_remp.upper()}"
                else:
                    donnees['remplace'] = nom_remp.upper()
            else:
                donnees['remplace'] = ''
        else:
            donnees['remplace'] = ''
    else:
        donnees['remplace'] = ''
    
    return donnees

def extraire_departement(texte):
    """Essaie d'extraire le nom d'un département du texte"""
    if not texte:
        return ""
    
    departements = [
        "Ain", "Aisne", "Allier", "Alpes-de-Haute-Provence", "Hautes-Alpes", "Alpes-Maritimes",
        "Ardèche", "Ardennes", "Ariège", "Aube", "Aude", "Aveyron", "Bouches-du-Rhône",
        "Calvados", "Cantal", "Charente", "Charente-Maritime", "Cher", "Corrèze", "Corse-du-Sud",
        "Haute-Corse", "Côte-d'Or", "Côtes-d'Armor", "Creuse", "Dordogne", "Doubs", "Drôme",
        "Eure", "Eure-et-Loir", "Finistère", "Gard", "Haute-Garonne", "Gers", "Gironde",
        "Hérault", "Ille-et-Vilaine", "Indre", "Indre-et-Loire", "Isère", "Jura", "Landes",
        "Loir-et-Cher", "Loire", "Haute-Loire", "Loire-Atlantique", "Loiret", "Lot",
        "Lot-et-Garonne", "Lozère", "Maine-et-Loire", "Manche", "Marne", "Haute-Marne",
        "Mayenne", "Meurthe-et-Moselle", "Meuse", "Morbihan", "Moselle", "Nièvre", "Nord",
        "Oise", "Orne", "Pas-de-Calais", "Puy-de-Dôme", "Pyrénées-Atlantiques", "Hautes-Pyrénées",
        "Pyrénées-Orientales", "Bas-Rhin", "Haut-Rhin", "Rhône", "Haute-Saône", "Saône-et-Loire",
        "Sarthe", "Savoie", "Haute-Savoie", "Paris", "Seine-Maritime", "Seine-et-Marne",
        "Yvelines", "Deux-Sèvres", "Somme", "Tarn", "Tarn-et-Garonne", "Var", "Vaucluse",
        "Vendée", "Vienne", "Haute-Vienne", "Vosges", "Yonne", "Territoire de Belfort",
        "Essonne", "Hauts-de-Seine", "Seine-Saint-Denis", "Val-de-Marne", "Val-d'Oise"
    ]
    
    texte_lower = texte.lower()
    deps_trouves = []
    
    for dep in departements:
        if dep.lower() in texte_lower:
            deps_trouves.append(dep)
    
    return " | ".join(deps_trouves) if deps_trouves else ""

def convertir_xml_vers_csv(nb_mois_arriere=1, limite=None):
    """
    Convertit le XML en CSV avec filtre temporel en streaming
    """
    url = "https://www.data.gouv.fr/api/1/datasets/r/1c5ac28d-92ca-4a19-aefb-63fbde4387a2"
    
    # Calculer la date limite
    date_limite = datetime.now() - timedelta(days=nb_mois_arriere * 30)
    
    print("""
    ╔════════════════════════════════════════════════════════════════════════════╗
    ║                                                                            ║
    ║           📜 CONVERSION JOURNAL OFFICIEL : XML → CSV 📜                    ║
    ║                                                                            ║
    ╚════════════════════════════════════════════════════════════════════════════╝
    """)
    
    print(f"📅 Période de recherche : depuis le {date_limite.strftime('%d/%m/%Y')}")
    print(f"   (soit {nb_mois_arriere} mois en arrière)\n")
    
    print("🔄 Téléchargement et traitement en streaming...\n")
    
    # Colonnes du CSV
    colonnes = [
        'nom_complet', 'nom', 'prenom', 'sexe',
        'type_decision', 'date_publication', 'date_effet',
        'fonction_actuelle', 'nouvelle_fonction', 
        'organisation', 'departement',
        'parlement', 'commission', 'cabinet', 'grade',
        'duree_mandat', 'est_suppleant', 'depart_retraite',
        'remplace', 'source', 'source_id'
    ]
    
    nom_fichier = f'nominations_jo_{nb_mois_arriere}mois.csv'
    
    # Ouvrir le fichier CSV en écriture
    csvfile = open(nom_fichier, 'w', encoding='utf-8-sig', newline='')
    writer = csv.DictWriter(csvfile, fieldnames=colonnes, delimiter=';', extrasaction='ignore')
    writer.writeheader()
    
    # Statistiques
    compteur_total = 0
    compteur_filtres = 0
    compteur_avant_limite = 0
    types_decisions = {}
    
    try:
        # Télécharger en streaming
        response = requests.get(url, stream=True)
        response.raw.decode_content = True
        
        print("✅ Connexion établie")
        print("🔄 Parsing en cours...\n")
        
        # Parser en streaming avec iterparse
        for event, elem in ET.iterparse(response.raw, events=('end',)):
            if elem.tag == 'result':
                compteur_total += 1
                
                # Vérifier la date AVANT d'extraire toutes les données
                date_pub = parse_date(elem.get('source_date', ''))
                
                if date_pub and date_pub >= date_limite:
                    compteur_avant_limite += 1
                    
                    # Vérifier la limite
                    if limite and compteur_filtres >= limite:
                        print(f"\n⚠️  Limite de {limite} résultats atteinte")
                        elem.clear()
                        break
                    
                    # Extraire les données seulement si la date correspond
                    donnees = extraire_donnees_result(elem)
                    
                    # Compter les types
                    type_dec = donnees.get('type_decision', 'Non spécifié')
                    types_decisions[type_dec] = types_decisions.get(type_dec, 0) + 1
                    
                    # Écrire dans le CSV
                    writer.writerow(donnees)
                    compteur_filtres += 1
                    
                    # Afficher progression tous les 100 résultats filtrés
                    if compteur_filtres % 100 == 0:
                        print(f"   ✓ {compteur_filtres} décisions exportées ({compteur_total} analysées)...")
                
                # Libérer la mémoire
                elem.clear()
        
    except Exception as e:
        print(f"\n⚠️  Erreur pendant le traitement : {e}")
        print(f"   {compteur_filtres} résultats ont été sauvegardés avant l'erreur")
    
    finally:
        csvfile.close()
    
    print(f"\n✅ Traitement terminé !")
    print(f"📊 {compteur_total:,} décisions analysées au total".replace(',', ' '))
    print(f"✅ {compteur_filtres:,} décisions exportées".replace(',', ' '))
    print(f"💾 Fichier créé : {nom_fichier}\n")
    
    if compteur_filtres == 0:
        print("⚠️  Aucune décision trouvée pour cette période")
        return
    
    # Statistiques
    print("═" * 100)
    print("📊 STATISTIQUES\n")
    print("Répartition par type de décision :")
    
    for type_dec, count in sorted(types_decisions.items(), key=lambda x: x[1], reverse=True):
        pourcentage = (count / compteur_filtres) * 100
        barre_longueur = int(pourcentage / 2)
        barre = "█" * barre_longueur
        print(f"   {type_dec:30s} : {barre} {count:5d} ({pourcentage:5.1f}%)")
    
    print("\n" + "═" * 100 + "\n")

def main():
    parser = argparse.ArgumentParser(
        description='Convertit les nominations du Journal Officiel en CSV avec filtre temporel',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples d'utilisation:
  python prefet_scrapper.py                    # Derniers 1 mois (par défaut)
  python prefet_scrapper.py --mois 3           # Derniers 3 mois
  python prefet_scrapper.py --mois 6           # Derniers 6 mois
  python prefet_scrapper.py --mois 12          # Dernière année
  python prefet_scrapper.py --mois 1 --limite 100  # 1 mois, max 100 résultats
        """
    )
    
    parser.add_argument(
        '--mois', 
        type=int, 
        default=1,
        help='Nombre de mois en arrière (défaut: 1)'
    )
    
    parser.add_argument(
        '--limite',
        type=int,
        default=None,
        help='Nombre maximum de résultats à exporter (défaut: tous)'
    )
    
    args = parser.parse_args()
    
    try:
        convertir_xml_vers_csv(nb_mois_arriere=args.mois, limite=args.limite)
    except Exception as e:
        print(f"\n❌ ERREUR : {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()