"""Genome — the loaded graph of all nodes.

Rebuilt from disk every engine cycle. The truth is always the Python files.
Includes parent-child index for O(1) lookups.
"""

import os
import re


class Genome:
    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self.plan_dir = os.path.join(project_dir, "plan")
        self.nodes: dict[str, 'Node'] = {}
        self._parent_index: dict[str, list[str]] = {}  # parent_name → [child_names]
        self.load_errors: list[tuple[str, str]] = []

    def add(self, node):
        self.nodes[node.name] = node

    def get(self, name: str):
        return self.nodes.get(name)

    def all_nodes(self) -> list:
        return list(self.nodes.values())

    def nodes_by_type(self, node_type: str) -> list:
        return [n for n in self.nodes.values() if n.type == node_type]

    def build_index(self):
        """Build parent→children index for fast lookups."""
        self._parent_index = {}
        for node in self.nodes.values():
            parent = node.edges.get("parent")
            if parent:
                self._parent_index.setdefault(parent, []).append(node.name)

    def children_of(self, name: str) -> list:
        """O(1) children lookup using index."""
        child_names = self._parent_index.get(name, [])
        return [self.nodes[n] for n in child_names if n in self.nodes]

    def node_in_any_journey(self, name: str) -> bool:
        """Check if a node is referenced in any journey's steps."""
        for node in self.nodes.values():
            if node.type == "journey" and hasattr(node, 'steps'):
                for step in node.steps:
                    match = re.search(r'\[(.+?)\]', step)
                    if match and match.group(1) == name:
                        return True
        return False
