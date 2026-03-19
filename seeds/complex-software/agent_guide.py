"""Agent Guide — THE document every agent reads.

This teaches agents how genome5 works through CONCRETE EXAMPLES.
Examples > abstract rules. Copy the patterns you see here.
"""
from genome5 import Node


class AgentGuide(Node):
    name = "Agent Guide"
    type = "guide"
    level = 0
    description = "How genome5 works. Read before every task."

    knowledge = [
        """
YOU ARE AN AI AGENT IN GENOME5.

You have FREEDOM. Think deeply. Create comprehensively. Nobody micromanages you.

=== WHAT IS GENOME5 ===

Everything is a Python node in plan/. Each node has:
  - name, type, level, description (identity)
  - edges (parent, owned_by, calls, depends_on)
  - validate() (checks itself — returns Tasks when something is wrong)
  - doc, decisions, knowledge (memory)

The engine loads ALL nodes, calls ALL validate(), routes tasks to owners.
When all validate() return [] — project is CONVERGED.

=== HOW TO CREATE A NODE ===

from genome5 import Node, Task

class MyService(Node):
    name = "Gateway API Service"        # exact name — used for matching
    type = "service"                     # any type you want
    level = 2                            # parent.level + 1
    description = "HTTP entry point — routes requests to Doorman"

    spec_reference = "docs/PANDO-PLAN.md:## 8. Two-Tier Node Architecture"

    expected_children = [                # exact names of children this node needs
        "Route Anonymous Build Request",
        "Handle Auth Failure",
        "Handle Rate Limit Exceeded",
    ]
    children_verified = False            # True after you've confirmed nothing missing

    edges = {
        "parent": "Gateway Module",      # who is my parent (level - 1)
        "owned_by": "Infrastructure Agent",  # who works on me
        "calls": ["Doorman Service", "Content Safety Service"],
    }

    files = ["src/gateway/api.ts"]       # source files (dev phase)

    doc = "Gateway handles all HTTP requests. Entry point for the system."
    decisions = ["Chose Express over Fastify — simpler"]
    knowledge = []

    def validate(self, genome):
        tasks = super().validate(genome)

        # Check expected children exist
        existing = {n.name for n in self.children(genome)}
        for name in self.expected_children:
            if name not in existing:
                tasks.append(Task(
                    f"Create use case: '{name}' (parent: '{self.name}', level: 3)",
                    self.name, phase="planning",
                ))

        # Check source files exist (dev phase)
        import os
        for f in self.files:
            if not os.path.exists(os.path.join(genome.project_dir, f)):
                tasks.append(Task(f"Implement: {f}", self.name, phase="dev"))

        return tasks

=== HOW TO CREATE A JOURNEY ===

class ConsumerBuildsApp(Node):
    name = "Consumer Builds App Journey"
    type = "journey"
    level = 4
    description = "End-to-end flow: stranger gets a live app without signup"

    edges = {
        "parent": "Build App Use Case",
        "owned_by": "Planning Agent",
    }

    steps = [
        "1. [Consumer] opens pando.network",
        "2. [Consumer] types app description",
        "3. [Gateway] receives HTTP POST",
        "4. [Content Safety] scans for harmful content",
        "5. [Doorman] classifies as build request",
        "6. [Build Service] starts planning",
        "7. [SSE Stream] sends live progress",
        "8. [Hosting] deploys to subdomain",
        "9. [Consumer] gets live URL",
        "",
        "ERROR PATHS:",
        "E1. [Content Safety] blocks → show rephrasing suggestion",
        "E2. [Build Service] crashes → [Recovery] resumes from checkpoint",
        "E3. Browser closes → [Claim Token] allows return within 30 days",
    ]

    knowledge = [
        "Things in [brackets] are services that MUST EXIST.",
        "If a service doesn't exist, the engine creates a dangling edge task.",
        "Error paths are critical — every journey needs them.",
    ]

=== HOW TO CREATE A PERSONA ===

class ConsumerPersona(Node):
    name = "Consumer"
    type = "persona"
    level = 1
    description = "Person who builds apps on Pando without technical knowledge"

    edges = {
        "parent": "Users Domain",
        "owned_by": "Planning Agent",
    }

    properties = {
        "goals": [
            "Build an app by describing it in plain language",
            "Get a live URL in under 5 minutes",
            "Edit and iterate on their app",
        ],
    }

=== KEY RULES ===

1. HIERARCHY: Every node has a parent (except Level 0 domains).
   Level must equal parent level + 1. Engine enforces this.

2. EXPECTED_CHILDREN: List exact node names. The engine checks
   if children with those names exist. Names must match exactly.

3. JOURNEYS: Steps reference services in [brackets].
   If the service doesn't exist, the engine detects a dangling edge
   and creates a task to build it. The hierarchy GROWS from journeys.

4. SPEC_REFERENCE: Use section headers, not line numbers.
   "docs/PANDO-PLAN.md:## 8. Two-Tier Node Architecture"

5. AFTER EVERY TASK:
   - Update the node's knowledge
   - REFLECT: should you update expected_children?
   - Did you discover something that changes the hierarchy?

6. IMPORT: always 'from genome5 import Node, Task'
   For seed types: 'from genome5.seeds import ServiceNode' (optional)
   NEVER: 'from plan...' or 'import subprocess' in node files

7. PYTHON: No leading zeros (0644 invalid). Use encoding="utf-8".
""",
    ]
