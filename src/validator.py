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

    # 6. Exhaustion lifecycle (engine-enforced, can't be bypassed)
    tasks.extend(_check_exhaustion(genome))

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
            if etype.startswith("_"):
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


def _check_exhaustion(genome: Genome) -> list[Task]:
    """Engine-enforced exhaustion lifecycle. Can't be bypassed by agents.

    For any node with expected_children:
    - State 2: children missing → task to create them (handled by node validate())
    - State 3: all children exist + NOT verified → FRESH agent re-reads spec
    - State 4: verified + NOT reviewed → FRESH reviewer checks completeness

    The fresh_session flag tells the engine to spawn a NEW agent, not reuse
    the persistent one. This ensures different LLM sampling paths.
    """
    tasks = []

    for node in genome.all_nodes():
        # Only applies to nodes with expected_children
        if not node.expected_children:
            continue

        # Check if all expected children exist
        existing = {n.name for n in node.children(genome)}
        missing = [name for name in node.expected_children if name not in existing]

        if missing:
            # State 2: children missing — node's own validate() handles this
            continue

        # All children exist
        if not node.children_verified:
            # STATE 3: Re-read spec with FRESH agent
            # Show child DESCRIPTIONS (not names) so agent evaluates
            # conceptual coverage, not string confirmation.
            child_descriptions = "; ".join(
                f"{c.name}: {c.description[:60]}"
                for c in node.children(genome)
            )
            spec_ref = node.spec_reference or "the project spec"

            tasks.append(Task(
                f"EXHAUSTION CHECK for '{node.name}': All {len(node.expected_children)} "
                f"children exist. Re-read {spec_ref} (with ±20 lines of surrounding context). "
                f"Current children cover: [{child_descriptions}]. "
                f"What concepts in the spec are NOT covered by these children? "
                f"If you find gaps, add the missing names to expected_children. "
                f"If genuinely nothing is missing, set children_verified = True.",
                node_name=node.name, phase="planning", priority=2,
                check=f"exhaustion-state3:{node.name[:30]}",
                fresh_session=True,  # MUST be a fresh agent session
            ))

        elif not node.children_reviewed:
            # STATE 4: Reviewer with FRESH agent
            child_list = ", ".join(
                f"{c.name} ({c.description[:40]})"
                for c in node.children(genome)
            )
            # Calculate sibling comparison for context
            parent = node.parent_node(genome)
            sibling_avg = 0
            if parent:
                siblings = parent.children(genome)
                sibling_counts = [len(s.expected_children) for s in siblings if s.expected_children]
                if sibling_counts:
                    sibling_avg = sum(sibling_counts) / len(sibling_counts)

            comparison = ""
            if sibling_avg > 0:
                comparison = (f" Sibling nodes average {sibling_avg:.0f} children. "
                            f"This node has {len(node.expected_children)}. ")

            tasks.append(Task(
                f"REVIEWER for '{node.name}': {len(node.expected_children)} children: "
                f"[{child_list}].{comparison}"
                f"Read the spec section and these children's descriptions. "
                f"Are ALL concepts from the spec covered? Is anything missing? "
                f"If you find gaps, add names to expected_children and set "
                f"children_verified = False. If complete, set children_reviewed = True.",
                node_name=node.name, phase="review", priority=3,
                check=f"exhaustion-state4:{node.name[:30]}",
                fresh_session=True,  # MUST be a different fresh agent
            ))

    return tasks
