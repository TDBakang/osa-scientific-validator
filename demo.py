"""Reproducible, non-writing demonstration of the L2 boundary.

Charge le vrai vecteur C2 via from_canonical_json() s'il est present au
chemin par defaut ou via ROCSA_REAL_VECTOR_PATH ; retombe sinon sur une
valeur illustrative NON probante mais typee sur les vrais modeles C1/C2
(voir tests/test_l2.py::illustrative_artifact - D-SCAFFOLD-21).
"""
import json
import os
from pathlib import Path

from rocsa_generator.canonical import sha256
from rocsa_generator.models import (
    CompilationArtifact, CompiledCSAControl, CompilationProvenance,
    CompilationQualification, from_canonical_json,
)
from rocsa_generator.scaffold_models import ScaffoldConfiguration
from rocsa_generator.scaffold_planner import build_scaffold_plan
from rocsa_generator.scaffold_renderer import render_scaffold

DEFAULT_REAL_VECTOR_PATH = Path("tests/fixtures/csa_101_compilation_artifact.canonical.json")
real_vector_path = Path(os.environ.get("ROCSA_REAL_VECTOR_PATH", DEFAULT_REAL_VECTOR_PATH))

if real_vector_path.is_file():
    artifact = from_canonical_json(real_vector_path.read_text(encoding="utf-8"))
    print(f"[demo] vecteur reel charge depuis {real_vector_path}")
else:
    print(f"[demo] AVERTISSEMENT: {real_vector_path} absent -> valeur illustrative non probante (D-SCAFFOLD-21)")
    source = b'{"csa_id":"CSA-101","status":"PROPOSED"}'
    artifact = CompilationArtifact(
        control=CompiledCSAControl(
            control_id="CSA-101", semantic_code="CRYPTO.INTEGRITY.VERIFY",
            title="Contrôle d'intégrité cryptographique", severity="CRITICAL",
            family="CSA-100", allowed_states=("PASSED", "FAILED", "NOT_APPLICABLE", "ERROR"),
            on_failure="BLOCK_DVS",
        ),
        provenance=CompilationProvenance(
            source_csa_id="CSA-101", source_version="1.0.0-draft",
            source_fingerprint=sha256(source), compiler_contract_version="1.0.0",
        ),
        field_trace=(), omitted_source_sections=(),
        qualification=CompilationQualification(
            source_status="PROPOSED", publication_eligible=False,
            publication_blocking_reasons=("Approbation scientifique absente",),
            execution_eligible=False, execution_blocking_reason="Implémentation métier absente",
        ),
    )

rendered = render_scaffold(build_scaffold_plan(artifact, ScaffoldConfiguration()))
print(json.dumps(rendered.manifest_draft.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True))
print("payload_bytes=", sum(f.size_bytes for f in rendered.payload_files))
print("publication_ready=", rendered.manifest_draft.publication_ready)
