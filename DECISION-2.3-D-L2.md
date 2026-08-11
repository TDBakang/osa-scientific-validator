# Décision 2.3-D-L2-01 — résolution différée des markers

Statut : `PROPOSED`
Date : 2026-08-11

## Décision

Le manifeste provisoire de L2 trace tous les markers nécessaires avec l'état `REQUIRED / UNRESOLVED`. Il porte obligatoirement `publication_ready=false`.

L3 doit inspecter chaque cible et remplacer cet état par exactement l'un des couples suivants :

- `CREATED / CURRENT_RUN` ;
- `REUSED / PREEXISTING_SHARED`.

L3 doit ensuite recalculer l'empreinte du lot. Aucun manifeste final ne peut conserver `UNRESOLVED`.

## Motif

L2 est sans I/O et ne peut connaître l'état du disque. La résolution différée évite une fausse preuve de propriété tout en maintenant les markers dans le périmètre traçable.

## Conséquence

Le `ManifestDraft` de L2 n'est jamais un manifeste publiable. Le writer L3 est responsable de la constatation, du journal transactionnel, du rollback et de la production du manifeste final.
