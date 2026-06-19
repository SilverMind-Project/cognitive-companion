"""Extracted DAG traversal core for pipeline graphs."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class NodeOutcome:
    """What a node-execute callback returns to the traversal core.

    active_ports: the output ports the node activated (drives live/dead edges).
    stop: when True the traversal halts immediately and returns control to the
        caller (durable executor uses this for cancellation and wait_until
        parking; the gate runner never sets it because parking steps are not
        gate_safe).
    """

    active_ports: frozenset[str]
    stop: bool = False


# Injected by the caller. Receives the node id; returns its outcome. The caller's
# closure is responsible for ALL side effects (db writes, emits, timing, the
# actual handler call). The core never imports Session, WorkflowExecution, or the
# event bus.
ExecuteNode = Callable[[int], Awaitable[NodeOutcome]]
# Optional hook invoked when a node is skipped as a dead branch (for logging /
# timing). Default no-op.
OnSkip = Callable[[int], Awaitable[None]]


async def traverse_dag(
    *,
    node_ids: set[int],
    adjacency: dict[int, dict[str, list[int]]],
    entry_ids: list[int],
    execute_node: ExecuteNode,
    on_skip: OnSkip | None = None,
) -> None:
    """Walk an in-degree-gated DAG, calling execute_node for each live node.

    This is the persistence-free extraction of PipelineExecutor._run_steps'
    traversal. Semantics MUST be identical: a node runs once all its in-set
    incoming edges are resolved and at least one is live; a node with only dead
    incoming edges is skipped and the skip propagates; entry nodes and run-set
    nodes fed by an out-of-set (ancestor) edge are live. Returns when the queue
    drains or execute_node returns stop=True.
    """
    # In-degree counts only edges whose source is in the run set. On resume
    # the run set is the descendant subset, so edges from already-executed
    # ancestors are treated as pre-resolved (not counted here).
    pending: dict[int, int] = defaultdict(int)
    for source_id, ports in adjacency.items():
        if source_id not in node_ids:
            continue
        for targets in ports.values():
            for target_id in targets:
                if target_id in node_ids:
                    pending[target_id] += 1

    # A node is "live" once a taken edge reaches it. Explicit entry steps are
    # live, and any run-set node fed by an out-of-set (ancestor) edge is live
    # because that ancestor already ran on the path that reached here.
    live: set[int] = set(entry_ids)
    for source_id, ports in adjacency.items():
        if source_id in node_ids:
            continue
        for targets in ports.values():
            for target_id in targets:
                if target_id in node_ids:
                    live.add(target_id)

    resolved: set[int] = set()  # executed or skipped
    enqueued: set[int] = set()  # pushed to the ready queue exactly once
    queue: deque[int] = deque()

    def _enqueue_ready(node_id: int) -> None:
        if node_id in enqueued or node_id in resolved:
            return
        enqueued.add(node_id)
        queue.append(node_id)

    def _resolve_out_edges(n_id: int, active_ports: frozenset[str] | set[str]) -> None:
        """Resolve every outgoing edge of *n_id* as live or dead.

        Decrements each in-set target's pending count, marks live targets,
        and enqueues a target once all its incoming edges are resolved. A
        live edge to a target outside the run set is enqueued so the
        ``dag_step_not_found`` warning still fires for dangling edges.
        """
        for port, targets in adjacency.get(n_id, {}).items():
            is_live = port in active_ports
            for target_id in targets:
                if is_live:
                    live.add(target_id)
                if target_id in node_ids:
                    pending[target_id] -= 1
                    if pending[target_id] <= 0:
                        _enqueue_ready(target_id)
                elif is_live:
                    _enqueue_ready(target_id)

    # Seed the frontier: every run-set node with no unresolved in-set
    # incoming edge. On a fresh execute this is the single entry node; on
    # resume it is the set of steps immediately after the resumed step.
    for node_id in node_ids:
        if pending[node_id] == 0:
            _enqueue_ready(node_id)

    while queue:
        node_id = queue.popleft()
        if node_id in resolved:
            continue
        resolved.add(node_id)

        # Dead branch: no live edge reached this node, so skip it and
        # propagate the skip (its outgoing edges resolve as dead too).
        if node_id not in live:
            if on_skip:
                await on_skip(node_id)
            _resolve_out_edges(node_id, frozenset())
            continue

        outcome = await execute_node(node_id)
        _resolve_out_edges(node_id, outcome.active_ports)
        if outcome.stop:
            break
