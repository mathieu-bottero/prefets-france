# -*- coding: utf-8 -*-
"""
Classification des directeurs régionaux DREETS / DEETS / DRIEETS / DGCOPOP / DCSTEP
à partir du Journal Officiel.
"""

import re


def normaliser(s):
    return re.sub(r'\s+', ' ', s or '').strip()


def nettoyer_territoire(t):
    t = normaliser(t)
    
    # Supprimer les groupes (groupe I, II, III, IV, etc.)
    t = re.sub(r'\s*\(groupe\s+[IVX]+\)', '', t, flags=re.IGNORECASE)
    
    # Supprimer les articles en début
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
    r"|[àa]\s+"                  # "à Saint-Pierre-et-Miquelon"
    r")"
)

# DRIEETS — Direction régionale et interdépartementale de l'économie, 
# de l'emploi, du travail et des solidarités (Île-de-France uniquement)
#
# ⚠️ CORRECTION MASI : Gère aussi "directeur régional de la direction régionale..."
RE_DRIEETS = re.compile(
    r"direct(?:eur|rice)\s+r[eé]gional(?:e)?\s+"
    r"(?:de\s+la\s+direction\s+r[eé]gionale\s+et\s+interd[eé]partemental(?:e)?\s+|"  # ← CAS MASI
    r"et\s+interd[eé]partemental(?:e)?\s+)"
    r"de\s+l[''](?:é|e)conomie,?\s+de\s+l['']emploi,?\s+du\s+travail\s+et\s+des\s+solidarit[eé]s"
    + _GRP
    + r"(?:\s+" + _ART + r"(.+?))?(?=\s*(?:,|\||;|$))",
    re.IGNORECASE
)

RE_DRIEETS_SIMPLE = re.compile(
    r"direct(?:eur|rice)\s+r[eé]gional(?:e)?\s+"
    r"(?:de\s+la\s+direction\s+r[eé]gionale\s+et\s+interd[eé]partemental(?:e)?\s+|"  # ← CAS MASI
    r"et\s+interd[eé]partemental(?:e)?\s+)"
    r"de\s+l[''](?:é|e)conomie,?\s+de\s+l['']emploi,?\s+du\s+travail\s+et\s+des\s+solidarit[eé]s",
    re.IGNORECASE
)

# DGCOPOP — Direction générale de la cohésion et des populations (Guyane uniquement)
#
# ⚠️ CORRECTION BERNOT : Gère "directrice générale DES populations" (sans "cohésion")
RE_DGCOPOP = re.compile(
    r"direct(?:eur|rice)\s+g[eé]n[eé]ral(?:e)?\s+"
    r"(?:de\s+la\s+coh[eé]sion\s+(?:et\s+)?)?des\s+populations?"  # ← "cohésion" optionnelle
    + _GRP
    + r"(?:\s+" + _ART + r"(.+?))?(?=\s*(?:,|\||;|$))",
    re.IGNORECASE
)

# DCSTEP — Direction de la cohésion sociale, du travail, de l'emploi 
# et de la population (Saint-Pierre-et-Miquelon uniquement)
#
# ⚠️ CORRECTION BÉPOIX : L'apostrophe est TOUJOURS présente dans "de l'emploi"
RE_DCSTEP = re.compile(
    r"direct(?:eur|rice)\s+de\s+la\s+coh[eé]sion\s+sociale,?\s+"
    r"du\s+travail,?\s+de\s+l['']emploi\s+et\s+de\s+la\s+population"  # ← apostrophe obligatoire
    + _GRP
    + r"(?:\s+" + _ART + r"(.+?))?(?=\s*(?:,|\||;|$))",
    re.IGNORECASE
)

# DEETS — Direction de l'économie, de l'emploi, du travail et des solidarités
# (Guadeloupe, Martinique, Réunion, Mayotte)
RE_DEETS = re.compile(
    r"direct(?:eur|rice)\s+de\s+l[''](?:é|e)conomie,?\s+"
    r"de\s+l['']emploi,?\s+du\s+travail\s+et\s+des\s+solidarit[eé]s"
    + _GRP
    + r"(?:\s+" + _ART + r"(.+?))?(?=\s*(?:,|\||;|$))",
    re.IGNORECASE
)

# DREETS — Direction régionale de l'économie, de l'emploi, du travail 
# et des solidarités (métropole hors Île-de-France)
RE_DREETS = re.compile(
    r"direct(?:eur|rice)\s+r[eé]gional(?:e)?\s+"
    r"de\s+l[''](?:é|e)conomie,?\s+de\s+l['']emploi,?\s+du\s+travail\s+et\s+des\s+solidarit[eé]s"
    + _GRP
    + r"(?:\s+" + _ART + r"(.+?))?(?=\s*(?:,|\||;|$))",
    re.IGNORECASE
)

# DREETS avec résidence administrative (sans mention de région)
RE_RESIDENCE = re.compile(
    r"en\s+r[eé]sidence\s+administrative\s+[aà]\s+([\w\-]+(?:\s+[\w\-]+)*)",
    re.IGNORECASE
)

RE_GRADE = re.compile(
    r"(?:administrateur|administratrice)\s+(?:de\s+l[''](?:é|É|e)tat|civil(?:e)?|"
    r"hors\s+classe|g[eé]n[eé]ral(?:e)?)|"
    r"(?:ing[eé]nieur(?:\s+en\s+chef|\s+g[eé]n[eé]ral)?)|"
    r"(?:attach[eé](?:e)?\s+principal(?:e)?)|"
    r"(?:directeur|directrice)\s+(?:d['']administration|de\s+projet|du\s+travail)",
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
    "la guyane":                      "Guyane",
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


def classifier_poste_dreets(texte):
    """
    Retourne (type, territoire, grade) ou None.

    type       : 'dreets' | 'deets' | 'drieets' | 'dgcopop' | 'dcstep'
    territoire : nom canonique de la région / collectivité
    grade      : grade du fonctionnaire, si trouvé
    """
    if not texte:
        return None

    texte = normaliser(texte)

    match_grade = RE_GRADE.search(texte)
    grade = match_grade.group(0) if match_grade else ''

    # Ordre : DRIEETS > DGCOPOP > DCSTEP > DEETS > DREETS
    
    # DRIEETS : Île-de-France uniquement
    match = RE_DRIEETS.search(texte)
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

        return ('drieets', territoire, grade)

    if RE_DRIEETS_SIMPLE.search(texte):
        return ('drieets', 'Île-de-France', grade)

    # DGCOPOP : Guyane uniquement
    match = RE_DGCOPOP.search(texte)
    if match:
        territoire_brut = match.group(1) if match.lastindex and match.group(1) else None
        if territoire_brut:
            territoire = normaliser_territoire(nettoyer_territoire(territoire_brut))
        else:
            ville = extraire_ville_residence(texte)
            territoire = VILLES_RESIDENCE.get(ville, "Guyane")
        return ('dgcopop', territoire, grade)

    # DCSTEP : Saint-Pierre-et-Miquelon uniquement
    match = RE_DCSTEP.search(texte)
    if match:
        territoire_brut = match.group(1) if match.lastindex and match.group(1) else None
        if territoire_brut:
            territoire = normaliser_territoire(nettoyer_territoire(territoire_brut))
        else:
            territoire = "Saint-Pierre-et-Miquelon"
        return ('dcstep', territoire, grade)

    # DEETS : Guadeloupe, Martinique, Réunion, Mayotte
    match = RE_DEETS.search(texte)
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

        return ('deets', territoire, grade)

    # DREETS : métropole hors Île-de-France
    match = RE_DREETS.search(texte)
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
        return ('dreets', territoire, grade)

    return None


LIBELLES_TYPE = {
    'dreets':   "Directeur(rice) régional(e) de l'économie, de l'emploi, du travail et des solidarités",
    'deets':    "Directeur(rice) de l'économie, de l'emploi, du travail et des solidarités",
    'drieets':  "Directeur(rice) régional(e) et interdépartemental(e) de l'économie, "
                "de l'emploi, du travail et des solidarités",
    'dgcopop':  "Directeur(rice) général(e) de la cohésion et des populations",
    'dcstep':   "Directeur(rice) de la cohésion sociale, du travail, de l'emploi et de la population",
}

REGIONS_DREETS  = {
    'Auvergne-Rhône-Alpes', 'Bourgogne-Franche-Comté', 'Bretagne',
    'Centre-Val de Loire', 'Corse', 'Grand Est', 'Hauts-de-France',
    'Normandie', 'Nouvelle-Aquitaine', 'Occitanie',
    'Pays de la Loire', "Provence-Alpes-Côte d'Azur",
}
REGIONS_DEETS   = {'Guadeloupe', 'Martinique', 'Réunion', 'Mayotte'}
REGIONS_DRIEETS = {'Île-de-France'}
REGIONS_DGCOPOP = {'Guyane'}
REGIONS_DCSTEP  = {'Saint-Pierre-et-Miquelon'}