#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recherche nominative dans le flux JO (multi-noms).
Usage :
    python debug_dreets.py "MASI" "BEPOIX" "BERNOT"
    python debug_dreets.py "MASI" "BEPOIX" "BERNOT" --depuis 60
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
    parser = argparse.ArgumentParser(
        description="Recherche de plusieurs noms dans le flux JO"
    )
    parser.add_argument('noms', nargs='+', help="Noms à rechercher (insensibles à la casse)")
    parser.add_argument('--depuis', type=int, default=60,
                        help="Nombre de mois en arrière (défaut: 60)")
    args = parser.parse_args()

    noms_recherche = [n.lower() for n in args.noms]
    date_limite = datetime.now() - timedelta(days=args.depuis * 30)

    print(f"\n🔍 Recherche de {len(noms_recherche)} nom(s) depuis le {date_limite.strftime('%d/%m/%Y')}...")
    print(f"   Noms : {', '.join(args.noms)}\n")

    resultats = {nom: [] for nom in args.noms}
    total = 0

    response = requests.get(URL_JO, stream=True, timeout=120)
    response.raw.decode_content = True

    print("⏳ Analyse du flux JO en cours...\n")

    for event, elem in ET.iterparse(response.raw, events=('end',)):
        if elem.tag != 'result':
            continue
        total += 1
        
        if total % 100_000 == 0:
            print(f"   📊 {total} décisions analysées...")

        # Filtre date
        date_pub = parse_date(elem.get('source_date', ''))
        if not date_pub or date_pub < date_limite:
            elem.clear()
            continue

        # Recherche dans le nom de la personne
        person = elem.find('person')
        nom_complet = ''
        sexe = ''
        if person is not None:
            name = person.find('name')
            if name is not None and name.text:
                nom_complet = name.text.strip()
            sexe = person.get('sexe', '')

        nom_complet_lower = nom_complet.lower()

        # Vérifier si un des noms recherchés est présent
        nom_trouve = None
        for idx, nom_rech in enumerate(noms_recherche):
            if nom_rech in nom_complet_lower:
                nom_trouve = args.noms[idx]
                break

        if not nom_trouve:
            elem.clear()
            continue

        # Trouvé — on extrait tout
        obj = elem.find('object')
        texte_poste    = extraire_texte(obj, 'text') if obj is not None else ''
        texte_contexte = extraire_texte(person, 'text') if person is not None else ''
        date_effet     = parse_date(elem.get('date_debut', ''))

        resultats[nom_trouve].append({
            'date_pub':    date_pub.strftime('%d/%m/%Y'),
            'date_effet':  date_effet.strftime('%d/%m/%Y') if date_effet else '(non précisée)',
            'type_ordre':  elem.get('type_ordre', ''),
            'nom':         nom_complet,
            'sexe':        sexe,
            'texte_poste': texte_poste,
            'texte_ctx':   texte_contexte,
            'source_id':   elem.get('source_id', ''),
        })

        elem.clear()

    # Affichage des résultats
    print(f"\n{'='*80}")
    print(f"  RÉSULTATS : {sum(len(r) for r in resultats.values())} nomination(s) trouvée(s) sur {total} décisions analysées")
    print(f"{'='*80}\n")

    for nom_recherche in args.noms:
        res_nom = resultats[nom_recherche]
        
        print(f"\n{'█'*80}")
        print(f"  🔎 Résultats pour : {nom_recherche}")
        print(f"     Total : {len(res_nom)} occurrence(s)")
        print(f"{'█'*80}\n")

        if not res_nom:
            print(f"  ❌ Aucun résultat trouvé pour '{nom_recherche}'.")
            print(f"     → Vérifiez l'orthographe ou élargissez la fenêtre avec --depuis 120\n")
            continue

        for i, r in enumerate(res_nom, 1):
            print(f"┌─ RÉSULTAT #{i} {'─'*65}")
            print(f"│")
            print(f"│ 📅 Date publication : {r['date_pub']}")
            print(f"│ 📆 Date effet       : {r['date_effet']}")
            print(f"│ 📋 Type décision    : {r['type_ordre']}")
            print(f"│ 👤 Nom complet      : {r['nom']}")
            print(f"│ ⚧  Sexe             : {r['sexe']}")
            print(f"│")
            print(f"│ 📝 TEXTE POSTE :")
            for ligne in r['texte_poste'].split('|'):
                print(f"│    {ligne.strip()}")
            
            if r['texte_ctx']:
                print(f"│")
                print(f"│ 📎 TEXTE CONTEXTE :")
                for ligne in r['texte_ctx'].split('|'):
                    print(f"│    {ligne.strip()}")
            
            print(f"│")
            print(f"│ 🔗 Legifrance : https://www.legifrance.gouv.fr/jorf/id/{r['source_id']}")
            print(f"│")
            print(f"└{'─'*78}\n")

    # Résumé
    print(f"\n{'='*80}")
    print(f"  RÉSUMÉ")
    print(f"{'='*80}")
    for nom in args.noms:
        count = len(resultats[nom])
        statut = "✅" if count > 0 else "❌"
        print(f"  {statut} {nom:20s} : {count} résultat(s)")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()