"""Unit tests for persistence-free graph traversal."""

from __future__ import annotations

import pytest

from backend.services.pipeline_graph_traversal import NodeOutcome, traverse_dag


@pytest.mark.asyncio
async def test_linear_chain_runs_in_order() -> None:
    # Arrange
    node_ids = {1, 2, 3}
    adjacency = {1: {"main": [2]}, 2: {"main": [3]}}
    entry_ids = [1]
    executed: list[int] = []

    async def execute_node(node_id: int) -> NodeOutcome:
        executed.append(node_id)
        return NodeOutcome(active_ports=frozenset(["main"]))

    # Act
    await traverse_dag(
        node_ids=node_ids,
        adjacency=adjacency,
        entry_ids=entry_ids,
        execute_node=execute_node,
    )

    # Assert
    assert executed == [1, 2, 3]


@pytest.mark.asyncio
async def test_fan_out_runs_all_targets() -> None:
    # Arrange
    node_ids = {1, 2, 3}
    adjacency = {1: {"main": [2, 3]}}
    entry_ids = [1]
    executed: list[int] = []

    async def execute_node(node_id: int) -> NodeOutcome:
        executed.append(node_id)
        return NodeOutcome(active_ports=frozenset(["main"]))

    # Act
    await traverse_dag(
        node_ids=node_ids,
        adjacency=adjacency,
        entry_ids=entry_ids,
        execute_node=execute_node,
    )

    # Assert
    assert executed[0] == 1
    assert set(executed[1:]) == {2, 3}


@pytest.mark.asyncio
async def test_fan_in_join_runs_once_after_all_parents() -> None:
    # Arrange
    node_ids = {1, 2, 3, 4}
    adjacency = {
        1: {"main": [2, 3]},
        2: {"main": [4]},
        3: {"main": [4]},
    }
    entry_ids = [1]
    executed: list[int] = []

    async def execute_node(node_id: int) -> NodeOutcome:
        executed.append(node_id)
        return NodeOutcome(active_ports=frozenset(["main"]))

    # Act
    await traverse_dag(
        node_ids=node_ids,
        adjacency=adjacency,
        entry_ids=entry_ids,
        execute_node=execute_node,
    )

    # Assert
    assert executed[0] == 1
    assert set(executed[1:3]) == {2, 3}
    assert executed[3] == 4


@pytest.mark.asyncio
async def test_condition_dead_branch_is_skipped_and_propagates() -> None:
    # Arrange
    # 1 is condition. true goes to 2, false to 3.
    # 3 has child 4, 4 has child 5.
    # We expect 3, 4, 5 to be skipped.
    node_ids = {1, 2, 3, 4, 5}
    adjacency = {
        1: {"true": [2], "false": [3]},
        3: {"main": [4]},
        4: {"main": [5]},
    }
    entry_ids = [1]
    executed: list[int] = []
    skipped: list[int] = []

    async def execute_node(node_id: int) -> NodeOutcome:
        executed.append(node_id)
        if node_id == 1:
            return NodeOutcome(active_ports=frozenset(["true"]))
        return NodeOutcome(active_ports=frozenset(["main"]))

    async def on_skip(node_id: int) -> None:
        skipped.append(node_id)

    # Act
    await traverse_dag(
        node_ids=node_ids,
        adjacency=adjacency,
        entry_ids=entry_ids,
        execute_node=execute_node,
        on_skip=on_skip,
    )

    # Assert
    assert executed == [1, 2]
    assert skipped == [3, 4, 5]


@pytest.mark.asyncio
async def test_join_with_one_live_one_dead_parent_runs() -> None:
    # Arrange
    # 1 -> true -> 2 -> 4 (join)
    # 1 -> false -> 3 -> 4 (join)
    node_ids = {1, 2, 3, 4}
    adjacency = {
        1: {"true": [2], "false": [3]},
        2: {"main": [4]},
        3: {"main": [4]},
    }
    entry_ids = [1]
    executed: list[int] = []
    skipped: list[int] = []

    async def execute_node(node_id: int) -> NodeOutcome:
        executed.append(node_id)
        if node_id == 1:
            return NodeOutcome(active_ports=frozenset(["true"]))
        return NodeOutcome(active_ports=frozenset(["main"]))

    async def on_skip(node_id: int) -> None:
        skipped.append(node_id)

    # Act
    await traverse_dag(
        node_ids=node_ids,
        adjacency=adjacency,
        entry_ids=entry_ids,
        execute_node=execute_node,
        on_skip=on_skip,
    )

    # Assert
    assert executed == [1, 2, 4]
    assert skipped == [3]


@pytest.mark.asyncio
async def test_stop_halts_traversal_immediately() -> None:
    # Arrange
    node_ids = {1, 2, 3}
    adjacency = {1: {"main": [2]}, 2: {"main": [3]}}
    entry_ids = [1]
    executed: list[int] = []

    async def execute_node(node_id: int) -> NodeOutcome:
        executed.append(node_id)
        if node_id == 2:
            return NodeOutcome(active_ports=frozenset(["main"]), stop=True)
        return NodeOutcome(active_ports=frozenset(["main"]))

    # Act
    await traverse_dag(
        node_ids=node_ids,
        adjacency=adjacency,
        entry_ids=entry_ids,
        execute_node=execute_node,
    )

    # Assert
    assert executed == [1, 2]


@pytest.mark.asyncio
async def test_resume_subset_seeds_descendants_live() -> None:
    # Arrange
    # Full graph is: 1 -> 2 -> 3 and 1 -> 3
    # Resume is at 2, so node_ids = {2, 3}, entry_ids = [2]
    # Edge 1 -> 3 should seed 3 as live because its source 1 is out-of-set.
    node_ids = {2, 3}
    adjacency = {
        1: {"main": [2, 3]},
        2: {"main": [3]},
    }
    entry_ids = [2]
    executed: list[int] = []

    async def execute_node(node_id: int) -> NodeOutcome:
        executed.append(node_id)
        return NodeOutcome(active_ports=frozenset(["main"]))

    # Act
    await traverse_dag(
        node_ids=node_ids,
        adjacency=adjacency,
        entry_ids=entry_ids,
        execute_node=execute_node,
    )

    # Assert
    assert executed == [2, 3]


@pytest.mark.asyncio
async def test_on_skip_called_for_dead_nodes() -> None:
    # Arrange
    node_ids = {1, 2}
    adjacency = {1: {"main": [2]}}
    entry_ids = [1]
    skipped: list[int] = []

    async def execute_node(node_id: int) -> NodeOutcome:
        # 1 returns no active ports, so edge 1->2 is dead
        return NodeOutcome(active_ports=frozenset())

    async def on_skip(node_id: int) -> None:
        skipped.append(node_id)

    # Act
    await traverse_dag(
        node_ids=node_ids,
        adjacency=adjacency,
        entry_ids=entry_ids,
        execute_node=execute_node,
        on_skip=on_skip,
    )

    # Assert
    assert skipped == [2]


@pytest.mark.asyncio
async def test_dangling_live_edge_to_out_of_set_target_enqueues() -> None:
    # Arrange
    # 1 -> 2 (but 2 is not in node_ids)
    node_ids = {1}
    adjacency = {1: {"main": [2]}}
    entry_ids = [1]
    executed: list[int] = []

    async def execute_node(node_id: int) -> NodeOutcome:
        executed.append(node_id)
        return NodeOutcome(active_ports=frozenset(["main"]))

    # Act
    await traverse_dag(
        node_ids=node_ids,
        adjacency=adjacency,
        entry_ids=entry_ids,
        execute_node=execute_node,
    )

    # Assert
    # execute_node should be called with 2 even though it's out of set,
    # so the caller can log or raise appropriate warnings.
    assert executed == [1, 2]
