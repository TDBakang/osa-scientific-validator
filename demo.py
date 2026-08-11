"""Reproducible demonstration: real B definition -> C2 -> pure D-L2."""
import json
from pathlib import Path

from rocsa_generator.models import FNCsaDefinition, compile_artifact
from rocsa_generator.scaffold_models import ScaffoldConfiguration
from rocsa_generator.scaffold_planner import build_scaffold_plan
from rocsa_generator.scaffold_renderer import render_scaffold

root = Path(__file__).resolve().parent
definition = FNCsaDefinition.model_validate_json(
    (root / "src/rocsa_generator/definitions/catalog/csa_101.json").read_text(
        encoding="utf-8"
    )
)
artifact = compile_artifact(definition)
rendered = render_scaffold(
    build_scaffold_plan(artifact, ScaffoldConfiguration())
)
print(json.dumps(
    rendered.manifest_draft.model_dump(mode="json"),
    ensure_ascii=False,
    indent=2,
    sort_keys=True,
))
print("pipeline=B->C1->C2->D-L2")
print("family=", artifact.control.family)
print("source_version=", artifact.provenance.source_version)
print("source_status=", artifact.qualification.source_status.value)
print("publication_ready=", rendered.manifest_draft.publication_ready)
