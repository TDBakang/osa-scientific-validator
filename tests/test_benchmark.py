"""Tests du protocole de benchmark (D-SCAFFOLD-27)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import benchmark


def test_percentile_nearest_rank_ceiling_method():
    # 10 valeurs triees 1..10 : p95 -> ceil(0.95*10)-1 = ceil(9.5)-1 = 10-1 = 9 -> valeur 10
    samples = list(range(1, 11))
    assert benchmark._percentile(samples, 95) == 10
    # p50 -> ceil(0.5*10)-1 = 5-1 = 4 -> valeur 5
    assert benchmark._percentile(samples, 50) == 5
    # p1 -> ceil(0.1)-1 = 1-1 = 0 -> valeur 1 (borne basse)
    assert benchmark._percentile(samples, 1) == 1


def test_percentile_raises_on_empty_sample():
    with pytest.raises(benchmark.InvalidBenchmarkParameters):
        benchmark._percentile([], 95)


def test_stats_computes_expected_fields_for_known_samples():
    # Secondes : 0.001 a 0.010
    samples = [i / 1000 for i in range(1, 11)]
    stats = benchmark._stats(samples)
    assert stats["n"] == 10
    assert stats["min_ms"] == pytest.approx(1.0)
    assert stats["max_ms"] == pytest.approx(10.0)
    assert stats["median_ms"] == pytest.approx(5.5)  # moyenne de 5 et 6 (n pair)


def test_stats_raises_clear_error_on_empty_sample_instead_of_crashing():
    """Avant correctif : IndexError brut. Après : erreur explicite et
    documentee (revue du 2026-08-11, point 4)."""
    with pytest.raises(benchmark.InvalidBenchmarkParameters):
        benchmark._stats([])


@pytest.mark.parametrize("iterations,warmup", [(0, 5), (-1, 5), (10, -1)])
def test_validate_parameters_rejects_invalid_values(iterations, warmup):
    with pytest.raises(benchmark.InvalidBenchmarkParameters):
        benchmark.validate_parameters(iterations, warmup)


def test_validate_parameters_accepts_minimal_valid_values():
    benchmark.validate_parameters(1, 0)  # ne doit pas lever


def test_report_is_never_overwritten_on_name_collision(tmp_path: Path):
    data = {"protocol": "D-SCAFFOLD-27", "value": 1}
    first = benchmark._write_report_exclusive(tmp_path, "same-stem", data)
    second = benchmark._write_report_exclusive(tmp_path, "same-stem", {"protocol": "D-SCAFFOLD-27", "value": 2})

    assert first != second
    assert first.exists() and second.exists()
    assert json.loads(first.read_text())["value"] == 1
    assert json.loads(second.read_text())["value"] == 2


def test_git_metadata_falls_back_gracefully_when_git_unavailable(monkeypatch):
    def _raise(*args, **kwargs):
        raise FileNotFoundError("git introuvable, simulation de test")

    monkeypatch.setattr(subprocess, "check_output", _raise)
    metadata = benchmark._git_metadata()
    assert metadata["git_commit"] == "unknown"
    assert metadata["git_branch"] == "unknown"
    assert metadata["git_dirty"] is None


def test_git_metadata_detects_dirty_repository(monkeypatch):
    def _fake_check_output(args, **kwargs):
        if args[1:] == ["rev-parse", "HEAD"]:
            return "abc123\n"
        if args[1:] == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return "main\n"
        if args[1:] == ["status", "--porcelain"]:
            return " M some_file.py\n"
        raise AssertionError(f"unexpected git invocation: {args}")

    monkeypatch.setattr(subprocess, "check_output", _fake_check_output)
    metadata = benchmark._git_metadata()
    assert metadata["git_dirty"] is True
    assert metadata["git_commit"] == "abc123"
    assert metadata["git_branch"] == "main"


def test_official_run_dimensions_are_fixed():
    assert benchmark.OFFICIAL_ITERATIONS == 1000
    assert benchmark.OFFICIAL_WARMUP == 10
