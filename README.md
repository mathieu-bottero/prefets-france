# 🗺️ Carte des Administrations Territoriales de France

Visualisation interactive des **préfets** et **directeurs départementaux des territoires (DDT/DDTM)** en poste dans les 101 départements français, avec mise à jour automatique depuis le flux XML du Journal Officiel.

---

## 📸 Aperçu

- Carte thématique de la France métropolitaine et de l'outre-mer
- Coloration par ancienneté en poste (< 6 mois / 6 mois–1 an / 1–2 ans / > 2 ans)
- Regroupement par **régions** ou **bassins hydrographiques**
- Dossier latéral avec titres complets, date de prise de fonction et successeur désigné
- Thème clair / sombre
- Recherchepar nom, département ou région

---

## 🏗️ Architecture du projet

```
.
├── index.html                    # Interface cartographique (D3.js)
│
├── maj_administrations.py        # 🔗 Orchestrateur : lance les deux scripts et fusionne les CSV
│
├── prefets/
│   ├── maj_base_prefets.py       # Mise à jour de la base des préfets
│   ├── poste_prefectoral.py      # Classificateur regex des postes préfectoraux (JO)
│   ├── prefet_scrapper.py        # Export brut du flux JO en CSV (debug/exploration)
│   └── data/
│       ├── base_prefets.csv      # CSV exporté (généré)
│       ├── prefets_departements.csv # CSV simplifié (généré)
│       └── etat_prefets.json     # État persistant (généré)
│
├── ddt/
│   ├── maj_base_ddt.py           # Mise à jour de la base des DDT/DDTM
│   ├── poste_ddt.py              # Classificateur regex des postes DDT/DDTM (JO)
│   ├── ddt_scrapper.py           # Export brut des nominations DDT en CSV (debug/exploration)
│   └── data/
│       ├── base_ddt.csv          # CSV exporté (généré)
│       └── etat_ddt.json         # État persistant (généré)
│
├── commun/
│   └── data/
│       ├── base_administrations.csv   # ✅ CSV fusionné (généré par l'orchestrateur)
│       ├── departements.geojson       # Géométries départementales
│       ├── regions.geojson            # Géométries régionales
│       ├── bassins.geojson            # Géométries des bassins hydrographiques
│       ├── bassin_departements.json   # Correspondances bassin ↔ départements
│       └── region_departements.json   # Correspondances région ↔ départements
│
└── requirements.txt
```

---

## ⚙️ Installation

### Prérequis

- Python 3.9+
- Un navigateur moderne (pour `index.html`)

### Dépendances Python

```bash
pip install -r requirements.txt
```

Les bibliothèques principales utilisées sont `requests`, `beautifulsoup4`, `selenium`, `pandas` et `python-dotenv`.

---

## 🚀 Utilisation

### Premier lancement (construction de l'historique complet)

```bash
python maj_administrations.py --mois 48 --init
```

Télécharge et analyse les 4 dernières années de nominations publiées au Journal Officiel. Cette opération peut prendre plusieurs minutes.

### Mise à jour hebdomadaire (usage courant)

```bash
python maj_administrations.py
```

Analyse le dernier mois par défaut, met à jour les états persistants et régénère `base_administrations.csv`.

### Options disponibles

| Option | Description |
|---|---|
| `--mois N` | Fenêtre d'analyse en mois (défaut : `1`) |
| `--sans-maj` | Fusionne uniquement les CSV existants, sans relancer les scripts sources |
| `--init-ddt` | Repart d'un état DDT vide (reconstruction complète uniquement) |
| `--script-prefets PATH` | Chemin alternatif vers le script des préfets |
| `--script-ddt PATH` | Chemin alternatif vers le script des DDT/DDTM |

### Exemples

```bash
# Analyse des 3 derniers mois
python maj_administrations.py --mois 3

# Fusion seule (pas de téléchargement)
python maj_administrations.py --sans-maj

# Reconstruction totale DDT sur 4 ans
python maj_administrations.py --mois 48 --init-ddt
```

---

## 🔄 Fonctionnement interne

### Source de données

Les nominations sont issues du flux XML ouvert **« Nominations publiées au Journal Officiel »** publié sur [data.gouv.fr](https://www.data.gouv.fr/datasets/nominations-publiees-au-journal-officiel?resource_id=1c5ac28d-92ca-4a19-aefb-63fbde4387a2). Le flux est parsé en **streaming** pour minimiser la consommation mémoire.

### Pipeline de traitement

```
Flux XML JO (data.gouv.fr)
        │
        ├─── maj_base_prefets.py ──► etat_prefets.json ──► base_prefets.csv
        │         (via poste_prefectoral.py)
        │
        └─── maj_base_ddt.py ─────► etat_ddt.json ──────► base_ddt.csv
                  (via poste_ddt.py)
                        │
                        └── maj_administrations.py ──► base_administrations.csv
```

### Classification des postes (regex)

Les fichiers `poste_prefectoral.py` et `poste_ddt.py` extraient le rôle et le territoire à partir du **texte libre** de chaque décision du JO par expressions régulières. Le texte source brut (`texte_source`) est toujours conservé dans les fichiers de sortie pour permettre une vérification manuelle.

### État persistant

Chaque base dispose d'un fichier JSON (`etat_prefets.json`, `etat_ddt.json`) qui accumule l'historique des titulaires. **Ne pas supprimer ces fichiers** entre deux exécutions hebdomadaires, au risque de perdre l'historique antérieur à la fenêtre `--mois`.

### Ancienneté et couleurs

| Couleur | Seuil |
|---|---|
| 🟢 Vert | < 6 mois (< 183 jours) |
| 🟡 Jaune | 6 mois – 1 an |
| 🟠 Orange | 1 an – 2 ans |
| 🔴 Rouge | > 2 ans |

---

## 🌐 Interface cartographique

Ouvrez `index.html` dans un navigateur (ou servez-le via un serveur local).

> ⚠️ Les fichiers GeoJSON et CSV sont chargés en `fetch`. Un serveur local est nécessaire si vous ouvrez le fichier directement depuis le système de fichiers (CORS).

```bash
# Serveur local rapide (Python)
python -m http.server 8000
# Puis ouvrir http://localhost:8000
```

### Fonctionnalités de la carte

- **Menu déroulant** : bascule entre la vue *Préfets* et *DDT/DDTM*
- **Mode Régions / Bassins** : change le découpage de regroupement affiché en surbrillance
- **Clic sur un département** : affiche le dossier complet dans le panneau latéral et zoome sur la région ou le bassin associé
- **Recherche** : filtre par nom, territoire ou code département
- **Outre-mer** : liste cliquable dans le panneau latéral (territoires non représentés sur la carte métropolitaine)
- **Thème clair/sombre** : persisté dans `localStorage`

---

## 📋 Format du CSV de sortie (`base_administrations.csv`)

Le fichier est encodé en **UTF-8 avec BOM**, délimité par `;`.

| Colonne | Description |
|---|---|
| `departement` | Code département (01–95, 2A, 2B, 971–976) |
| `territoire` | Nom du département |
| `prefet_nom_complet` | Nom complet du préfet en poste |
| `prefet_sexe` | `M` ou `F` |
| `prefet_date_decision` | Date de l'arrêté de nomination |
| `prefet_date_prise_fonction` | Date effective de prise de fonction |
| `prefet_anciennete_jours` | Ancienneté calculée en jours |
| `prefet_titre_global` | Titre(s) complet(s) séparés par ` \| ` |
| `prefet_texte_source` | Texte brut du JO |
| `ddt_type_poste` | DDT ou DDTM |
| `ddt_titulaire_nom_complet` | Nom du directeur en poste |
| `ddt_titulaire_sexe` | `M` ou `F` |
| `ddt_grade` | Grade du fonctionnaire |
| `ddt_date_decision` | Date de l'arrêté |
| `ddt_date_prise_fonction` | Date effective de prise de fonction |
| `ddt_anciennete_jours` | Ancienneté en jours |
| `ddt_titulaire_designe_nom_complet` | Successeur désigné (si applicable) |
| `ddt_titulaire_designe_date_prise_fonction` | Date de prise de fonction du successeur désigné |
| `ddt_statut` | `poste recensé` / `poste vacant ou inconnu` / `non concerné par une DDT/DDTM` |
| `ddt_message` | Message informatif complémentaire |
| `ddt_texte_source` | Texte brut du JO |

---

## ⚠️ Limites connues

- La classification des postes repose sur des **expressions régulières** appliquées à du texte libre : des erreurs d'interprétation sont possibles, notamment pour les libellés atypiques du JO. Le champ `texte_source` est toujours disponible pour vérification.
- **Paris** (75), les **Hauts-de-Seine** (92), la **Seine-Saint-Denis** (93), le **Val-de-Marne** (94) et les territoires d'outre-mer ne disposent pas de DDT/DDTM au sens du flux étudié.
- Le flux JO ne couvre que les nominations publiées ; les postes antérieurs à la fenêtre d'initialisation `--mois` ne sont pas retrouvés a posteriori.
- Les **préfets de région** et **de zone** sont traités dans `base_prefets.csv` mais ne sont pas fusionnés dans `base_administrations.csv` (qui ne retient que les préfets départementaux).

---

## 🗓️ Automatisation (cron)

Exemple de tâche cron pour une mise à jour chaque lundi à 6h00 :

```cron
0 6 * * 1 cd /chemin/vers/le/projet && python maj_administrations.py --mois 1
```

---

## 📦 Dépendances principales

| Bibliothèque | Usage |
|---|---|
| `requests` | Téléchargement du flux XML du JO |
| `beautifulsoup4` / `selenium` | Scraping complémentaire éventuel |
| `pandas` | Manipulation de données tabulaires |
| `D3.js v7` | Rendu cartographique (front-end) |
| `Turf.js v6` | Calculs géospatiaux (front-end) |

---

## 📄 Licence

Ce projet est à usage interne / personnel. Les données nominatives proviennent du **Journal Officiel de la République française**, source officielle et publique.