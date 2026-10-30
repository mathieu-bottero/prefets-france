#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostic : Trouve TOUTES les nominations DREETS manquantes
"""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

URL_JO = "https://www.data.gouv.fr/api/1/datasets/r/1c5ac28d-92ca-4a19-aefb-63fbde4387a2"

REGIONS_RECHERCHEES = {
    "Pays de la Loire": ["Giudicelli", "nantes"],
    "Nouvelle-Aquitaine": ["bordeaux", "nouvelle-aquitaine", "limoges", "poitiers"],
    "Martinique": ["martinique", "fort-de-france"],
    "Réunion": ["réunion", "reunion", "saint-denis"],
}

def parse_date(date_str):
    if not date_str or not date_str.strip():
        return None
    try:
        return datetime.strptime(date_str[:10], '%Y-%m-%d')
    except Exception:
        return None

def extraire_texte(element, tag):
    if element is None:
        return ""
    textes = [e.text.strip() for e in element.findall(tag) if e.text and e.text.strip()]
    return " | ".join(textes)

date_limite = datetime.now() - timedelta(days=36 * 30)

print("🔍 Recherche des nominations DREETS/DEETS manquantes (36 derniers mois)...\n")

response = requests.get(URL_JO, stream=True, timeout=120)
response.raise_for_status()
response.raw.decode_content = True

resultats = {region: [] for region in REGIONS_RECHERCHEES}

for event, elem in ET.iterparse(response.raw, events=('end',)):
    if elem.tag != 'result':
        continue
    
    date_pub = parse_date(elem.get('source_date', ''))
    if not date_pub or date_pub < date_limite:
        elem.clear()
        continue
    
    type_decision = elem.get('type_ordre', '').lower()
    if type_decision not in ['nomination', 'charge', 'renouvellement']:
        elem.clear()
        continue
    
    person = elem.find('person')
    obj = elem.find('object')
    
    texte_person = extraire_texte(person, 'text') if person else ''
    texte_obj = extraire_texte(obj, 'text') if obj else ''
    texte_complet = f"{texte_person} {texte_obj}".lower()
    
    # Chercher "directeur" ou "directrice" + "économie" OU "solidarités" OU "dreets" OU "deets"
    if not (("directeur" in texte_complet or "directrice" in texte_complet) and 
            ("économie" in texte_complet or "economie" in texte_complet or 
             "solidarités" in texte_complet or "solidarites" in texte_complet or
             "dreets" in texte_complet or "deets" in texte_complet)):
        elem.clear()
        continue
    
    # Vérifier si ça correspond à une région recherchée
    for region, mots_cles in REGIONS_RECHERCHEES.items():
        if any(mot.lower() in texte_complet for mot in mots_cles):
            name = person.find('name') if person else None
            nom_complet = name.text.strip() if name is not None and name.text else "Nom inconnu"
            
            resultats[region].append({
                'nom': nom_complet,
                'date': date_pub.strftime('%d/%m/%Y'),
                'type': type_decision,
                'source_id': elem.get('source_id', ''),
                'texte_person': texte_person[:200],
                'texte_obj': texte_obj[:200]
            })
    
    elem.clear()

# Affichage des résultats
print("=" * 100)
for region, nominations in resultats.items():
    print(f"\n📍 {region.upper()} : {len(nominations)} nomination(s) trouvée(s)")
    print("-" * 100)
    for n in nominations:
        print(f"   ✅ {n['nom']} — {n['date']} ({n['type']})")
        print(f"      Source : {n['source_id']}")
        print(f"      Person : {n['texte_person']}")
        print(f"      Object : {n['texte_obj']}")
        print()

print("=" * 100)