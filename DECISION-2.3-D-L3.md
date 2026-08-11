# Décisions doctrinales — 2.3-D-L3 (writer réel)

Statut : `PROPOSED`
Date : 2026-08-11

## D-SCAFFOLD-24 — Le manifeste final ne réutilise jamais `publication_ready`

**Contexte.** `ManifestDraft.publication_ready` (2.3-D-L2) est verrouillé à
`False` par contrat de schéma (`const: false`) : c'est un brouillon, jamais
publiable. L3 produit un manifeste *final*, une fois l'écriture réellement
effectuée sur disque — une notion différente de « publiable ».

**Risque identifié.** Réutiliser `publication_ready` avec un sens différent
selon qu'on lit un `ManifestDraft` (L2) ou un manifeste final (L3) reproduit
exactement le type de confusion déjà corrigé deux fois pendant la revue de
L2 (deux définitions différentes portant le même nom).

**Décision.** Le manifeste final introduit un champ distinct,
`write_completed: bool`, qui signifie uniquement « l'écriture transactionnelle
de ce lot a réussi et a été publiée atomiquement sur disque ». Il ne dit rien
sur la validation scientifique, la publication CSA, ni l'autorité
d'exécution — ces trois axes restent portés par `authority.*`, inchangé et
toujours `False` à ce stade du projet (D-SCAFFOLD-02 : générable ne veut
dire ni validé ni publiable).

## D-SCAFFOLD-25 — Protocole d'écriture sûr contre TOCTOU

**Décision.** Toute écriture de fichier par L3 suit ce protocole, sans
exception :

1. **Marche composant par composant** depuis la racine du projet, avec
   `os.open(nom, flags, dir_fd=parent_fd)` où `flags` inclut `O_NOFOLLOW`.
   Aucun composant du chemin ne peut être un symlink — rejet immédiat si
   rencontré, à n'importe quel niveau (SCAFFOLD-15).
2. **Écriture en fichier temporaire** dans le même répertoire que la cible
   (`O_CREAT | O_EXCL | O_WRONLY`), jamais directement sur le chemin final.
3. **`fsync`** du descripteur avant fermeture, pour garantir la durabilité
   avant toute visibilité du nom final.
4. **Revérification au dernier moment** : juste avant `os.replace()`, on
   relit l'état de la cible (`os.lstat` avec `dir_fd`) pour confirmer qu'elle
   correspond toujours à l'attente du mode (absente pour `CREATE_ONLY`,
   présente avec l'empreinte attendue pour `REGENERATE_VERIFIED`).
5. **`os.replace()` atomique** (même système de fichiers, donc atomique sur
   POSIX) pour publier le fichier temporaire sous son nom final.

**Explicitement interdit** : `shutil.copy*`, `Path.write_text/write_bytes`,
`open()` de haut niveau sans `dir_fd`/`O_NOFOLLOW` — aucun de ces appels
n'offre les garanties ci-dessus.

**Statut.** Actée. Débloque l'implémentation de L3.

---

## D-SCAFFOLD-26 — Verrou coopératif pour sérialiser les writers ROCSA

**Contexte.** La revue de sécurité du 2026-08-11 a identifié une fenêtre
TOCTOU résiduelle au rollback : entre la vérification d'ownership
(`lstat` comparé à `(device, inode)` publiés) et la suppression
(`unlink`), un processus concurrent peut remplacer la cible. Aucune
primitive POSIX standard ne permet une suppression atomique
« si-et-seulement-si l'inode correspond toujours ».

**Décision.** `publish_scaffold()` acquiert un verrou exclusif
(`flock(root_fd, LOCK_EX)`) sur le descripteur de la racine du projet
avant toute inspection ou écriture, et le libère dans tous les cas
(`finally`) — y compris en cas de refus dès la phase d'inspection, avant
toute écriture.

**Garantie.** Sérialise tous les appels à `publish_scaffold()` qui
acquièrent ce verrou : deux runs concurrents sur la même racine ne
s'exécutent jamais en parallèle. Réduit la fenêtre TOCTOU du rollback à
néant *entre écrivains ROCSA coopératifs*.

**Limite explicite, jamais à oublier.** `flock` est un verrou
*consultatif* (advisory) : il ne protège que contre les processus qui
l'acquièrent aussi. Un script qui écrit directement dans l'arborescence
sans passer par `publish_scaffold()` — manuellement, ou via un futur
outil qui oublierait d'acquérir ce verrou — n'est pas bloqué et peut
provoquer exactement la course que le verrou est censé éliminer. **Toute
future écriture dans cette arborescence (L4, CLI, script d'exploitation)
DOIT acquérir ce même verrou** pour bénéficier de la garantie. Cette
contrainte doit être rappelée dans la documentation de tout futur point
d'entrée touchant à `src/rocsa_generator/generated/` ou `tests/generated/`.

**Vérification.** Deux propriétés testées séparément :
1. Le verrou est libéré même si l'inspection refuse la publication avant
   toute écriture (pas de verrou orphelin sur un simple refus).
2. Une seconde tentative d'acquisition (`LOCK_EX | LOCK_NB`) échoue tant
   que le premier détenteur n'a pas libéré — preuve que le verrou
   sérialise réellement, pas seulement une déclaration d'intention.

**Statut.** Actée.

---

## Note de vérification

Contrairement à L2 (pur, testé en mémoire), L3 opère réellement sur
disque : les tests (`tests/test_writer.py`) exercent le vrai comportement
sur système de fichiers réel (`tmp_path` pytest) — création, refus,
rollback, rejet de symlink — pas une simulation.

**Incident corrigé pendant la vérification locale** : le test de rollback
utilisait initialement `chmod` pour forcer un échec d'écriture (répertoire
en lecture seule). Ce déclencheur est invalide si les tests tournent en
`root` (cas du VPS actuel) — `root` contourne les bits de permission
POSIX, donc le test passait silencieusement sans jamais exercer le
chemin de rollback qu'il prétendait couvrir. Corrigé via un monkeypatch
déterministe sur `stage_and_publish`, indépendant du contexte
d'exécution (`root` ou non).

**Ce paquet n'est pas autonome**, comme L2 : `writer.py`/`writer_models.py`
dépendent de `scaffold_models.py`/`canonical.py` (2.3-D-L2) et de
`rocsa_generator.models` (2.3-C1/C2), déjà présents sur `main`. À
décompresser dans le dépôt, pas installer isolément.

---

## Addendum — revue de sécurité et corrections (2026-08-11)

Une revue de sécurité externe a rendu un verdict **NO-GO** sur la première
version de L3, avec 6 points majeurs/critiques et une liste de tests
adversariaux manquants. Deux des points critiques ont été reproduits et
confirmés avant correction (méthodologie du projet : vérification par
exécution réelle, jamais par confiance).

### Corrections apportées

1. **Échappement de racine via `..`** (critique, confirmé par
   reproduction) — `safe_fs.py` faisait confiance à L2 pour ne jamais
   fournir de chemin dangereux. `os.open("..", dir_fd=...)` réussit
   normalement (`..` est une vraie entrée de répertoire, pas un
   symlink — `O_NOFOLLOW` ne le bloque pas). **Corrigé** : validation
   défensive indépendante (`_validate_relative_path`) en tête de chaque
   fonction publique de `safe_fs.py`, rejetant `..`, `.`, composants
   vides, chemins absolus, octets nuls, antislash.

2. **Le préflight en lecture seule créait des répertoires** (majeur,
   confirmé par reproduction) — `lstat_leaf`/`read_leaf_nofollow`
   partageaient la même marche que l'écriture, qui appelait `os.mkdir()`
   sur les composants manquants. **Corrigé** : deux marches distinctes,
   `_walk_parent_inspect` (jamais de création, utilisée en phase
   d'inspection) et `_walk_parent_ensure` (peut créer, réservée à
   `stage_and_publish`).

3. **Fenêtre TOCTOU entre `lstat` et `os.replace()`** (critique) —
   **Corrigé** : `stage_and_publish` n'est plus jamais un "replace" (en
   pratique, la phase d'inspection garantit déjà qu'on n'atteint cette
   fonction que sur une cible absente, mode confondu). Publication via
   `os.link()` (linkat) : succès ou `FileExistsError` en un seul appel
   système atomique, sans vérification séparée de l'action.

4. **Rollback vulnérable à une course** (majeur) — **Corrigé** :
   `stage_and_publish` retourne `(device, inode)` de l'objet publié ;
   `remove_leaf_if_owned` vérifie cette identité exacte avant toute
   suppression, refuse (`OWNERSHIP_LOST`) si la cible ne correspond plus
   — jamais supprimer l'objet d'un tiers.

5. **`os.write()` peut écrire partiellement** (majeur) — **Corrigé** :
   `_write_all` boucle jusqu'à écriture intégrale.

6. **Lecture non validée contre les fichiers spéciaux** (mineur à la
   revue, **révélé plus grave en le corrigeant** : `os.open()` seul,
   même en lecture, **bloque indéfiniment** à l'ouverture d'un FIFO sans
   écrivain — une vérification `fstat()` après coup n'aide pas, le
   blocage survient avant. **Corrigé** : ouverture avec `O_NONBLOCK`,
   `fstat` pour confirmer un fichier régulier, repli en lecture standard
   ensuite.

7. **Atomicité du lot complet** — non corrigé, contesté avec la doctrine
   existante : `D-SCAFFOLD-13` autorise déjà explicitement l'absence de
   "promesse de visibilité globale instantanée", tout en exigeant
   "aucun état partiel après retour géré" — garanti par le rollback
   vérifié (point 4).

8. **Tests adversariaux** — ajoutés : chemins `..`/absolus/composants
   vides (paramétré), préflight non-mutant, apparition concurrente
   rejetée atomiquement, perte d'ownership au rollback, écriture
   partielle simulée, FIFO, rollback de répertoire vide, absence de
   résidus temporaires. Suite passée de 9 à 28 tests, tous sur système
   de fichiers réel.

### Point non traité, accepté comme dette documentée

Rollback des répertoires : supprime uniquement si encore vide au moment
du rollback (comportement sûr — ne détruit jamais un contenu déposé par
un tiers pendant la fenêtre du run), mais reste une opération best-effort
sans vérification d'ownership aussi stricte que pour les fichiers
(un répertoire n'a pas d'empreinte de contenu comparable à un inode de
fichier régulier). Jugé acceptable : l'échec de ce nettoyage laisse au
pire un répertoire vide orphelin, jamais une perte de données ni une
incohérence de sécurité.

---

## Note de clôture (2026-08-11)

Cette livraison reprend le code déjà revu et validé (deux passes de revue
de sécurité externe, deux bugs critiques confirmés puis corrigés à
chaque passe), auquel s'ajoutent uniquement les deux éléments qui
manquaient encore pour clore le point 1 de la deuxième revue (rollback
vulnérable au TOCTOU) : la décision D-SCAFFOLD-26 ci-dessus, et deux
tests qui exercent réellement le verrou (pas seulement sa présence dans
le code) — dont un test de contrôle négatif qui échoue quand le verrou
est désactivé, confirmant que ces tests détectent effectivement une
régression plutôt que de passer par accident.

**Suite complète vérifiée localement, sur système de fichiers réel** :
35/35 tests passent (31 hérités + 4 nouveaux sur le verrou), plus
demo.py/demo_writer.py exécutés avec succès sur le vrai vecteur CSA-101.

**Ce paquet n'est pas autonome** : writer.py/writer_models.py/safe_fs.py
dépendent de scaffold_models.py/scaffold_planner.py/scaffold_renderer.py/
canonical.py (2.3-D-L2) et de rocsa_generator.models (2.3-C1/C2), déjà
présents sur main. À décompresser dans le dépôt, jamais installer
isolément — et ne jamais écraser src/rocsa_generator/__init__.py ni
src/rocsa_generator/models/__init__.py avec une version tierce sans
`git diff` préalable : ces deux fichiers portent des exports historiques
(legacy runtime, modèles CSA) qui ne doivent jamais être perdus par
écrasement.
