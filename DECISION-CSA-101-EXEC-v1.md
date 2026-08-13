# Décisions doctrinales — CSA-101, contrat d'exécution v1

Statut : `PROPOSED`
Date : 2026-08-11

## Contexte

`src/rocsa_generator/definitions/catalog/csa_101.json` déclare la fiche
normative (« Vérification de l'intégrité cryptographique ») depuis
2.3-B2, mais aucune logique exécutable ne l'a jamais implémentée —
signalé comme hors périmètre à chaque jalon (2.3-C1, 2.3-C2, 2.3-D
L1/L2/L3). Le module généré par L3 lève systématiquement
`ControlExecutionNotAuthorizedError`.

## D-CSA101-EXEC-01 — Localisation : source authentique, jamais dans le généré

**Décision.** La logique métier réelle vit comme code source normal,
écrit à la main, testé, revu — `src/rocsa_generator/csa_controls/csa_101.py`
— jamais comme texte templaté dans `scaffold_renderer.py`.

**Justification.** Modifier le module déjà généré par L2/L3 en ferait une
seconde source de vérité, en contradiction directe avec `SCAFFOLD-08`
(arborescence fermée) et `SCAFFOLD-16` (code humain protégé). Preuve
mécanique concrète : `writer._inspect_payload()` en mode
`REGENERATE_VERIFIED` compare le contenu existant au contenu fraîchement
rendu et refuse toute republication si les deux divergent
(`PublicationRefused: "existing content different, refusing overwrite"`)
— un module généré modifié à la main casserait donc la republication dès
le prochain run, pas seulement en théorie.

**Conséquence.** Cette décision ne dit *pas* comment le module généré
finira par appeler cette logique (import statique ? nouveau template ?) —
question distincte, à trancher séparément, une fois `execution_eligible`
elle-même réévaluée (`D-FNCSA-COMPILE-09`, toujours `False` à ce stade).
Le module `csa_controls/csa_101.py` est autonome et testable
indépendamment du pipeline de scaffold.

**Pas d'héritage `BaseCSA` legacy.** `src/rocsa/core/base_csa.py` (et le
vocabulaire `CSAStatus`/`CSAFamily`/`CSASeverity` associé) date du
commit fondateur `v0.1.0`, antérieur à toute la doctrine FN-CSA/B/C/D.
Vocabulaire incompatible avec `D-FNCSA-RESULT-01` (`SKIPPED` legacy ≠
`NOT_APPLICABLE` normatif — pas un synonyme, deux concepts différents) ;
défaut `score: float = 1.0` dangereux (succès implicite par omission,
contraire à l'échec fermé) ; chargement dynamique piloté par YAML
(`importlib.import_module` + `getattr`), incompatible avec les artefacts
déterministes de L2/L3. `src/rocsa/` reste hors du chemin d'exécution de
CSA-101, migration/dépréciation à traiter comme chantier séparé.

## D-CSA101-EXEC-02 — Contrat d'entrée, dérivé de la fiche normative

Champs `execution.inputs` de la fiche (`scientific_object`,
`reference_hash`, `declared_algorithm`) mappés directement sur les
paramètres de la fonction — aucun champ inventé, aucun renommage :

```python
def verify_integrity(
    scientific_object: Path,
    reference_hash: str,
    declared_algorithm: str,
) -> IntegrityCheckResult: ...
```

**Profil v1 — restriction volontaire, distincte de la fiche.** La fiche
laisse `declared_algorithm` générique (extensible). Le profil v1
restreint : seul `"SHA-256"` (exact, sensible à la casse) est accepté ;
toute autre valeur produit `ERROR` — jamais de déduction automatique
d'un algorithme (exclusion explicite de la fiche : *« Déduction
automatique d'un algorithme cryptographique absent »*).

**`reference_hash`** doit correspondre au motif `^[0-9a-fA-F]{64}$` —
**redéclaration locale assumée**, pas un import de `Sha256Hex` de
`compilation_artifact.py`. Un import créerait une dépendance de ce
module vers le pipeline de compilation, ce que ce document interdit
explicitement (indépendance du noyau métier, D-CSA101-EXEC-01). La
valeur identique aux deux endroits n'est pas une coïncidence à cacher :
SHA-256 fait 64 caractères hexadécimaux par construction mathématique,
pas par choix arbitraire — mais le code ne doit jamais prétendre
« réutiliser exactement » un motif qu'il redéclare en réalité (erreur
commise dans la version initiale, corrigée après revue).
Normalisation de casse acceptée : la valeur fournie est convertie en
minuscule avant comparaison — choix confirmé explicitement, normaliser
la casse d'une représentation hexadécimale est une équivalence de
représentation standard, pas une « déduction automatique d'algorithme ».
**Normalisation de casse explicitement actée** : `reference_hash` est
converti en minuscule avant validation/comparaison — une entrée en
majuscules (`"AAAA..."`) est acceptée, pas rejetée. Ce n'est pas une
« déduction automatique » interdite par la fiche (qui vise l'absence
d'algorithme, pas la représentation d'une valeur fournie) : c'est une
équivalence de représentation standard, au même titre qu'ignorer des
espaces superflus. Confirmé explicitement le 2026-08-12 après
comparaison avec une variante plus stricte (minuscule uniquement)
trouvée dans une version antérieure du module, avant tranchage.

## D-CSA101-EXEC-03 — Correspondance préconditions → états de résultat

Réutilise `ResultState` de `fn_csa.py` (`PASSED/FAILED/NOT_APPLICABLE/
ERROR`) — jamais de vocabulaire dupliqué.

| Situation | État | Justification |
|---|---|---|
| `scientific_object` absent, illisible, ou non un fichier régulier (répertoire, FIFO, etc.) | `ERROR` | Échec technique d'exécution, pas un jugement sur l'objet |
| `reference_hash` absent ou mal formé | `ERROR` | Précondition `hash_available` non satisfaite |
| `declared_algorithm` ≠ `"SHA-256"` | `ERROR` | Limite de capacité du profil v1, pas une conclusion sur l'objet |
| Empreinte calculée = `reference_hash` | `PASSED` | — |
| Empreinte calculée ≠ `reference_hash` | `FAILED` | — |

**`NOT_APPLICABLE` n'est jamais produit par CSA-101 dans ce profil v1** —
toutes ses préconditions déclarées sont des échecs d'exécution, pas des
jugements de portée (« cet objet n'a pas besoin de ce contrôle » relève
d'un orchestrateur en amont, pas de CSA-101 seul). Décision confirmée
explicitement avant implémentation.

## D-CSA101-EXEC-04 — Lecture seule stricte, protection FIFO

Aucune écriture, aucune modification de `scientific_object` (exclusion
explicite de la fiche : *« Réparation ou modification automatique de
l'objet contrôlé »*). Lecture en blocs (64 Kio), ouverture avec
`O_NONBLOCK` puis vérification `fstat` de fichier régulier avant lecture
réelle — même défense contre les FIFO qu'introduite dans `safe_fs.py`
après la revue de sécurité de L3 (un `open()` bloquant seul aurait pu
bloquer indéfiniment sur un FIFO substitué).

**Statut.** `PROPOSED`. Ne passera à `Actée` qu'une fois L4-B2 (liaison
statique au module généré), L4-B3 (génération/publication L2/L3 de bout
en bout) et L4-B4 (qualification/approbation par l'autorité scientifique)
réalisés — cette livraison ne couvre que L4-B1 (noyau métier autonome).

---

## Addendum — revue et corrections (2026-08-12)

Une revue a identifié 11 points sur la première version du module. Deux
ont été confirmés par reproduction directe avant correction (méthodologie
du projet) :

1. **Crash sur `reference_hash` de mauvais type** — `123.lower()` levait
   `AttributeError` non capturé, contredisant la garantie « ne lève
   jamais d'exception ». **Confirmé par reproduction.**
2. **Crash sur `scientific_object=None`** — `os.open(None, ...)` levait
   `TypeError`, non capturé par le `except OSError` existant (`TypeError`
   n'est pas une sous-classe d'`OSError`). **Confirmé par reproduction.**

**Corrigés, avec validation d'entrée Pydantic stricte** (`_VerifyIntegrityInput`,
vérifiée empiriquement : convertit bien tout type incorrect en
`ValidationError` capturable, y compris `None`/`int` là où l'ancienne
version plantait).

**Corrections supplémentaires, jugées fondées par simple lecture :**

3. **Hachage non réellement en flux** — l'ancienne version accumulait
   tous les blocs lus (`chunks.append`) avant de les hacher en un seul
   appel `hashlib.sha256(contenu_complet)`, annulant l'intérêt mémoire
   de la lecture par blocs pour un gros fichier. **Corrigé** :
   `digest.update()` appelé par bloc. Vérifié par un test qui espionne
   les appels `update()` (confirmant plusieurs appels ≤ 64 Kio chacun,
   jamais un seul appel avec la totalité du contenu) — et par contrôle
   négatif : la réintroduction délibérée du bug fait échouer ce test.
4. **Vecteurs de test circulaires** — les tests généraient l'empreinte
   attendue avec `hashlib.sha256()`, la même fonction que
   l'implémentation testait, prouvant seulement une cohérence interne.
   **Corrigé** : vecteurs SHA-256 normatifs fixes (chaîne vide, `"abc"`,
   valeurs FIPS 180-4 connues), indépendants de toute exécution du code
   testé.
5. **Contradiction de statut** (`PROPOSED` en tête, `Actée` en pied) —
   **corrigé**, `PROPOSED` jusqu'à L4-B2/B3/B4.
6. **Affirmation inexacte sur la réutilisation du motif SHA-256** — le
   code redéclarait localement un motif identique à `Sha256Hex` tout en
   prétendant le « réutiliser exactement ». **Corrigé** : reconnaissance
   explicite d'une redéclaration assumée, pour préserver l'indépendance
   du module (pas d'import créant une dépendance vers le pipeline de
   compilation).
7. **Symlinks non tranchés** — `os.open()` suivait un symlink terminal
   sans politique explicite. **Corrigé** : refus par défaut (`O_NOFOLLOW`),
   cohérent avec la doctrine de confinement de L3.
8. **Mutation concurrente non détectée** — un fichier modifié pendant le
   calcul pouvait produire un résultat correspondant à un état transitoire
   jamais stable. **Corrigé** : comparaison `(device, inode, taille,
   mtime_ns)` avant ouverture et après lecture ; divergence → `ERROR`.
9. **Assertions de test trop larges** — `pytest.raises(Exception)`
   resserré en `pytest.raises(ValidationError)` ; le test d'inspection
   du code source (`"NOT_APPLICABLE" not in source`) retiré, remplacé
   par la couverture comportementale déjà exhaustive des branches de la
   table de décision (aucun test, sur aucune branche, ne produit jamais
   `NOT_APPLICABLE`).

**Non retenu, avec justification** : la suggestion d'enrichir
`IntegrityCheckResult` avec des champs de forme FN-CSA complète
(`FailurePrescription`, version de profil, contexte d'exécution) a été
jugée prématurée. Précision après revue v3 : le noyau B1 n'est **pas**
totalement découplé de `fn_csa.py` — il importe déjà `ResultState`. Le
découplage porte spécifiquement sur le **pipeline de compilation**
(`CompilationArtifact`, `ScaffoldPlan`, etc.), pas sur le vocabulaire
canonique d'état lui-même. Formulation corrigée : *« Le noyau B1
réutilise seulement le vocabulaire canonique d'état. La construction du
résultat FN-CSA complet, notamment la prescription et les preuves
d'exécution, relève de l'adaptateur B2. »* Seul `bytes_read` a été
ajouté au noyau (utile à l'audit, sans coupler au pipeline de
compilation).

**Découpage adopté** (suggestion de la revue) :

| Sous-lot | Contenu | État |
|---|---|---|
| L4-B1 | Noyau SHA-256 autonome | **Livré, corrigé, 26/26 tests** |
| L4-B2 | Adaptateur statique vers le contrat FN-CSA + liaison au module généré | Non commencé |
| L4-B3 | Génération et publication de bout en bout via L2/L3 | Non commencé |
| L4-B4 | Qualification et approbation par l'autorité scientifique | Non commencé |

**Vérifié localement** : 26/26 tests passent (dont vecteurs SHA-256
normatifs, types d'entrée incorrects, symlinks, FIFO, mutation
concurrente simulée, streaming réel confirmé par contrôle négatif). Ce
module reste un noyau autonome, non relié au pipeline généré — L4-B2
reste entièrement à faire avant que CSA-101 soit exécutable dans ROCSA.

---

## Addendum 2 — troisième revue et corrections (2026-08-13)

Une troisième revue a identifié 7 points sur la v2. Les 4 principaux ont
été confirmés par reproduction directe avant correction :

1. **`re.match()` acceptait un saut de ligne final** — `$` en Python
   (sans `re.MULTILINE`) correspond aussi juste avant un `\n` final,
   donc `"a"*64 + "\n"` passait la vérification de format et produisait
   `FAILED` (comparaison échouée) plutôt qu'`ERROR` (entrée mal formée)
   — mauvaise catégorie de résultat, silencieusement. **Confirmé par
   reproduction, y compris via contrôle négatif** (réintroduction
   délibérée du bug → le nouveau test échoue bien). **Corrigé** :
   `re.fullmatch()`.
2. **Seul `os.open()` était protégé contre `OSError`** — `os.fstat`,
   `os.get_blocking`, `os.set_blocking`, `os.read`, `os.close` pouvaient
   laisser remonter une exception brute, contredisant la garantie « ne
   lève jamais ». **Confirmé par lecture de code** (absence de
   `try/except` autour de ces appels). **Corrigé** : chaque étape de
   `_hash_file_streaming` capture `OSError` explicitement ; testé en
   simulant un échec de lecture et de `fstat` via monkeypatch.
3. **Identité de fichier vérifiée via `path.stat()`, pas `fstat(fd)`** —
   rouvrir le chemin après lecture pouvait vérifier un objet différent
   de celui réellement lu si le nom avait été remplacé entre-temps.
   **Corrigé** : `_fd_identity(fd)` sur le descripteur déjà ouvert,
   avant et après lecture.
4. **`IntegrityCheckResult` acceptait des combinaisons incohérentes**
   (`PASSED` sans `computed_hash`, `ERROR` avec `computed_hash`).
   **Confirmé par construction directe du modèle.** **Corrigé** :
   validateur `@model_validator` imposant la cohérence état/empreinte,
   et rejetant explicitement `NOT_APPLICABLE` (jamais un état valide
   pour ce résultat technique, D-CSA101-EXEC-03).

**Corrections supplémentaires, jugées fondées par simple lecture :**

5. Justification du découplage reformulée (voir ci-dessus) — le noyau
   importe déjà `ResultState` de `fn_csa.py`, le découplage porte sur le
   pipeline de compilation, pas sur tout vocabulaire FN-CSA.
6. Portabilité de `O_NOFOLLOW` — repli explicite via `lstat()` manuel
   quand le drapeau est absent de la plateforme, refusant spécifiquement
   les symlinks détectés (pas tous les fichiers — un bug a été introduit
   puis corrigé pendant cette même passe : la première tentative de
   repli rejetait tout fichier régulier en l'absence d'`O_NOFOLLOW`,
   erreur immédiatement détectée en relisant le code avant livraison).
7. **Non retenu** : vecteur normatif supplémentaire (un million de
   caractères `'a'`) — jugé apportant peu au-delà des deux vecteurs déjà
   présents (chaîne vide, `"abc"`) et du test de fichier volumineux
   aléatoire (qui prouve le streaming, pas la conformité cryptographique
   — distinction déjà correctement établie par la revue elle-même).

**Vérifié localement** : 36/36 tests passent (10 nouveaux : saut de
ligne/espaces dans `reference_hash`, erreurs système simulées sur
`read`/`fstat`, cohérence du modèle de résultat sur les 4 combinaisons
état/empreinte). Contrôle négatif appliqué au correctif `fullmatch` :
confirmé que le test échoue bien quand le bug est délibérément
réintroduit.

---

## Addendum 3 — GO pour L4-B1, deux corrections mineures (2026-08-13)

Quatrième revue : GO pour l'intégration de L4-B1. Deux imperfections
mineures, non bloquantes selon la revue, corrigées quand même par
cohérence :

1. **`os.close()` non protégé dans deux chemins d'erreur de
   `_open_regular_file_no_symlink`** — une erreur exceptionnelle à la
   fermeture aurait pu remonter brute, contredisant la garantie « ne
   lève jamais ». **Corrigé** : `_close_quietly()`, utilisée
   systématiquement partout où un descripteur est fermé (y compris dans
   `_hash_file_streaming`, qui utilisait déjà ce motif localement — 
   factorisé en une seule fonction).
2. **`import threading` inutilisé** dans les tests (résidu d'une
   version antérieure du test de mutation, réécrite depuis sans
   threading réel). **Corrigé**, avec `import time` retiré au passage
   (devenu inutilisé pour la même raison).

**Point de doctrine soulevé pour B2, pas B1** : les messages d'erreur de
B1 sont actuellement du texte libre concaténé (« inaccessible, symlink,
non un fichier régulier, modifié pendant la vérification, ou erreur
système »). B2 devra introduire des codes d'erreur structurés
(`INVALID_INPUT`, `UNSUPPORTED_ALGORITHM`, `OBJECT_NOT_FOUND`,
`OBJECT_NOT_REGULAR`, `SYMLINK_REFUSED`, `READ_ERROR`, `OBJECT_MUTATED`,
`HASH_MISMATCH`) plutôt que d'analyser le texte de `detail` pour en
déduire la prescription — noté pour la décision B2, pas une exigence
rétroactive sur B1.

**Vérifié localement** : 36/36 tests toujours verts après les deux
correctifs, `python3 -m compileall -q src tests` propre.
