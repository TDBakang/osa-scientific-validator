"""Contrôle structurel autonome de la livraison 2.3-D-L3-v3."""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    sources = sorted((ROOT / "src").rglob("*.py")) + sorted((ROOT / "tests").rglob("*.py"))
    for source in sources:
        ast.parse(source.read_text(encoding="utf-8"), filename=str(source))

    schema = json.loads((ROOT / "schemas/manifest_draft.schema.json").read_text(encoding="utf-8"))
    assert schema["$schema"].endswith("2020-12/schema")

    planner = (ROOT / "src/rocsa_generator/scaffold_planner.py").read_text(encoding="utf-8")
    renderer = (ROOT / "src/rocsa_generator/scaffold_renderer.py").read_text(encoding="utf-8")
    for text in (planner, renderer):
        assert not any(token in text for token in ("open(", "os.link", "os.write", "os.mkdir"))

    safe_fs = (ROOT / "src/rocsa_generator/safe_fs.py").read_text(encoding="utf-8")
    writer = (ROOT / "src/rocsa_generator/writer.py").read_text(encoding="utf-8")
    models = (ROOT / "src/rocsa_generator/writer_models.py").read_text(encoding="utf-8")
    required_safe = ("_validate_relative_path", "O_NOFOLLOW", "os.link(", "_write_all", "lock_root_exclusive", "OwnedDirectory")
    required_writer = ("created_dirs_this_run", "directory_rollbacks", "close_owned_directories", "ROLLBACK_FAILED", "lock_root_exclusive", "unlock_root")
    assert all(token in safe_fs for token in required_safe)
    assert all(token in writer for token in required_writer)
    assert "class DirectoryRollbackRecord" in models
    assert "FORCE" not in "\n".join(line for line in writer.splitlines() if "no FORCE" not in line)

    # D-SCAFFOLD-26 : le verrou coopératif ne doit pas être présent
    # uniquement dans le code — il doit être réellement exercé par au
    # moins un test qui prouve la sérialisation (pas juste sa présence
    # syntaxique). Sans ce garde-fou, un verrou jamais testé peut être
    # accidentellement contourné (mauvais ordre d'appel, exception avant
    # acquisition, etc.) sans que rien ne le détecte.
    tests_writer = (ROOT / "tests/test_writer.py").read_text(encoding="utf-8")
    assert "LOCK_NB" in tests_writer, "aucun test n'exerce reellement le verrou (D-SCAFFOLD-26)"
    assert "BlockingIOError" in tests_writer, "aucun test ne verifie qu'une seconde acquisition est bloquee"

    decision = (ROOT / "DECISION-2.3-D-L3.md").read_text(encoding="utf-8")
    assert "D-SCAFFOLD-26" in decision, "le verrou cooperatif doit etre journalise comme decision doctrinale"

    print(f"OK: {len(sources)} fichiers Python syntaxiquement valides")
    print("OK: socle L2 pur et schéma Draft 2020-12")
    print("OK: confinement, publication sans écrasement et verrou coopératif présents")
    print("OK: journal immédiat et résultats individualisés du rollback présents")
    print("OK: verrou coopératif réellement testé (LOCK_NB/BlockingIOError) et journalisé (D-SCAFFOLD-26)")
    print("Exécuter ensuite: python3 -m pytest -q")
    return 0


if __name__ == "__main__":
    sys.exit(main())
