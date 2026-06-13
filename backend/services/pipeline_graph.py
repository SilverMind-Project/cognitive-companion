"""Graph topology utilities for pipeline DAGs."""

from __future__ import annotations

from collections import defaultdict, deque

from backend.models.pipeline import PipelineEdge


def build_adjacency(edges: list[PipelineEdge]) -> dict[int, dict[str, list[int]]]:
    """Return ``{source_step_id: {source_port: [target_step_id, ...]}}``.

    A single output port may fan out to multiple targets, so each port maps to
    a list of targets. Targets preserve edge insertion order for deterministic
    traversal.
    """
    adj: dict[int, dict[str, list[int]]] = {}
    for edge in edges:
        adj.setdefault(edge.source_step_id, {}).setdefault(edge.source_port, []).append(
            edge.target_step_id
        )
    return adj


def find_entry_step_ids(step_ids: set[int], edges: list[PipelineEdge]) -> list[int]:
    """Return sorted step IDs that have no incoming edges."""
    has_incoming = {edge.target_step_id for edge in edges}
    return sorted(step_id for step_id in step_ids if step_id not in has_incoming)


def topological_order(step_ids: set[int], edges: list[PipelineEdge]) -> list[int]:
    """Return step IDs in topological order, or raise ValueError on cycles."""
    in_degree: dict[int, int] = defaultdict(int)
    adj: dict[int, list[int]] = defaultdict(list)

    for edge in edges:
        if edge.source_step_id in step_ids and edge.target_step_id in step_ids:
            adj[edge.source_step_id].append(edge.target_step_id)
            in_degree[edge.target_step_id] += 1

    queue: deque[int] = deque(sorted(step_id for step_id in step_ids if in_degree[step_id] == 0))
    order: list[int] = []

    while queue:
        step_id = queue.popleft()
        order.append(step_id)
        for neighbour in sorted(adj.get(step_id, [])):
            in_degree[neighbour] -= 1
            if in_degree[neighbour] == 0:
                queue.append(neighbour)

    if len(order) != len(step_ids):
        raise ValueError(
            f"Pipeline contains a cycle: {len(order)} steps ordered out of {len(step_ids)}"
        )
    return order


def find_descendants(
    start_step_id: int,
    step_ids: set[int],
    edges: list[PipelineEdge],
) -> set[int]:
    """Return all step IDs reachable from start_step_id, excluding start_step_id."""
    adj = build_adjacency(edges)
    visited: set[int] = set()
    queue: deque[int] = deque([start_step_id])

    while queue:
        current = queue.popleft()
        for targets in adj.get(current, {}).values():
            for target_id in targets:
                if target_id not in visited and target_id in step_ids:
                    visited.add(target_id)
                    queue.append(target_id)

    return visited


def validate_graph(
    step_ids: set[int],
    edges: list[PipelineEdge],
    step_output_ports: dict[int, tuple[str, ...]],
    *,
    check_entry: bool = True,
) -> list[str]:
    """Validate graph topology and return human-readable errors.

    The entry-node count (exactly one starting step) is an *execution*
    invariant, not an *authoring* one: while a pipeline is being built, steps
    are routinely added before they are wired, which legitimately produces
    multiple entry nodes. Authoring-time callers (the edge-save endpoint) pass
    ``check_entry=False`` so incremental edits are not rejected; execution,
    import, and the non-blocking validate endpoint keep the full check.
    Structural checks (unknown steps, duplicate source ports, invalid ports,
    cycles) always run.
    """
    errors: list[str] = []

    referenced_step_ids = {edge.source_step_id for edge in edges} | {
        edge.target_step_id for edge in edges
    }
    unknown = referenced_step_ids - step_ids
    if unknown:
        errors.append(f"Edges reference unknown step IDs: {sorted(unknown)}")

    if check_entry:
        entries = find_entry_step_ids(step_ids, edges)
        if len(entries) == 0:
            errors.append("Pipeline has no entry node (all steps have incoming edges, cycle?).")
        elif len(entries) > 1:
            errors.append(
                f"Pipeline must have exactly one entry node; found {len(entries)}: {entries}."
            )

    for edge in edges:
        declared = step_output_ports.get(edge.source_step_id, ("main",))
        if edge.source_port not in declared:
            errors.append(
                f"Edge from step {edge.source_step_id} uses port '{edge.source_port}' "
                f"which is not in declared output_ports {declared}."
            )

    try:
        topological_order(step_ids, edges)
    except ValueError as exc:
        errors.append(str(exc))

    return errors
