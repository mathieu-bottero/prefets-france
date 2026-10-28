#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de debug : extrait toutes les nominations DDT/DDTM du JO en CSV brut
"""

import requests
import xml.etree.ElementTree as ET
import csv
import argparse
from datetime import datetime, timedelta

URL_JO = "https://www.data.gouv.fr/api/1/datasets/r/1c5ac28d-92ca-4a19-aefb-63fbde4387a2"

def parse_date(date_str):
    if not date_str or not date_str.strip():
        return None
    try:
        return datetime.strptime(date_str[:10], '%Y-%m-%d')
    except:
        return None

def extraire_texte_concatene(element, tag):
    if element is None:
        return ""
    textes = [e.text.strip() for e in element.findall(tag) if e.text and e.text.strip()]
    return " | ".join(textes) if textes else ""

def main():
    parser = argparse.ArgumentParser(description='Extrait les nominations DDT/DDTM du JO')
    parser.add_argument('--mois', type=int, default=12, help="Nombre de mois en arrière")
    args = parser.parse_args()

    date_limite = datetime.now() - timedelta(days=args.mois * 30)
    print(f"Extraction des nominations DDT/DDTM depuis le {date_limite.strftime('%d/%m/%Y')}...\n")

    fichier_sortie = f'nominations_ddt_{args.mois}mois.csv'
    colonnes = [
        'date_publication', 'date_effet', 'type_decision',
        'nom_complet', 'sexe', 'texte_poste', 'source_id'
    ]

    with open(fichier_sortie, 'w', encoding='utf-8-sig', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=colonnes, delimiter=';')
        writer.writeheader()

        response = requests.get(URL_JO, stream=True)
        response.raw.decode_content = True
        
        total, retenus = 0, 0
        
        for event, elem in ET.iterparse(response.raw, events=('end',)):
            if elem.tag == 'result':
                total += 1
                date_pub = parse_date(elem.get('source_date', ''))
                
                if date_pub and date_pub >= date_limite:
                    obj = elem.find('object')
                    texte = extraire_texte_concatene(obj, 'text') if obj else ''
                    
                    if 'directeur départemental des territoires' in texte.lower() or \
                       'directrice départementale des territoires' in texte.lower():
                        
                        person = elem.find('person')
                        nom_complet = ''
                        sexe = ''
                        
                        if person is not None:
                            name = person.find('name')
                            if name is not None:
                                nom_complet = name.text.strip() if name.text else ''
                            sexe = person.get('sexe', '')
                        
                        date_effet = parse_date(elem.get('date_debut', ''))
                        
                        writer.writerow({
                            'date_publication': date_pub.strftime('%d/%m/%Y'),
                            'date_effet': date_effet.strftime('%d/%m/%Y') if date_effet else '',
                            'type_decision': elem.get('type_ordre', ''),
                            'nom_complet': nom_complet,
                            'sexe': sexe,
                            'texte_poste': texte,
                            'source_id': elem.get('source_id', '')
                        })
                        
                        retenus += 1
                        if retenus % 50 == 0:
                            print(f"   {retenus} nominations trouvées...")
                
                elem.clear()

    print(f"\n✅ {retenus} nominations DDT/DDTM extraites sur {total} décisions")
    print(f"💾 Fichier : {fichier_sortie}")

if __name__ == "__main__":
    main()