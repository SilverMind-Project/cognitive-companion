"""Tests for pipeline graph topology utilities."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from backend.services.pipeline_graph import (
    build_adjacency,
    find_descendants,
    find_entry_step_ids,
    topological_order,
    validate_graph,
)


@dataclass
class _FakeEdge:
    source_step_id: int
    source_port: str
    target_step_id: int
    target_port: str = "main"


def test_build_adjacency_maps_ports():
    edges = [_FakeEdge(1, "true", 2), _FakeEdge(1, "false", 3)]

    adj = build_adjacency(edges)

    assert adj[1]["true"] == 2
    assert adj[1]["false"] == 3


def test_find_entry_steps_returns_step_with_no_incoming():
    edges = [_FakeEdge(1, "main", 2), _FakeEdge(2, "main", 3)]

    entries = find_entry_step_ids({1, 2, 3}, edges)

    assert entries == [1]


def test_find_entry_steps_returns_empty_when_cycle_has_no_entry():
    edges = [_FakeEdge(1, "main", 2), _FakeEdge(2, "main", 1)]

    entries = find_entry_step_ids({1, 2}, edges)

    assert entries == []


def test_topological_order_linear():
    edges = [_FakeEdge(1, "main", 2), _FakeEdge(2, "main", 3)]

    order = topological_order({1, 2, 3}, edges)

    assert order == [1, 2, 3]


def test_topological_order_diamond():
    edges = [
        _FakeEdge(1, "true", 2),
        _FakeEdge(1, "false", 3),
        _FakeEdge(2, "main", 4),
        _FakeEdge(3, "main", 4),
    ]

    order = topological_order({1, 2, 3, 4}, edges)

    assert order[0] == 1
    assert order[-1] == 4
    assert set(order[1:3]) == {2, 3}


def test_topological_order_cycle_raises_value_error():
    edges = [_FakeEdge(1, "main", 2), _FakeEdge(2, "main", 1)]

    with pytest.raises(ValueError, match="cycle"):
        topological_order({1, 2}, edges)


def test_find_descendants_returns_all_reachable():
    edges = [
        _FakeEdge(1, "main", 2),
        _FakeEdge(2, "main", 3),
        _FakeEdge(2, "side", 4),
    ]

    descendants = find_descendants(1, {1, 2, 3, 4}, edges)

    assert descendants == {2, 3, 4}


def test_validate_graph_single_entry_no_cycle_passes():
    edges = [_FakeEdge(1, "main", 2), _FakeEdge(2, "main", 3)]

    errors = validate_graph({1, 2, 3}, edges, {1: ("main",), 2: ("main",), 3: ("main",)})

    assert errors == []


def test_validate_graph_multiple_entry_nodes_fails():
    edges = [_FakeEdge(1, "main", 2), _FakeEdge(3, "main", 4)]

    errors = validate_graph(
        {1, 2, 3, 4},
        edges,
        {1: ("main",), 2: ("main",), 3: ("main",), 4: ("main",)},
    )

    assert any("exactly one entry node" in error for error in errors)


def test_validate_graph_cycle_fails():
    edges = [_FakeEdge(1, "main", 2), _FakeEdge(2, "main", 1)]

    errors = validate_graph({1, 2}, edges, {1: ("main",), 2: ("main",)})

    assert any("cycle" in error for error in errors)


def test_validate_graph_invalid_port_fails():
    edges = [_FakeEdge(1, "maybe", 2)]

    errors = validate_graph({1, 2}, edges, {1: ("true", "false"), 2: ("main",)})

    assert any("not in declared output_ports" in error for error in errors)
