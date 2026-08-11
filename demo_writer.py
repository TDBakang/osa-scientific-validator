"""Démonstration minimale du cycle CREATED puis REUSED de L3."""
from __future__ import annotations

import tempfile
from pathlib import Path

from rocsa_generator.models import FNCsaDefinition, compile_artifact
from rocsa_generator.scaffold_models import ScaffoldConfiguration
from rocsa_generator.scaffold_planner import build_scaffold_plan
from rocsa_generator.scaffold_renderer import render_scaffold
from rocsa_generator.writer import publish_scaffold
from rocsa_generator.writer_models import WriteMode


def main() -> None:
    root_dir = Path(__file__).resolve().parent
    definition = FNCsaDefinition.model_validate_json(
        (root_dir / "src/rocsa_generator/definitions/catalog/csa_101.json").read_text(encoding="utf-8")
    )
    artifact = compile_artifact(definition)
    rendered = render_scaffold(build_scaffold_plan(artifact, ScaffoldConfiguration()))
    with tempfile.TemporaryDirectory(prefix="rocsa-l3-demo-") as directory:
        root = Path(directory)
        created_report, created_manifest = publish_scaffold(rendered, root, WriteMode.CREATE_ONLY)
        reused_report, reused_manifest = publish_scaffold(rendered, root, WriteMode.REGENERATE_VERIFIED)
        assert created_report.write_completed and created_manifest is not None
        assert reused_report.write_completed and reused_manifest is not None
        print("created=", [record.state for record in created_report.records])
        print("reused=", [record.state for record in reused_report.records])
        # Le fingerprint final inclut la matérialisation CREATED/REUSED : il
        # décrit donc le run, pas seulement les octets. Les octets, eux, sont
        # prouvés identiques par REUSED_VERIFIED.
        print("content_reused_verified=", all(record.state.value == "REUSED_VERIFIED" for record in reused_report.records))
        print("run_fingerprints_distinct=", created_manifest.bundle_fingerprint != reused_manifest.bundle_fingerprint)
        print("authority=", created_manifest.authority)


if __name__ == "__main__":
    main()
