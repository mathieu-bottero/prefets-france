# -*- coding: utf-8 -*-
"""
Classification des postes préfectoraux (préfet, préfet de région, préfet de zone,
sous-préfet d'arrondissement, directeur de cabinet, chargé de mission auprès du préfet,
secrétaire général de préfecture, SGAR) à partir du texte libre du Journal Officiel.

Approche : le texte n'étant pas structuré, on utilise des expressions régulières
"best effort". Le texte brut est toujours conservé en parallèle dans la base
pour permettre une vérification manuelle en cas de doute — voir README.
"""

import re

def normaliser(s):
    return re.sub(r'\s+', ' ', s or '').strip()

def nettoyer_territoire(t):
    t = normaliser(t)
    t = re.sub(r"\s*\(groupe [IVX]+\)\s*$", "", t, flags=re.IGNORECASE)
    t = t.rstrip(' .')
    # certains textes du JO redoublent l'article dans le nom capturé
    # (ex: "de la région des Hauts-de-France") -> on l'enlève
    t = re.sub(r"^(?:des|de\s+la|de\s+l['’]|du|d['’])\s+", "", t, flags=re.IGNORECASE)
    return t.strip()

BOUNDARY = r"(?=,|\||\(groupe|pour une durée|avec une période|$)"

# préfet/préfète, mais jamais la sous-chaîne "préfet(e)" à l'intérieur de "sous-préfet(e)"
PREF = r"(?<!sous[- ])préf(?:et|ète)"
SPREF = r"sous-préf(?:et|ète)"

# formes longues avant "de" seul, sinon "de" absorbe "de la"/"de l'" à tort
ARTICLE = r"(?:de\s+la|de\s+l['’]|d['’]|des|du|de)"

RE_REGION = re.compile(PREF + r"\s+de\s+la\s+région\s+(.+?)" + BOUNDARY, re.IGNORECASE)
RE_ZONE = re.compile(PREF + r"\s+de\s+la\s+zone\s+de\s+défense\s+et\s+de\s+sécurité\s+(.+?)" + BOUNDARY, re.IGNORECASE)
RE_DEPT = re.compile(
    PREF + r"\s+" + ARTICLE +
    r"\s*(?!région\b)(?!zone\s+de\s+défense)(.+?)" +
    BOUNDARY,
    re.IGNORECASE
)
RE_SOUS_PREFET_ARR = re.compile(SPREF + r"\s+" + ARTICLE + r"\s*(.+?)" + BOUNDARY, re.IGNORECASE)
RE_SG_PREFECTURE = re.compile(r"secrétaire\s+générale?\s+de\s+la\s+préfecture\s+" + ARTICLE + r"\s*(.+?)" + BOUNDARY, re.IGNORECASE)

ANCHOR_DIRECTEUR_CABINET = re.compile(
    r"direct(?:eur|rice)(?:\s+adjoint[e]?)?\s+de\s+cabinet",
    re.IGNORECASE
)
ANCHOR_CHARGE_MISSION = re.compile(r"chargée?\s+de\s+mission\s+auprès\s+du\s+" + PREF, re.IGNORECASE)
ANCHOR_SGAR_ADJOINT = re.compile(r"adjoint[e]?\s+au\s+secrétaire\s+général\s+pour\s+les\s+affaires\s+régionales", re.IGNORECASE)
ANCHOR_SGAR = re.compile(r"secrétaire\s+générale?\s+pour\s+les\s+affaires\s+régionales", re.IGNORECASE)
ANCHOR_AUPRES_GENERIQUE = re.compile(r"auprès\s+(?:du|de\s+la)\s+" + PREF, re.IGNORECASE)

# Libellés lisibles pour l'export
LIBELLES_ROLE = {
    'prefet': "Préfet(ète)",
    'prefet_region': "Préfet(ète) de région",
    'prefet_zone': "Préfet(ète) de zone de défense et de sécurité",
    'directeur_cabinet': "Directeur(rice) de cabinet du préfet",
    'sous_prefet_mission': "Sous-préfet(ète) chargé(e) de mission auprès du préfet",
    'sous_prefet_arrondissement': "Sous-préfet(ète) d'arrondissement",
    'secretaire_general_prefecture': "Secrétaire général(e) de préfecture",
    'sgar': "Secrétaire général(e) pour les affaires régionales (SGAR)",
    'sgar_adjoint': "Adjoint(e) au SGAR",
    'autre_aupres_prefet': "Autre fonction auprès du préfet (non classifiée précisément)",
}

def classifier_postes(texte):
    """Retourne une liste de (role, territoire) déduits d'un texte libre du JO.
    Un même texte peut produire plusieurs postes (ex: préfet de région + de zone + de département)."""
    if not texte:
        return []
    texte = normaliser(texte)
    resultats = []

    regions = [nettoyer_territoire(m.group(1)) for m in RE_REGION.finditer(texte)]
    zones = [nettoyer_territoire(m.group(1)) for m in RE_ZONE.finditer(texte)]
    depts = [nettoyer_territoire(m.group(1)) for m in RE_DEPT.finditer(texte)]

    # NB : les mentions "préfet de la région X" / "de la zone Y" ne sont ajoutées
    # comme poste de LA PERSONNE concernée par la décision que si elle EST
    # elle-même préfet(e) (aucune ancre "auprès du préfet"/"directeur de cabinet"
    # ci-dessous ne matche) — sinon ce ne sont que des mentions de son supérieur.
    if ANCHOR_DIRECTEUR_CABINET.search(texte):
        if depts:
            resultats.append(('directeur_cabinet', depts[-1]))
        elif regions:
            resultats.append(('directeur_cabinet', regions[-1]))
    elif ANCHOR_CHARGE_MISSION.search(texte):
        if depts:
            resultats.append(('sous_prefet_mission', depts[-1]))
        elif regions:
            resultats.append(('sous_prefet_mission', regions[-1]))
    elif ANCHOR_SGAR_ADJOINT.search(texte):
        if regions:
            resultats.append(('sgar_adjoint', regions[-1]))
    elif ANCHOR_SGAR.search(texte):
        if regions:
            resultats.append(('sgar', regions[-1]))
    elif ANCHOR_AUPRES_GENERIQUE.search(texte):
        if depts:
            resultats.append(('autre_aupres_prefet', depts[-1]))
        elif regions:
            resultats.append(('autre_aupres_prefet', regions[-1]))
    else:
        for r in regions:
            resultats.append(('prefet_region', r))
        for z in zones:
            resultats.append(('prefet_zone', z))
        for d in depts:
            resultats.append(('prefet', d))

    for m in RE_SG_PREFECTURE.finditer(texte):
        resultats.append(('secretaire_general_prefecture', nettoyer_territoire(m.group(1))))

    if not (ANCHOR_DIRECTEUR_CABINET.search(texte) or ANCHOR_CHARGE_MISSION.search(texte)):
        for m in RE_SOUS_PREFET_ARR.finditer(texte):
            resultats.append(('sous_prefet_arrondissement', nettoyer_territoire(m.group(1))))

    return resultats
