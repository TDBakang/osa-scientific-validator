"""Self-check the source delivery without writing generated scaffolds."""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    l2_root = ROOT / "src" / "rocsa_generator"
    l2_files = [l2_root / n for n in ("canonical.py", "scaffold_models.py", "scaffold_planner.py", "scaffold_renderer.py")]
    sources = sorted((ROOT / "src").rglob("*.py")) + sorted((ROOT / "tests").rglob("*.py"))
    for source in sources:
        ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    schema = json.loads((ROOT / "schemas/manifest_draft.schema.json").read_text(encoding="utf-8"))
    assert schema["$schema"].endswith("2020-12/schema")
    forbidden = ("open(", ".write_", ".write(", "os.replace", "Path.write", "shutil.")
    pure_modules = (l2_root / "scaffold_planner.py", l2_root / "scaffold_renderer.py")
    for module in pure_modules:
        text = module.read_text(encoding="utf-8")
        assert not any(token in text for token in forbidden), f"I/O token in {module.name}"

    # Garde-fou contre la régression documentée dans D-SCAFFOLD-21 : ces
    # valeurs ne doivent réapparaître comme littéraux dans les fichiers
    # propres à L2 — celles-ci auraient dû être éliminées en refactorant
    # L2 pour consommer directement DocumentStatus/FamilyId réels plutôt
    # que de les dupliquer localement. Restreint aux fichiers L2 : le
    # dossier models/ n'est pas livré par ce paquet (il existe déjà sur
    # feature/2.3-C-pure-compilation) et tests/test_l2.py référence
    # intentionnellement ces chaînes pour vérifier leur ABSENCE.
    banned_literals = {"CRYPTO", "APPROVED", "SUSPENDED"}
    for source in l2_files:
        if not source.is_file():
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in banned_literals:
                raise AssertionError(f"regression D-SCAFFOLD-21: literal {node.value!r} found in {source.relative_to(ROOT)}:{node.lineno}")

    print(f"OK: {len(sources)} Python files parse correctly")
    print("OK: L2 planner and renderer contain no forbidden writer primitive")
    print("OK: draft schema declares JSON Schema Draft 2020-12")
    print("OK: no D-SCAFFOLD-21 regression literals (CRYPTO/APPROVED/SUSPENDED) found in L2 files")
    return 0


if __name__ == "__main__":
    sys.exit(main())

