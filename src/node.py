"""Node — the universal building block.

Everything in genome5 is a node. A Python file with:
- name, type, description (identity)
- edges (connections: parent, owned_by, calls, depends_on)
- validate() (self-checking — returns tasks when something is wrong)
- doc/decisions/knowledge (structured memory)

Agents create whatever node types they need. The engine doesn't care
what type a node is — it loads Python and calls validate().
"""

import os


class Task:
    """A message from validate() routed to the owning agent."""

    def __init__(self, message: str, node_name: str = "",
                 phase: str = "planning", priority: int = 5,
                 severity: str = "error", check: str = "",
                 suggestion: str = "", context: str = ""):
        self.message = message
        self.node_name = node_name
        self.phase = phase
        self.priority = priority
        self.severity = severity
        self.check = check
        self.suggestion = suggestion
        self.context = context  # for cycle detection: same check + same context = cycle

    def __repr__(self):
        return f"Task(P{self.priority}/{self.severity}: {self.message[:60]})"


Issue = Task  # backward compat


class Node:
    """Base class for all genome5 nodes.

    Agents extend this. The engine requires: name (non-empty), validate().
    Everything else is optional but useful.
    """

    name: str = ""
    type: str = ""
    level: int = 0
    description: str = ""

    spec_reference: str = ""
    expected_children: list = []
    children_verified: bool = False

    properties: dict = {}
    edges: dict = {}
    files: list = []

    doc: str = ""
    decisions: list = []
    knowledge: list = []

    # Engine-managed
    _source_file: str = ""
    _mtime: float = 0

    def __init__(self):
        # Per-instance copies of mutable defaults — prevents cross-instance corruption
        self.expected_children = list(getattr(type(self), 'expected_children', []))
        self.edges = dict(getattr(type(self), 'edges', {}))
        self.files = list(getattr(type(self), 'files', []))
        self.decisions = list(getattr(type(self), 'decisions', []))
        self.knowledge = list(getattr(type(self), 'knowledge', []))
        self.properties = dict(getattr(type(self), 'properties', {}))

    def validate(self, genome) -> list[Task]:
        """Check this node. Override in subclasses for project-specific checks."""
        tasks = []
        if not self.name:
            tasks.append(Task("Node has no name", phase="structural", priority=1))
        if not self.description:
            tasks.append(Task(f"'{self.name}': no description",
                         self.name, phase="structural", priority=3, severity="warning",
                         check="no-description"))
        return tasks

    def children(self, genome) -> list['Node']:
        """Nodes whose parent edge points to this node."""
        return [n for n in genome.all_nodes()
                if n.edges.get("parent") == self.name]

    def parent_node(self, genome) -> 'Node | None':
        parent_name = self.edges.get("parent")
        return genome.get(parent_name) if parent_name else None

    def get_owner(self, genome) -> 'Node | None':
        owner_name = self.edges.get("owned_by")
        return genome.get(owner_name) if owner_name else None

    def get_owned_nodes(self, genome) -> list['Node']:
        return [n for n in genome.all_nodes()
                if n.edges.get("owned_by") == self.name]

    def get_connections(self, genome) -> list['Node']:
        """All nodes connected via edges (any direction)."""
        connected = []
        for etype, targets in self.edges.items():
            if etype.startswith("_"):
                continue
            target_list = targets if isinstance(targets, list) else [targets]
            for t in target_list:
                target_name = t[0] if isinstance(t, tuple) else t
                node = genome.get(target_name)
                if node and node not in connected:
                    connected.append(node)
        for node in genome.all_nodes():
            for etype, targets in node.edges.items():
                if etype.startswith("_"):
                    continue
                target_list = targets if isinstance(targets, list) else [targets]
                for t in target_list:
                    target_name = t[0] if isinstance(t, tuple) else t
                    if target_name == self.name and node not in connected:
                        connected.append(node)
        return connected

    def __repr__(self):
        return f"<{type(self).__name__} '{self.name}'>"
