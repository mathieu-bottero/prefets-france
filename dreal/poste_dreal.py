# -*- coding: utf-8 -*-
"""
Classification des directeurs régionaux DREAL / DEAL / DRIEAT / DTAM / DGTM
à partir du Journal Officiel.
"""

import re


def normaliser(s):
    return re.sub(r'\s+', ' ', s or '').strip()


def nettoyer_territoire(t):
    t = normaliser(t)
    t = re.sub(
        r"^(?:"
        r"de\s+la\s+r[eé]gion\s+"
        r"|r[eé]gion\s+"
        r"|de\s+la\s+"
        r"|de\s+l['']"
        r"|d['']"
        r"|des\s+"
        r"|du\s+"
        r"|de\s+"
        r")",
        "",
        t,
        flags=re.IGNORECASE
    )
    return t.strip()


# ── Patterns ─────────────────────────────────────────────────────────────────

_GRP = r"(?:\s*\([^)]*\))?"   # "(groupe I)", "(groupe II)"... optionnel

_ART = (
    r"(?:"
    r"de\s+la\s+r[eé]gion\s+"   # "de la région Occitanie"
    r"|r[eé]gion\s+"             # "région Centre-Val de Loire"
    r"|de\s+la\s+"               # "de la Bretagne / de La Réunion"
    r"|de\s+l['']"               # "de l'Île-de-France"
    r"|d['']"                    # "d'Occitanie"
    r"|des\s+"                   # "des Hauts-de-France"
    r"|du\s+"                    # "du Grand Est"
    r"|de\s+"                    # "de Corse"
    r")"
)

_LIBELLE_ENV_AMENAGEMENT_LOGEMENT = (
    r"de\s+l['']environnement,?\s+"
    r"de\s+l['']am[eé]nagement"
    r"(?:,?\s+(?:et\s+)?du\s+logement)"
)

# DRIEAT — NOTE : "interdépartemental" sans aucun caractère parasite
RE_DRIEAT = re.compile(
    r"direct(?:eur|rice)\s+r[eé]gional(?:e)?\s+et\s+inter(?:د|d)[eé]partemental(?:e)?\s+"
    r"de\s+l['']environnement,?\s+de\s+l['']am[eé]nagement\s+et\s+des\s+transports"
    + _GRP
    + r"(?:\s+" + _ART + r"(.+?))?(?=\s*(?:,|\||;|$))",
    re.IGNORECASE
)

RE_DRIEAT_SIMPLE = re.compile(
    r"direct(?:eur|rice)\s+r[eé]gional(?:e)?\s+et\s+interdépartemental(?:e)?\s+"
    r"de\s+l['']environnement,?\s+de\s+l['']am[eé]nagement\s+et\s+des\s+transports",
    re.IGNORECASE
)

# DRIHL — Direction régionale et interdépartementale
# de l'hébergement et du logement d'Île-de-France.
RE_DRIHL = re.compile(
    r"direct(?:eur|rice)\s+r[eé]gional(?:e)?\s+et\s+interd[eé]partemental(?:e)?\s+"
    r"de\s+l['']h[eé]bergement\s+et\s+du\s+logement"
    + _GRP
    + r"(?:\s+" + _ART + r"(.+?))?(?=\s*(?:,|\||;|$))",
    re.IGNORECASE
)

# Variante de sécurité : la DRIHL est nécessairement située en Île-de-France.
RE_DRIHL_SIMPLE = re.compile(
    r"direct(?:eur|rice)\s+r[eé]gional(?:e)?\s+et\s+interd[eé]partemental(?:e)?\s+"
    r"de\s+l['']h[eé]bergement\s+et\s+du\s+logement",
    re.IGNORECASE
)

# DGTM — "directeur général des territoires et de la mer (groupe II) de Guyane"
RE_DGTM = re.compile(
    r"direct(?:eur|rice)\s+g[eé]n[eé]ral(?:e)?\s+"
    r"des\s+territoires\s+et\s+de\s+la\s+mer"
    + _GRP
    + r"(?:\s+" + _ART + r"(.+?))?(?=\s*(?:,|\||;|$))",
    re.IGNORECASE
)

# DEAL — "directeur de l'environnement, de l'aménagement et du logement
#          (groupe II) de La Réunion"
RE_DEAL = re.compile(
    r"direct(?:eur|rice)\s+"
    + _LIBELLE_ENV_AMENAGEMENT_LOGEMENT
    + _GRP
    + r"(?:\s+" + _ART + r"(.+?))?(?=\s*(?:,|\||;|$))",
    re.IGNORECASE
)

# DREAL — "directeur régional de l'environnement, de l'aménagement et du logement
#           (groupe I) de la région Provence-Alpes-Côte d'Azur"
RE_DREAL = re.compile(
    r"direct(?:eur|rice)\s+r[eé]gional(?:e)?\s+"
    + _LIBELLE_ENV_AMENAGEMENT_LOGEMENT
    + _GRP
    + r"(?:\s+" + _ART + r"(.+?))?(?=\s*(?:,|\||;|$))",
    re.IGNORECASE
)

# DREAL avec résidence administrative (sans mention de région)
RE_RESIDENCE = re.compile(
    r"en\s+r[eé]sidence\s+administrative\s+[aà]\s+([\w\-]+(?:\s+[\w\-]+)*)",
    re.IGNORECASE
)

# DTAM — "directeur des territoires, de l'alimentation et de la mer
#          (groupe X) de Saint-Pierre-et-Miquelon"
RE_DTAM = re.compile(
    r"direct(?:eur|rice)\s+des\s+territoires,?\s+de\s+l['']alimentation\s+et\s+de\s+la\s+mer"
    + _GRP
    + r"(?:\s+" + _ART + r"(.+?))?",   # le territoire est implicite (SPM) ou explicite
    re.IGNORECASE
)

RE_GRADE = re.compile(
    r"ing[eé]nieur(?:\s+en\s+chef|\s+g[eé]n[eé]ral)?\s+"
    r"(?:des\s+ponts,?\s*des\s+eaux\s+et\s+des\s+for[eê]ts"
    r"|de\s+l['']agriculture\s+et\s+de\s+l['']environnement)",
    re.IGNORECASE
)


# ── Mapping ville de résidence → région ──────────────────────────────────────

VILLES_RESIDENCE = {
    # Métropole
    "lyon":       "Auvergne-Rhône-Alpes",
    "besançon":   "Bourgogne-Franche-Comté",
    "dijon":      "Bourgogne-Franche-Comté",
    "rennes":     "Bretagne",
    "orléans":    "Centre-Val de Loire",
    "orleans":    "Centre-Val de Loire",
    "ajaccio":    "Corse",
    "strasbourg": "Grand Est",
    "metz":       "Grand Est",
    "châlons-en-champagne": "Grand Est",
    "chalons-en-champagne": "Grand Est",
    "lille":      "Hauts-de-France",
    "amiens":     "Hauts-de-France",
    "rouen":      "Normandie",
    "caen":       "Normandie",
    "toulouse":   "Occitanie",
    "montpellier": "Occitanie",
    "nantes":     "Pays de la Loire",
    "bordeaux":   "Nouvelle-Aquitaine",
    "limoges":    "Nouvelle-Aquitaine",
    "poitiers":   "Nouvelle-Aquitaine",
    "marseille":  "Provence-Alpes-Côte d'Azur",
    "aix-en-provence": "Provence-Alpes-Côte d'Azur",
    
    # Outre-mer
    "basse-terre":     "Guadeloupe",
    "fort-de-france":  "Martinique",
    "cayenne":         "Guyane",
    "saint-denis":     "Réunion",
    "mamoudzou":       "Mayotte",
    "saint-pierre":    "Saint-Pierre-et-Miquelon",
}


# ── Alias régions ─────────────────────────────────────────────────────────────

ALIAS_REGIONS = {
    "auvergne-rhône-alpes":           "Auvergne-Rhône-Alpes",
    "auvergne rhône alpes":           "Auvergne-Rhône-Alpes",
    "auvergne-rhone-alpes":           "Auvergne-Rhône-Alpes",
    "bourgogne-franche-comté":        "Bourgogne-Franche-Comté",
    "bourgogne franche comté":        "Bourgogne-Franche-Comté",
    "bourgogne-franche-comte":        "Bourgogne-Franche-Comté",
    "bretagne":                       "Bretagne",
    "centre-val de loire":            "Centre-Val de Loire",
    "centre val de loire":            "Centre-Val de Loire",
    "centre":                         "Centre-Val de Loire",
    "corse":                          "Corse",
    "grand est":                      "Grand Est",
    "grand-est":                      "Grand Est",
    "hauts-de-france":                "Hauts-de-France",
    "hauts de france":                "Hauts-de-France",
    "île-de-france":                  "Île-de-France",
    "ile-de-france":                  "Île-de-France",
    "île de france":                  "Île-de-France",
    "ile de france":                  "Île-de-France",
    "normandie":                      "Normandie",
    "nouvelle-aquitaine":             "Nouvelle-Aquitaine",
    "nouvelle aquitaine":             "Nouvelle-Aquitaine",
    "occitanie":                      "Occitanie",
    "pays de la loire":               "Pays de la Loire",
    "provence-alpes-côte d'azur":     "Provence-Alpes-Côte d'Azur",
    "provence alpes côte d'azur":     "Provence-Alpes-Côte d'Azur",
    "provence-alpes-cote d'azur":     "Provence-Alpes-Côte d'Azur",
    "provence-alpes-côte d azur":     "Provence-Alpes-Côte d'Azur",
    "paca":                           "Provence-Alpes-Côte d'Azur",
    "guadeloupe":                     "Guadeloupe",
    "martinique":                     "Martinique",
    "guyane":                         "Guyane",
    "la réunion":                     "Réunion",
    "réunion":                        "Réunion",
    "reunion":                        "Réunion",
    "mayotte":                        "Mayotte",
    "saint-pierre-et-miquelon":       "Saint-Pierre-et-Miquelon",
    "saint pierre et miquelon":       "Saint-Pierre-et-Miquelon",
}


def normaliser_territoire(t):
    cle = t.lower().strip()
    return ALIAS_REGIONS.get(cle, t)


def extraire_ville_residence(texte):
    """Extrait la ville de résidence administrative du texte."""
    match = RE_RESIDENCE.search(texte)
    if match:
        ville = match.group(1).lower().strip()
        # Nettoyer les éventuels caractères parasites
        ville = re.sub(r'[,;.].*$', '', ville).strip()
        return ville
    return None


def classifier_poste_dreal(texte):
    """
    Retourne (type, territoire, grade) ou None.

    type       : 'dreal' | 'deal' | 'drieat' | 'dtam' | 'dgtm'
    territoire : nom canonique de la région / collectivité
    grade      : grade du fonctionnaire, si trouvé
    """
    if not texte:
        return None

    texte = normaliser(texte)

    match_grade = RE_GRADE.search(texte)
    grade = match_grade.group(0) if match_grade else ''

    # Ordre : DRIHL > DRIEAT > DGTM > DTAM > DEAL > DREAL
    
    # DRIHL : Île-de-France uniquement
    match = RE_DRIHL.search(texte)
    if match:
        territoire_brut = (
            match.group(1)
            if match.lastindex and match.group(1)
            else None
        )

        if territoire_brut:
            territoire = normaliser_territoire(
                nettoyer_territoire(territoire_brut)
            )
        else:
            territoire = "Île-de-France"

        return ('drihl', territoire, grade)

    if RE_DRIHL_SIMPLE.search(texte):
        return ('drihl', 'Île-de-France', grade)

    match = RE_DRIEAT.search(texte)
    if match:
        territoire_brut = match.group(1) if match.lastindex and match.group(1) else None
        if territoire_brut:
            territoire = normaliser_territoire(nettoyer_territoire(territoire_brut))
        else:
            # Pas de région dans le texte, chercher la ville de résidence
            ville = extraire_ville_residence(texte)
            territoire = VILLES_RESIDENCE.get(ville) if ville else "Île-de-France"
        return ('drieat', territoire, grade)

    if RE_DRIEAT_SIMPLE.search(texte):
        return ('drieat', 'Île-de-France', grade)

    # DGTM : Guyane uniquement
    match = RE_DGTM.search(texte)
    if match:
        territoire_brut = match.group(1) if match.lastindex and match.group(1) else None
        if territoire_brut:
            territoire = normaliser_territoire(nettoyer_territoire(territoire_brut))
        else:
            ville = extraire_ville_residence(texte)
            territoire = VILLES_RESIDENCE.get(ville, "Guyane")
        return ('dgtm', territoire, grade)

    # DTAM : territoire toujours Saint-Pierre-et-Miquelon
    if RE_DTAM.search(texte):
        return ('dtam', 'Saint-Pierre-et-Miquelon', grade)

    match = RE_DEAL.search(texte)
    if match:
        territoire_brut = (
            match.group(1)
            if match.lastindex and match.group(1)
            else None
        )

        if territoire_brut:
            territoire = normaliser_territoire(
                nettoyer_territoire(territoire_brut)
            )
        else:
            # Pas de région dans le texte, chercher la ville de résidence
            ville = extraire_ville_residence(texte)
            territoire = VILLES_RESIDENCE.get(ville) if ville else ""

            if not territoire:
                return None

        # La DEAL Guyane a été supprimée et remplacée par la DGTM.
        # Une ancienne nomination DEAL Guyane ne doit donc plus alimenter
        # la base des postes en cours.
        if territoire == "Guyane":
            return ('obsolete_deal_guyane', territoire, grade)

        return ('deal', territoire, grade)

    match = RE_DREAL.search(texte)
    if match:
        territoire_brut = match.group(1) if match.lastindex and match.group(1) else None
        if territoire_brut:
            territoire = normaliser_territoire(nettoyer_territoire(territoire_brut))
        else:
            # Pas de région dans le texte, chercher la ville de résidence
            ville = extraire_ville_residence(texte)
            territoire = VILLES_RESIDENCE.get(ville) if ville else ""
            if not territoire:
                return None
        return ('dreal', territoire, grade)

    return None


LIBELLES_TYPE = {
    'dreal':  "Directeur(rice) régional(e) de l'environnement, de l'aménagement et du logement",
    'deal':   "Directeur(rice) de l'environnement, de l'aménagement et du logement",
    'drieat': "Directeur(rice) régional(e) et interdépartemental(e) de l'environnement, "
              "de l'aménagement et des transports",
    'drihl':  "Directeur(rice) régional(e) et interdépartemental(e) de l'hébergement et du logement",
    'dtam':   "Directeur(rice) des territoires, de l'alimentation et de la mer",
    'dgtm':   "Directeur(rice) général(e) des territoires et de la mer",
}

REGIONS_DREAL  = {
    'Auvergne-Rhône-Alpes', 'Bourgogne-Franche-Comté', 'Bretagne',
    'Centre-Val de Loire', 'Corse', 'Grand Est', 'Hauts-de-France',
    'Normandie', 'Nouvelle-Aquitaine', 'Occitanie',
    'Pays de la Loire', "Provence-Alpes-Côte d'Azur",
}
REGIONS_DEAL   = {'Guadeloupe', 'Martinique', 'Réunion', 'Mayotte'}
REGIONS_DGTM   = {'Guyane'}
REGIONS_DRIEAT = {'Île-de-France'}
REGIONS_DRIHL  = {'Île-de-France'}
REGIONS_DTAM   = {'Saint-Pierre-et-Miquelon'}