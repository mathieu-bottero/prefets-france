#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recherche nominative dans le flux JO.
Usage :
    python recherche_nom.py "JECHOUX"
    python recherche_nom.py "JECHOUX" --depuis 2020
"""

import requests
import xml.etree.ElementTree as ET
import argparse
from datetime import datetime, timedelta

URL_JO = "https://www.data.gouv.fr/api/1/datasets/r/1c5ac28d-92ca-4a19-aefb-63fbde4387a2"


def parse_date(date_str):
    if not date_str:
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('nom', help="Nom à rechercher (insensible à la casse)")
    parser.add_argument('--depuis', type=int, default=120,
                        help="Nombre de mois en arrière (défaut: 120)")
    args = parser.parse_args()

    nom_recherche = args.nom.lower()
    date_limite = datetime.now() - timedelta(days=args.depuis * 30)

    print(f"\n🔍 Recherche de '{args.nom}' depuis le {date_limite.strftime('%d/%m/%Y')}...\n")

    resultats = []
    total = 0

    response = requests.get(URL_JO, stream=True, timeout=120)
    response.raw.decode_content = True

    for event, elem in ET.iterparse(response.raw, events=('end',)):
        if elem.tag != 'result':
            continue
        total += 1

        # Filtre date
        date_pub = parse_date(elem.get('source_date', ''))
        if not date_pub or date_pub < date_limite:
            elem.clear()
            continue

        # Recherche dans le nom de la personne
        person = elem.find('person')
        nom_complet = ''
        if person is not None:
            name = person.find('name')
            if name is not None and name.text:
                nom_complet = name.text.strip()

        if nom_recherche not in nom_complet.lower():
            elem.clear()
            continue

        # Trouvé — on extrait tout
        obj = elem.find('object')
        texte_poste    = extraire_texte(obj, 'text') if obj is not None else ''
        texte_contexte = extraire_texte(person, 'text') if person is not None else ''
        date_effet     = parse_date(elem.get('date_debut', ''))

        resultats.append({
            'date_pub':    date_pub.strftime('%d/%m/%Y'),
            'date_effet':  date_effet.strftime('%d/%m/%Y') if date_effet else '(non précisée)',
            'type_ordre':  elem.get('type_ordre', ''),
            'nom':         nom_complet,
            'texte_poste': texte_poste,
            'texte_ctx':   texte_contexte,
            'source_id':   elem.get('source_id', ''),
        })

        elem.clear()

    # Affichage
    print(f"{'='*70}")
    print(f"  {len(resultats)} résultat(s) pour '{args.nom}' sur {total} décisions analysées")
    print(f"{'='*70}\n")

    for r in resultats:
        print(f"📅 Publication : {r['date_pub']}  |  Effet : {r['date_effet']}")
        print(f"📋 Type        : {r['type_ordre']}")
        print(f"👤 Nom         : {r['nom']}")
        print(f"📝 Poste       : {r['texte_poste']}")
        if r['texte_ctx']:
            print(f"📎 Contexte    : {r['texte_ctx']}")
        print(f"🔗 Source      : https://www.legifrance.gouv.fr/jorf/id/{r['source_id']}")
        print(f"{'─'*70}")

    if not resultats:
        print("  Aucun résultat trouvé.")
        print("  → Vérifiez l'orthographe ou élargissez la fenêtre avec --depuis 120")


if __name__ == "__main__":
    main()