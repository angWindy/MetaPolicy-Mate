"""Tests for Qdrant payload mapping."""

from src.rag.container import _map_access_level_to_classification


def test_department_maps_to_internal():
    assert _map_access_level_to_classification("department") == "internal"


def test_restricted_maps_to_restricted():
    assert _map_access_level_to_classification("restricted") == "restricted"


def test_public_maps_to_public():
    assert _map_access_level_to_classification("public") == "public"


def test_internal_maps_to_internal():
    assert _map_access_level_to_classification("internal") == "internal"


def test_unknown_maps_to_internal_for_safety():
    assert _map_access_level_to_classification("nonsense") == "internal"
