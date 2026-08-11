# Analyse et démonstration — 2.3-D-L2-v2

## Non-conformité corrigée

La première L2 réintroduisait quatre écarts déjà interdits par
`D-SCAFFOLD-21` : vocabulaire de statut inventé, version source limitée au
SemVer d'outillage, famille `CRYPTO` au lieu de `CSA-100`, et artefact C2
reconstruit manuellement dans les preuves.

La v2 supprime le modèle C2 parallèle. Le planificateur reçoit directement le
`CompilationArtifact` défini au jalon C2. La démonstration suit exclusivement :

```text
csa_101.json réel
  -> FNCsaDefinition
  -> compile_contract_only() [C1]
  -> compile_artifact() [C2]
  -> build_scaffold_plan() [D-L2]
  -> render_scaffold() [D-L2]
```

## Résultats attendus du vecteur réel

```text
control_id       CSA-101
family           CSA-100
source_version   1.0.0-draft
source_status    PROPOSED
publication      non éligible
execution        non éligible
```

Les versions d'outillage restent strictes (`X.Y.Z`). La version de la source
reste celle du contrat C2 (`SemanticVersion`) et accepte un suffixe de
pré-version. Le vocabulaire de statut a une seule source de vérité :
`DocumentStatus` dans `fn_csa.py`.

## Barrière méthodologique

Les tests et `demo.py` chargent la fiche réelle du catalogue et appellent
`compile_artifact()`. Aucune fixture ne construit un `CompilationArtifact` à la
main. Une incompatibilité entre B, C1, C2 et D-L2 provoque donc un échec avant
merge.

Le périmètre L2 reste inchangé : planification et rendu purs en mémoire ; aucun
writer, accès disque métier, publication, rollback ou exécution scientifique.
