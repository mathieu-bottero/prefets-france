# -*- coding: utf-8 -*-
"""
Classification des directeurs départementaux DDETS/DDPP/DDETSPP
à partir du Journal Officiel.

Organisation départementale :
- Départements > 400 000 hab : DDETS + DDPP (2 directeurs)
- Départements < 400 000 hab : DDETSPP (1 directeur)

Création : 1er avril 2021
Nomination par arrêté du Premier ministre
Mandat de 4 ans avec période probatoire de 6 mois
"""



def classifier_poste_ddets_ddpp(texte):
    """
    Retourne (type, territoire, grade) ou None.

    type       : 'ddets', 'ddpp' ou 'ddetspp'
    territoire : nom du département
    grade      : grade du fonctionnaire (extraction simplifiée)
    """
    if not texte:
        return None

    texte = normaliser(texte)
    
    # Extraction grade (simplifiée)
    match_grade = RE_GRADE.search(texte)
    grade = match_grade.group(0).strip() if match_grade else ''

    # Ordre important : DDETSPP d'abord (plus long), puis DDPP, puis DDETS
    match = RE_DDETSPP.search(texte)
    if match:
        return ('ddetspp', nettoyer_territoire(match.group(1)), grade)

    match = RE_DDPP.search(texte)
    if match:
        return ('ddpp', nettoyer_territoire(match.group(1)), grade)

    match = RE_DDETS.search(texte)
    if match:
        return ('ddets', nettoyer_territoire(match.group(1)), grade)

    return None

LIBELLES_TYPE = {
    'ddets': "Directeur(rice) départemental(e) de l'emploi, du travail et des solidarités",
    'ddpp': "Directeur(rice) départemental(e) de la protection des populations",
    'ddetspp': "Directeur(rice) départemental(e) de l'emploi, du travail, des solidarités et de la protection des populations",
}

# ===================================================================
# DONNÉES DE RÉFÉRENCE
# ===================================================================

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
    "Mayotte": "976",
}

# Estimation population 2024 (source : INSEE)
# Départements > 400 000 habitants = DDETS + DDPP séparées
POPULATION_DEPARTEMENTS = {
    'Nord': 2608000,
    'Paris': 2165000,
    'Bouches-du-Rhône': 2044000,
    'Rhône': 1885000,
    'Pas-de-Calais': 1465000,
    'Haute-Garonne': 1415000,
    'Seine-Maritime': 1255000,
    'Gironde': 1640000,
    'Loire-Atlantique': 1429000,
    'Alpes-Maritimes': 1094000,
    'Yvelines': 1438000,
    'Seine-et-Marne': 1403000,
    'Essonne': 1296000,
    'Hauts-de-Seine': 1609000,
    'Seine-Saint-Denis': 1632000,
    'Val-de-Marne': 1398000,
    'Val-d\'Oise': 1243000,
    'Isère': 1272000,
    'Var': 1076000,
    'Hérault': 1175000,
    'Ille-et-Vilaine': 1096000,
    'Finistère': 915000,
    'Meurthe-et-Moselle': 733000,
    'Puy-de-Dôme': 664000,
    'Bas-Rhin': 1142000,
    'Moselle': 1043000,
    'Calvados': 694000,
    'Savoie': 398000,
    'Loire': 765000,
    'Vaucluse': 561000,
    'Maine-et-Loire': 818000,
    'Marne': 398000,
    'Vendée': 685000,
    'Sarthe': 566000,
    'Morbihan': 750000,
    'Oise': 829000,
    'Vienne': 438000,
    'Haute-Savoie': 829000,
    'Doubs': 398000,
    'Gard': 748000,
    'Loiret': 680000,
    'Aude': 374000,
    'Somme': 569000,
    'Charente-Maritime': 651000,
    'Pyrénées-Atlantiques': 682000,
    'Côte-d\'Or': 534000,
    'Drôme': 517000,
    'Côtes-d\'Armor': 598000,
    'Landes': 398000,
    'Haut-Rhin': 398000,
    'Indre-et-Loire': 610000,
    'Ain': 652000,
    'Manche': 495000,
    'Aisne': 531000,
    'Mayenne': 307000,
    'Eure': 601000,
    'Orne': 279000,
    'Deux-Sèvres': 374000,
    'Tarn': 387000,
    'Yonne': 335000,
    'Ardèche': 328000,
    'Allier': 335000,
    'Cher': 302000,
    'Charente': 352000,
    'Corrèze': 239000,
    'Dordogne': 398000,
    'Gers': 191000,
    'Lot': 173000,
    'Lot-et-Garonne': 332000,
    'Pyrénées-Orientales': 479000,
    'Tarn-et-Garonne': 260000,
    'Vosges': 364000,
    'Jura': 259000,
    'Haute-Loire': 227000,
    'Haute-Marne': 172000,
    'Nièvre': 204000,
    'Saône-et-Loire': 551000,
    'Haute-Saône': 235000,
    'Ardennes': 270000,
    'Aveyron': 279000,
    'Cantal': 144000,
    'Creuse': 116000,
    'Eure-et-Loir': 390000,
    'Indre': 217000,
    'Loir-et-Cher': 329000,
    'Lozère': 76000,
    'Hautes-Alpes': 141000,
    'Alpes-de-Haute-Provence': 164000,
    'Ariège': 153000,
    'Corse-du-Sud': 158000,
    'Haute-Corse': 182000,
    'Hautes-Pyrénées': 229000,
    'Territoire de Belfort': 141000,
    'Meuse': 184000,
    'Haute-Vienne': 374000,
    'Guadeloupe': 384000,
    'Martinique': 364000,
    'Guyane': 290000,
    'Réunion': 860000,
    'Mayotte': 270000,
}

import re
import unicodedata


def normaliser(s):
    return re.sub(r'\s+', ' ', s or '').strip()


def normaliser_comparaison(s):
    """
    Normalise pour comparaison robuste :
    - minuscules ;
    - accents supprimés ;
    - apostrophes typographiques uniformisées ;
    - espaces normalisés.
    """
    s = s or ""
    s = s.replace("’", "'").replace("`", "'")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    return normaliser(s)


# Les libellés sont examinés du plus long au plus court.
# Cela évite par exemple les ambiguïtés sur les noms composés.
_DEPARTEMENTS_NORMALISES = sorted(
    (
        (normaliser_comparaison(nom), nom)
        for nom in DEPARTEMENTS
    ),
    key=lambda x: len(x[0]),
    reverse=True
)


# Détection du type de direction.
RE_DDETSPP_TITRE = re.compile(
    r"direct(?:eur|rice)\s+departemental(?:e)?\s+"
    r"de\s+l[' ]emploi,?\s+du\s+travail,?\s+des\s+solidarites\s+"
    r"et\s+de\s+la\s+protection\s+des\s+populations",
    re.IGNORECASE
)

RE_DDETS_TITRE = re.compile(
    r"direct(?:eur|rice)\s+departemental(?:e)?\s+"
    r"de\s+l[' ]emploi,?\s+du\s+travail\s+et\s+des\s+solidarites"
    r"(?!\s+et\s+de\s+la\s+protection\s+des\s+populations)",
    re.IGNORECASE
)

RE_DDPP_TITRE = re.compile(
    r"direct(?:eur|rice)\s+departemental(?:e)?\s+"
    r"de\s+la\s+protection\s+des\s+populations",
    re.IGNORECASE
)


def trouver_departement(texte):
    """
    Retourne exclusivement un département officiel de DEPARTEMENTS,
    ou None si aucun nom connu n'est présent.
    """
    texte_normalise = normaliser_comparaison(texte)

    for nom_normalise, nom_canonique in _DEPARTEMENTS_NORMALISES:
        # Évite de reconnaître une sous-chaîne au milieu d'un mot.
        pattern = (
            r"(?<![a-z0-9])"
            + re.escape(nom_normalise)
            + r"(?![a-z0-9])"
        )

        if re.search(pattern, texte_normalise, re.IGNORECASE):
            return nom_canonique

    return None


def classifier_poste_ddets_ddpp(texte):
    """
    Retourne (type_poste, territoire, grade) ou None.

    type_poste : ddets / ddpp / ddetspp
    territoire : libellé strictement issu de DEPARTEMENTS
    grade      : volontairement vide tant qu'un parseur dédié n'est pas fiabilisé
    """
    if not texte:
        return None

    texte_normalise = normaliser_comparaison(texte)

    # Toujours le type le plus spécifique en premier.
    if RE_DDETSPP_TITRE.search(texte_normalise):
        type_poste = "ddetspp"
    elif RE_DDETS_TITRE.search(texte_normalise):
        type_poste = "ddets"
    elif RE_DDPP_TITRE.search(texte_normalise):
        type_poste = "ddpp"
    else:
        return None

    territoire = trouver_departement(texte_normalise)

    # Sécurité essentielle : aucun faux territoire ne doit entrer dans l'état.
    if not territoire:
        return None

    # Paris est explicitement déclaré comme organisation spécifique chez vous.
    if territoire in TERRITOIRES_ORGANISATION_SPECIFIQUE:
        return None

    # À améliorer ultérieurement avec un parseur dédié ; mieux vaut vide que faux.
    grade = ""

    return type_poste, territoire, grade

def get_type_organisation(territoire):
    """Détermine l'organisation applicable au territoire."""

    # Paris, petite couronne et outre-mer : organisation hors modèle
    # métropolitain DDETS / DDPP / DDETSPP.
    if territoire in TERRITOIRES_SANS_DDETS:
        return 'organisation_locale_specifique'

    pop = POPULATION_DEPARTEMENTS.get(territoire, 0)
    return 'ddets_ddpp_separees' if pop >= 400000 else 'ddetspp_fusionnee'

# Départements avec organisation spécifique (pas de DDETS/DDPP/DDETSPP)
TERRITOIRES_ORGANISATION_SPECIFIQUE = {}

# Territoires pour lesquels il n'existe pas de DDETS départementale autonome.
#
# Pour Paris et la petite couronne, les missions relèvent de l'organisation
# territoriale propre de la DRIEETS Île-de-France.
#
# En outre-mer, l'organisation des services de l'État ne correspond pas au
# schéma métropolitain DDETS / DDPP / DDETSPP.
TERRITOIRES_SANS_DDETS = {
    "Paris": "Organisation locale spécifique : compétences emploi, travail et solidarités exercées dans le cadre de la DRIEETS Île-de-France.",
    "Hauts-de-Seine": "Organisation locale spécifique : compétences emploi, travail et solidarités exercées dans le cadre de la DRIEETS Île-de-France.",
    "Seine-Saint-Denis": "Organisation locale spécifique : compétences emploi, travail et solidarités exercées dans le cadre de la DRIEETS Île-de-France.",
    "Val-de-Marne": "Organisation locale spécifique : compétences emploi, travail et solidarités exercées dans le cadre de la DRIEETS Île-de-France.",

    "Guadeloupe": "Organisation locale spécifique outre-mer : pas de DDETS départementale au sens du modèle métropolitain.",
    "Martinique": "Organisation locale spécifique outre-mer : pas de DDETS départementale au sens du modèle métropolitain.",
    "Guyane": "Organisation locale spécifique outre-mer : pas de DDETS départementale au sens du modèle métropolitain.",
    "Réunion": "Organisation locale spécifique outre-mer : pas de DDETS départementale au sens du modèle métropolitain.",
    "Mayotte": "Organisation locale spécifique outre-mer : pas de DDETS départementale au sens du modèle métropolitain.",
}

MESSAGE_ORGANISATION_SPECIFIQUE = (
    "Organisation territoriale spécifique"
)