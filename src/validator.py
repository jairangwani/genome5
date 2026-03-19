"""Validator — universal checks only.

The engine runs these on every node. No domain knowledge.
1. Load errors (broken Python files)
2. Dangling edges (references to non-existent nodes)
3. Level consistency (node.level == parent.level + 1)
4. Near-duplicate names (Levenshtein < 3)
5. Staleness cascade (info-level only, one level deep)
"""

import os
from src.genome import Genome
from src.node import Task


def validate_genome(genome: Genome) -> list[Task]:
    """Run universal validation. Returns sorted tasks."""
    tasks = []

    # 1. Load errors
    for filepath, error in genome.load_errors:
        rel = os.path.relpath(filepath, genome.project_dir)
        tasks.append(Task(
            f"File '{rel}' failed to load: {error[:200]}",
            node_name=rel, phase="structural", priority=1,
            check="load-error",
        ))

    # 2. Each node validates itself
    for node in genome.all_nodes():
        tasks.extend(node.validate(genome))

    # 3. Dangling edges
    tasks.extend(_check_dangling_edges(genome))

    # 4. Level consistency
    tasks.extend(_check_level_consistency(genome))

    # 5. Staleness (info-level, one level deep)
    tasks.extend(_check_staleness(genome))

    return prioritize(tasks)


def prioritize(tasks: list[Task]) -> list[Task]:
    phase_order = {"structural": 0, "planning": 1, "review": 2, "dev": 3, "test": 4}
    severity_order = {"error": 0, "warning": 1, "info": 2}
    return sorted(tasks, key=lambda t: (
        phase_order.get(t.phase, 99),
        t.priority,
        severity_order.get(t.severity, 3),
    ))


def _check_dangling_edges(genome: Genome) -> list[Task]:
    tasks = []
    all_names = set(genome.nodes.keys())

    for node in genome.all_nodes():
        for etype, targets in node.edges.items():
            if etype.startswith("_") or etype == "owned_by":
                continue
            target_list = targets if isinstance(targets, list) else [targets]
            for t in target_list:
                target_name = t[0] if isinstance(t, tuple) else t
                if target_name and target_name not in all_names:
                    tasks.append(Task(
                        f"'{node.name}' references non-existent '{target_name}'",
                        node_name=node.name, phase="structural", priority=2,
                        check="dangling-edge",
                        suggestion=f"Create '{target_name}' or remove the edge",
                    ))
    return tasks


def _check_level_consistency(genome: Genome) -> list[Task]:
    tasks = []
    for node in genome.all_nodes():
        parent = node.parent_node(genome)
        if parent and parent.level != node.level - 1:
            tasks.append(Task(
                f"'{node.name}' is level {node.level} but parent "
                f"'{parent.name}' is level {parent.level} (expected {node.level - 1})",
                node_name=node.name, phase="structural", priority=1,
                check="level-mismatch",
            ))
    return tasks


def _check_staleness(genome: Genome) -> list[Task]:
    """One level deep, info-level only. Does not block progress."""
    tasks = []
    for node in genome.all_nodes():
        parent = node.parent_node(genome)
        if parent and parent._mtime > node._mtime > 0:
            tasks.append(Task(
                f"'{node.name}' may be stale: parent '{parent.name}' changed",
                node_name=node.name, phase="planning", priority=5, severity="info",
                check="staleness",
            ))
    return tasks
