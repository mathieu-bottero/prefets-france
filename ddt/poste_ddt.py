# -*- coding: utf-8 -*-
"""
Classification des directeurs départementaux des territoires (DDT/DDTM)
à partir du Journal Officiel.

Structure simplifiée :
- 1 département = 1 DDT (départements non côtiers) ou 1 DDTM (côtiers)
- Nomination par arrêté du Premier ministre
- Mandat de 4 ans avec période probatoire de 6 mois
"""

import re

def normaliser(s):
    return re.sub(r'\s+', ' ', s or '').strip()

def nettoyer_territoire(t):
    t = normaliser(t)

    t = re.sub(
        r"^territoires\s+et\s+de\s+la\s+mer\s+de\s+",
        "",
        t,
        flags=re.IGNORECASE
    )
    t = re.sub(r"^territoires\s+de\s+", "", t, flags=re.IGNORECASE)

    t = re.sub(
        r"^(?:des|de\s+la|de\s+l['’]|du|d['’])\s+",
        "",
        t,
        flags=re.IGNORECASE
    )

    return t.strip()

# Patterns de détection
DDT = r"direct(?:eur|rice)\s+départemental(?:e)?\s+des\s+territoires"
DDTM = r"direct(?:eur|rice)\s+départemental(?:e)?\s+des\s+territoires\s+et\s+de\s+la\s+mer"
# Patterns de détection
# Les espaces finaux sont volontairement inclus dans les articles :
# le nom du territoire commence juste après.
ARTICLE = r"(?:de\s+la\s+|de\s+l['’]|d['’]|des\s+|du\s+|de\s+)"

RE_DDTM = re.compile(
    r"direct(?:eur|rice)\s+départemental(?:e)?\s+"
    r"des\s+territoires\s+et\s+de\s+la\s+mer\s+"
    + ARTICLE +
    r"(.+?)(?=\s*(?:,|\||$))",
    re.IGNORECASE
)

RE_DDT = re.compile(
    r"direct(?:eur|rice)\s+départemental(?:e)?\s+"
    r"des\s+territoires\s+"
    + ARTICLE +
    # Sécurité : ne jamais considérer un DDTM comme un DDT.
    r"(?!territoires\s+et\s+de\s+la\s+mer\b)"
    r"(?!et\s+de\s+la\s+mer\b)"
    r"(.+?)(?=\s*(?:,|\||$))",
    re.IGNORECASE
)

# Pattern spécifique à l'anomalie rencontrée dans le flux JO :
# « directeur départemental des territoires des territoires et de la mer... »
RE_DDTM_DOUBLON = re.compile(
    r"(direct(?:eur|rice)\s+départemental(?:e)?\s+des\s+territoires)"
    r"\s+des\s+territoires\s+et\s+de\s+la\s+mer",
    re.IGNORECASE
)


# Pattern pour extraire le grade
RE_GRADE = re.compile(
    r"ingénieur(?:\s+en\s+chef|\s+général)?\s+(?:des\s+ponts,?\s*des\s+eaux\s+et\s+des\s+forêts|de\s+l'agriculture\s+et\s+de\s+l'environnement)",
    re.IGNORECASE
)

def classifier_poste_ddt(texte):
    """
    Retourne (type, territoire, grade) ou None.

    type       : 'ddt' ou 'ddtm'
    territoire : nom du département
    grade      : grade du fonctionnaire, si trouvé
    """
    if not texte:
        return None

    texte = normaliser(texte)

    # Corrige l'anomalie de certains libellés du JO :
    #
    # Avant :
    # directeur départemental des territoires des territoires
    # et de la mer de la Charente-Maritime
    #
    # Après :
    # directeur départemental des territoires et de la mer
    # de la Charente-Maritime
    texte = RE_DDTM_DOUBLON.sub(r"\1 et de la mer", texte)

    match_grade = RE_GRADE.search(texte)
    grade = match_grade.group(0) if match_grade else ''

    # Toujours tester DDTM avant DDT : le libellé DDTM contient
    # intégralement le début du libellé DDT.
    match = RE_DDTM.search(texte)
    if match:
        return ('ddtm', nettoyer_territoire(match.group(1)), grade)

    match = RE_DDT.search(texte)
    if match:
        return ('ddt', nettoyer_territoire(match.group(1)), grade)

    return None

LIBELLES_TYPE = {
    'ddt': "Directeur(rice) départemental(e) des territoires",
    'ddtm': "Directeur(rice) départemental(e) des territoires et de la mer",
}

# Départements côtiers (normalement DDTM)
DEPARTEMENTS_COTIERS = {
    'Alpes-Maritimes', 'Bouches-du-Rhône', 'Calvados', 'Charente-Maritime',
    'Côtes-d\'Armor', 'Finistère', 'Gard', 'Gironde', 'Hérault', 
    'Ille-et-Vilaine', 'Landes', 'Loire-Atlantique', 'Manche', 
    'Morbihan', 'Nord', 'Pas-de-Calais', 'Pyrénées-Atlantiques',
    'Pyrénées-Orientales', 'Seine-Maritime', 'Somme', 'Var', 'Vendée',
    # Outre-mer
    'Guadeloupe', 'Martinique', 'Guyane', 'Réunion', 'Mayotte'
}