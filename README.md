# Base nationale des préfets et préfètes

Périmètre volontairement restreint au titre de **préfet(ète)** lui-même — départemental,
de région, de zone de défense et de sécurité. Les sous-préfets, directeurs de cabinet,
SGAR, etc. ont été testés (voir plus bas) mais écartés : le texte du JO y est plus
composite (plus de grades à distinguer : substitut, adjoint, vice-, avocat général...)
et le risque de confondre un titulaire et son adjoint plus élevé.

## Fichiers

- **`poste_prefectoral.py`** — module qui déduit, à partir du texte libre du JO, quel(s)
  poste(s) préfectoral(aux) une décision concerne (préfet, préfet de région, préfet de
  zone de défense, sous-préfet d'arrondissement, directeur de cabinet, chargé de mission
  auprès du préfet, secrétaire général de préfecture, SGAR, adjoint au SGAR).
- **`maj_base_prefets.py`** — script principal : télécharge les décisions du JO, les
  classe avec le module ci-dessus, met à jour un état persistant et exporte un CSV lisible.
  **Remplace `prefet_scrapper.py`** pour cet usage (il en réutilise la logique de
  téléchargement, mais avec la classification par poste en plus).
- **`etat_prefets.json`** — fichier d'état persistant. **Ne pas supprimer entre deux
  exécutions hebdomadaires** : c'est lui qui porte l'historique complet.
- **`base_prefets.csv`** — export lisible, régénéré à chaque exécution à partir de
  `etat_prefets.json`. C'est ce fichier que la hiérarchie consulte.

## Usage

**Premier lancement** (pour constituer un historique complet — un département dont le
préfet a été nommé il y a 2 ans n'apparaîtra pas si on ne regarde qu'un mois en arrière) :

```
python3 maj_base_prefets.py --mois 36 --init
```

**Lancements hebdomadaires suivants** (cron), sans `--init` pour conserver l'état :

```
python3 maj_base_prefets.py --mois 1
```

La fenêtre `--mois 1` en routine hebdomadaire donne une bonne marge de sécurité (le
traitement est idempotent : reclasser un événement déjà connu ne change rien, grâce au
suivi des `source_id` déjà traités).

Exemple de tâche cron (tous les lundis à 6h) :
```
0 6 * * 1 cd /chemin/vers/prefets && python3 maj_base_prefets.py --mois 1 >> maj.log 2>&1
```

## Ce que la base contient, poste par poste

- `titulaire_actuel` : la personne en fonction aujourd'hui (nom, sexe, date de la
  décision JO, date de prise de fonction).
- `titulaire_designe` : une nomination déjà publiée au JO mais dont la prise de
  fonction est encore à venir (utile pour anticiper un changement).
- `historique` : les titulaires précédents.
- `texte_source` : le texte brut du JO ayant servi à la classification — **toujours
  conservé pour vérification manuelle**.

## Limites importantes à connaître

1. **Classification par expressions régulières sur du texte libre, pas par un
   identifiant structuré.** Le JO ne fournit pas de champ "poste" propre : le script
   déduit le poste du texte de la décision. Sur l'échantillon d'1 mois fourni, la
   classification préfet/préfète (départemental, région, zone) s'est révélée fiable une
   fois les pièges d'accord (préfet/préfète) et de confusion avec le supérieur
   hiérarchique corrigés. `texte_source` reste toujours gardé en clair dans le CSV,
   pour qu'un doute se vérifie d'un coup d'œil plutôt que de rester invisible.
2. **Pas de fusion de doublons entre libellés de territoire légèrement différents**
   (ex. un jour le JO écrit "Hauts-de-France", un autre jour "région des
   Hauts-de-France"). Le nettoyage actuel gère les cas rencontrés dans l'échantillon,
   mais un contrôle visuel du CSV de temps en temps reste utile.
3. **Cessations de fonction "orphelines"** : si quelqu'un quitte un poste alors que sa
   prise de fonction remonte à avant le début de l'historique constitué (premier lancement
   avec une fenêtre trop courte), le départ est bien enregistré mais sans titulaire
   précédent à raccrocher — c'est pour cela qu'il vaut mieux démarrer avec un historique
   long (`--mois 36`, voire plus).
4. **Les nominations/cessations de préfets titulaires sont des événements rares** (une
   grosse centaine de postes au total en France, turnover plus lent que les sous-préfets).
   Sur l'échantillon d'1 mois fourni, **aucun** événement n'entrait dans le périmètre
   retenu (préfet/préfète) — ce n'est pas un bug, juste le signe qu'un mois est trop
   court pour voir ce niveau de la hiérarchie bouger. C'est justement pour ça que le
   tout premier lancement doit utiliser un historique long (`--mois 36`).

## Pourquoi sous-préfets/directeurs de cabinet/SGAR ont été écartés

Testés sur le même échantillon : le texte du JO y combine souvent plusieurs titres pour
la même personne en une seule phrase (ex. "Substitute du procureur général... |
procureure de la République..." dans le cas — comparable — des magistrats), avec des
formes masculin/féminin (substitut/substitute, adjoint/adjointe, vice-) qu'il faut toutes
couvrir séparément sous peine de confondre un titulaire avec son adjoint. Risque jugé
trop élevé pour une first version fiable ; à reprendre plus tard si besoin, avec le même
niveau d'exigence que pour les préfets.
