"""Protocole de benchmark statistique (D-SCAFFOLD-27, révisé après revue
du 2026-08-11 — voir DECISION-2.3-D-L4-A.md, addendum).

Mesure séparément deux chemins critiques, jamais mélangés :
1. Rendu pur L2 (build_scaffold_plan + render_scaffold, en mémoire)
2. Publication réelle L3 (publish_scaffold, CREATE_ONLY, disque réel)

Méthode de percentile : rang le plus proche par excès (« nearest-rank »,
arrondi au plafond) — index = ceil(p/100 * n) - 1, borné à [0, n-1].
Méthode standard, documentée explicitement pour que deux exécutions
indépendantes du même protocole produisent des chiffres comparables.

Exécuter sur le VPS cible, ou sur un environnement de qualification
matériellement représentatif, hors chemin des données et services de
production — jamais dans un environnement de développement local ou un
bac à sable de vérification, qui ne garantit rien sur le comportement
réel (cf. DECISION-2.3-D-L4-A.md).

Usage :
    python3 benchmark.py --official               # 1000 tirages + 10 echauffement, canonique
    python3 benchmark.py --iterations 10 --warmup 2   # exploratoire, non officiel
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from rocsa_generator.models import FNCsaDefinition, compile_artifact
from rocsa_generator.scaffold_models import ScaffoldConfiguration
from rocsa_generator.scaffold_planner import build_scaffold_plan
from rocsa_generator.scaffold_renderer import render_scaffold
from rocsa_generator.writer import publish_scaffold
from rocsa_generator.writer_models import WriteMode

OFFICIAL_ITERATIONS = 1000
OFFICIAL_WARMUP = 10


class InvalidBenchmarkParameters(ValueError):
    """Levée pour tout paramètre rendant le protocole invalide (SCAFFOLD-27,
    addendum) — jamais un crash bas niveau (IndexError, etc.)."""


def validate_parameters(iterations: int, warmup: int) -> None:
    if iterations < 1:
        raise InvalidBenchmarkParameters(f"iterations doit etre >= 1, recu {iterations}")
    if warmup < 0:
        raise InvalidBenchmarkParameters(f"warmup doit etre >= 0, recu {warmup}")


def _percentile(sorted_samples: list[float], pct: float) -> float:
    """Rang le plus proche par excès (nearest-rank, ceiling) : méthode
    documentée et déterministe, cf. docstring du module."""
    if not sorted_samples:
        raise InvalidBenchmarkParameters("impossible de calculer un percentile sur un echantillon vide")
    n = len(sorted_samples)
    index = min(n - 1, max(0, math.ceil(pct / 100 * n) - 1))
    return sorted_samples[index]


def _stats(samples: list[float]) -> dict[str, float]:
    if not samples:
        raise InvalidBenchmarkParameters("aucun tirage mesure (echantillon vide) - verifier iterations/warmup")
    ordered = sorted(samples)
    n = len(ordered)
    median = ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2
    return {
        "n": n,
        "min_ms": ordered[0] * 1000,
        "median_ms": median * 1000,
        "p95_ms": _percentile(ordered, 95) * 1000,
        "p99_ms": _percentile(ordered, 99) * 1000,
        "max_ms": ordered[-1] * 1000,
    }


def _real_artifact():
    root = Path(__file__).resolve().parent
    catalog = root / "src/rocsa_generator/definitions/catalog/csa_101.json"
    definition = FNCsaDefinition.model_validate_json(catalog.read_text(encoding="utf-8"))
    return compile_artifact(definition)


def _run_git(*args: str) -> str | None:
    try:
        return subprocess.check_output(["git", *args], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def _git_metadata() -> dict[str, object]:
    commit = _run_git("rev-parse", "HEAD")
    branch = _run_git("rev-parse", "--abbrev-ref", "HEAD")
    status = _run_git("status", "--porcelain")
    return {
        "git_commit": commit or "unknown",
        "git_branch": branch or "unknown",
        "git_dirty": bool(status) if status is not None else None,
    }


def _rocsa_generator_version() -> str:
    try:
        return importlib.metadata.version("rocsa-generator")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _initial_load_average() -> tuple[float, float, float] | None:
    if hasattr(os, "getloadavg"):
        try:
            return os.getloadavg()
        except OSError:
            return None
    return None


def _disk_metadata() -> dict[str, object]:
    tmp_dir = tempfile.gettempdir()
    usage = shutil.disk_usage(tmp_dir)
    return {
        "tmp_directory": tmp_dir,
        "disk_total_bytes": usage.total,
        "disk_used_bytes": usage.used,
        "disk_free_bytes": usage.free,
    }


def benchmark_l2_render(iterations: int, warmup: int) -> dict[str, float]:
    validate_parameters(iterations, warmup)
    artifact = _real_artifact()
    configuration = ScaffoldConfiguration()
    samples: list[float] = []
    for i in range(warmup + iterations):
        started = time.perf_counter()
        render_scaffold(build_scaffold_plan(artifact, configuration))
        elapsed = time.perf_counter() - started
        if i >= warmup:
            samples.append(elapsed)
    return _stats(samples)


def benchmark_l3_publish(iterations: int, warmup: int) -> dict[str, object]:
    validate_parameters(iterations, warmup)
    artifact = _real_artifact()
    configuration = ScaffoldConfiguration()
    rendered = render_scaffold(build_scaffold_plan(artifact, configuration))
    files_per_iteration = len(rendered.payload_files) + len(rendered.infrastructure_files)
    samples: list[float] = []
    failures = 0
    for i in range(warmup + iterations):
        with tempfile.TemporaryDirectory(prefix="rocsa-l4-benchmark-") as tmp:
            root = Path(tmp)
            started = time.perf_counter()
            report, _manifest = publish_scaffold(rendered, root, WriteMode.CREATE_ONLY)
            elapsed = time.perf_counter() - started
            if not report.write_completed:
                failures += 1
            elif i >= warmup:
                samples.append(elapsed)
    if failures:
        raise RuntimeError(f"{failures} echec(s) de publication pendant le benchmark L3 - resultats invalides")
    stats = _stats(samples)
    stats["files_per_iteration"] = files_per_iteration
    stats["write_mode"] = WriteMode.CREATE_ONLY.value
    stats["all_succeeded"] = True
    return stats


def _write_report_exclusive(output_dir: Path, base_stem: str, data: dict[str, object]) -> Path:
    """Écrit le rapport en mode création exclusive (jamais d'écrasement
    silencieux, contrairement à Path.write_text). En cas de collision de
    nom (deux runs dans la même microseconde sur le même commit — quasi
    impossible mais non exclu), ajoute un suffixe numérique croissant
    plutôt que d'écraser."""
    output_dir.mkdir(exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=True).encode("utf-8")
    candidate = output_dir / f"{base_stem}.json"
    suffix = 0
    while True:
        try:
            fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            suffix += 1
            candidate = output_dir / f"{base_stem}-{suffix}.json"
            continue
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)
        return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--iterations", type=int, default=100, help="Nombre de tirages mesures (exploratoire). Ignore si --official.")
    parser.add_argument("--warmup", type=int, default=5, help="Nombre de tirages d'echauffement exclus. Ignore si --official.")
    parser.add_argument("--official", action="store_true", help=f"Force {OFFICIAL_ITERATIONS} tirages + {OFFICIAL_WARMUP} echauffement (protocole canonique D-SCAFFOLD-27). Refuse si le depot git est sale.")
    parser.add_argument("--output-dir", type=Path, default=Path("benchmarks"))
    args = parser.parse_args()

    iterations = OFFICIAL_ITERATIONS if args.official else args.iterations
    warmup = OFFICIAL_WARMUP if args.official else args.warmup

    try:
        validate_parameters(iterations, warmup)
    except InvalidBenchmarkParameters as exc:
        print(f"[benchmark] parametres invalides: {exc}", file=sys.stderr)
        return 2

    git_meta = _git_metadata()
    if args.official and git_meta["git_dirty"]:
        print("[benchmark] REFUS: --official exige un depot git propre (modifications non commitees detectees)", file=sys.stderr)
        return 2
    if git_meta["git_dirty"]:
        print("[benchmark] AVERTISSEMENT: depot git sale - ce run ne peut pas etre considere comme reproductible", file=sys.stderr)

    mode_label = "OFFICIEL" if args.official else "exploratoire"
    print(f"[benchmark] mode {mode_label} : L2 render, {warmup} warmup + {iterations} tirages mesures...")
    l2_stats = benchmark_l2_render(iterations, warmup)
    print(f"[benchmark] L2 render : mediane={l2_stats['median_ms']:.3f}ms p95={l2_stats['p95_ms']:.3f}ms p99={l2_stats['p99_ms']:.3f}ms")

    print(f"[benchmark] mode {mode_label} : L3 publish, {warmup} warmup + {iterations} tirages mesures...")
    l3_stats = benchmark_l3_publish(iterations, warmup)
    print(f"[benchmark] L3 publish : mediane={l3_stats['median_ms']:.3f}ms p95={l3_stats['p95_ms']:.3f}ms p99={l3_stats['p99_ms']:.3f}ms")

    report = {
        "protocol": "D-SCAFFOLD-27",
        "protocol_official_run": args.official,
        "percentile_method": "nearest-rank-ceiling",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%S.", time.gmtime()) + f"{time.time_ns() % 1_000_000_000 // 1000:06d}Z",
        "rocsa_generator_version": _rocsa_generator_version(),
        "python_version": sys.version,
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "initial_load_average": _initial_load_average(),
        "iterations": iterations,
        "warmup": warmup,
        "l2_render": l2_stats,
        "l3_publish": l3_stats,
        **_git_metadata(),
        **_disk_metadata(),
    }

    base_stem = f"{report['timestamp_utc'].replace(':', '-')}_{report['git_commit'][:12]}"
    output_path = _write_report_exclusive(args.output_dir, base_stem, report)
    print(f"[benchmark] rapport ecrit dans {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
