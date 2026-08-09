import json
from pathlib import Path
import pytest

from rocsa_generator.models.csa import CSADefinition, CSAFamily, CSASeverity
from rocsa_generator.normalizer import CSANormalizer
from rocsa_generator.registry import RocsaRegistry


def test_normalizer_raw_list():
    raw_list = [{"control_id": "TEST-100", "name": "Control Test", "severity": "HIGH"}]
    def_obj = CSANormalizer.normalize(raw_list, file_stem="100_crypto_test")
    assert isinstance(def_obj, CSADefinition)
    assert def_obj.family == CSAFamily.CRYPTO
    assert len(def_obj.controls) == 1
    assert def_obj.controls[0].severity == CSASeverity.HIGH


def test_registry_search_by_family(tmp_path):
    catalog_file = tmp_path / "100_crypto_catalog.json"
    catalog_file.write_text(json.dumps([{"control_id": "CRYPTO-01"}]), encoding="utf-8")

    registry = RocsaRegistry()
    scanned = registry.scan_directory(tmp_path)
    assert scanned == 1

    crypto_entries = registry.search_by_family(CSAFamily.CRYPTO)
    assert len(crypto_entries) == 1
    assert crypto_entries[0].definition.controls[0].control_id == "CRYPTO-01"
