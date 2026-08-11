# Décisions doctrinales — 2.3-D-L4-A (protocole de benchmark)

Statut : `PROPOSED`
Date : 2026-08-11

## Contexte

`D-SCAFFOLD-20` exige : *« Preuve reproductible. Un vecteur réel et un
protocole de benchmark accompagnent le contrat. »* Les tests de fumée déjà
écrits pour L2 (`test_smoke_performance_100_real_c2_artifacts`) et le
scénario L3 le disent eux-mêmes explicitement : *« Garde-fou de fumée, pas
un protocole statistique (celui-ci est D-L4). »* Cette décision comble ce
manque.

## D-SCAFFOLD-27 — Protocole de benchmark statistique reproductible

**Décision.** Un script dédié (`benchmark.py`) mesure séparément deux
chemins critiques, jamais mélangés dans une même statistique :

1. **Rendu pur (L2)** — `build_scaffold_plan()` + `render_scaffold()`, en
   mémoire, sans I/O.
2. **Publication réelle (L3)** — `publish_scaffold()` en mode
   `CREATE_ONLY`, sur un répertoire temporaire réel, incluant l'ouverture
   du descripteur racine, le verrou, l'écriture atomique et le `fsync`.

Séparer les deux est nécessaire : L2 est purement CPU/mémoire, L3 dépend
du sous-système de fichiers et du disque — les fusionner produirait une
statistique ne représentant fidèlement ni l'un ni l'autre.

**Méthodologie statistique :**
- **1000 tirages** par chemin mesuré (pas 100 comme les smoke tests — un
  échantillon plus large resserre l'intervalle de confiance du p95/p99).
- **10 tirages d'échauffement** exclus du calcul (JIT du bytecode Python,
  cache disque du premier accès) — mesurés mais non comptabilisés.
- Chaque tirage chronométré individuellement (`time.perf_counter()`),
  jamais un temps cumulé divisé après coup — cohérent avec la pratique
  déjà en place dans les smoke tests.
- Rapporte **médiane, p95, p99, min, max**, pas seulement une moyenne
  (une moyenne masque les valeurs aberrantes qui comptent le plus pour un
  writer transactionnel).

**Exigence d'exécution.** Ce protocole doit être exécuté sur le VPS
cible, ou sur un environnement de qualification matériellement
représentatif, **hors chemin des données et services de production** —
jamais dans un environnement de développement local ou un bac à sable de
vérification, qui ne garantit rien sur le comportement réel. La
publication L3 utilise des répertoires temporaires isolés
(`tempfile.TemporaryDirectory`), donc n'écrit jamais dans l'arborescence
réelle du projet — mais sollicite réellement le disque et les `fsync` de
la machine, d'où la nécessité d'un environnement représentatif.

**Méthode de percentile.** Rang le plus proche par excès (« nearest-rank
», arrondi au plafond) : `index = ceil(p/100 * n) - 1`, borné à
`[0, n-1]`. Choix déterministe et documenté explicitement — plusieurs
définitions du p95/p99 existent (interpolation linéaire, rang inférieur,
etc.), et sans préciser laquelle est utilisée, deux implémentations du
même protocole produiraient des chiffres différents pour le même
échantillon.

**Deux modes d'exécution.** `--official` fige les paramètres à 1000
tirages + 10 d'échauffement (seule configuration reconnue comme
protocole canonique D-SCAFFOLD-27) et **refuse de s'exécuter si le
dépôt git contient des modifications non commitées** — un run officiel
sur un état non reproductible n'aurait aucune valeur de référence. Tout
autre paramétrage est explicitement marqué `"protocol_official_run":
false` dans le rapport — exploratoire, jamais cité comme référence.

**Reproductibilité.** Le rapport de sortie inclut : version Python,
version de `rocsa-generator`, plateforme, nombre de cœurs CPU, charge
système initiale (`os.getloadavg()`), horodatage à la microseconde,
commit git + branche + état propre/sale, métadonnées disque (espace
total/utilisé/libre, répertoire temporaire utilisé). Sans ces
métadonnées, un chiffre de performance ne peut être ni reproduit ni
invalidé par un run ultérieur.

**Pas de seuil de blocage automatique dans cette version.** Le protocole
mesure et documente, il ne fait pas encore échouer la CI sur une
régression de performance — introduire un seuil sans historique de
plusieurs runs produirait un seuil arbitraire. Une fois plusieurs
exécutions officielles accumulées, une décision doctrinale ultérieure
pourra introduire un seuil de régression.

**Sortie.** Rapport JSON structuré, écrit en **mode création exclusive**
(jamais d'écrasement silencieux, y compris en cas de collision de nom
entre deux runs très rapprochés — un suffixe numérique croissant est
ajouté dans ce cas), versionné à la main dans `benchmarks/`, pour
constituer un historique de référence au fil du temps.

**Statut.** `PROPOSED` — passera à `Actée` après la première exécution
officielle réussie sur le VPS cible et revue de ses résultats.

---

## Addendum — revue et corrections (2026-08-11)

Une revue a identifié 9 points sur la première version du protocole.
Deux ont été reproduits et confirmés avant correction (méthodologie du
projet, cf. revues L3) :

1. **Écrasement silencieux confirmé** — `Path.write_text()` n'offre
   aucune garantie anti-collision malgré la promesse « jamais écrasé »
   du texte original. **Corrigé** : écriture via `os.O_CREAT | O_EXCL`,
   suffixe numérique croissant en cas de collision.
2. **Crash sur échantillon vide confirmé** — `--iterations 0` ou
   `--iterations -1` provoquait un `IndexError` brut plutôt qu'un refus
   explicite. **Corrigé** : `validate_parameters()` dédiée, levée avant
   toute mesure, avec message clair et code de sortie 2.

Corrections supplémentaires apportées sans reproduction préalable
(revue jugée suffisamment fondée par simple lecture) :
3. `git_dirty`/`git_branch` ajoutés aux métadonnées ; `--official`
   refuse désormais un dépôt sale.
4. Doctrine d'exécution reformulée (« VPS cible ou environnement de
   qualification représentatif », pas « uniquement production »).
5. Métadonnées système enrichies : version `rocsa-generator`, charge
   système initiale, espace disque, fichiers par itération, mode
   d'écriture, statut de réussite.
6. Méthode de percentile explicitée (nearest-rank, ceiling) et
   documentée dans ce fichier et dans le docstring du module.
7. Suite de tests ajoutée (`tests/test_benchmark.py`, 12 tests) :
   percentile, stats, validation de paramètres, non-écrasement, repli
   git gracieux — vérifiés localement avant livraison.
8. `import shutil` désormais utilisé (métadonnées disque) ; variable
   `manifest` renommée `_manifest` (non exploitée après l'assertion de
   succès).

**Vérifié localement** : 12/12 tests passent, script fonctionnel en
mode exploratoire et refuse correctement les paramètres invalides et
les runs `--official` sur dépôt sale. Le run officiel (1000+10) reste à
exécuter sur le vrai VPS pour valider le protocole en conditions réelles
avant de passer ce document à `Actée`.
