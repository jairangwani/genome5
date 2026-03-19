"""Agent Guide — THE document every agent reads.

Teaches agents how genome5 works through CONCRETE EXAMPLES.
Explains the use-case-first flow and what the engine enforces.
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

You have FREEDOM. Think deeply. Create comprehensively. No micromanagement.

=== THE FLOW (use-case-first) ===

PHASE 1: PERSONAS — WHO uses this system?
  Create persona nodes. Exhaust ALL user types: primary users, operators,
  admins, threat actors, automated agents, visitors, API consumers.
  The engine will ask you "what did you miss?" with a FRESH agent.
  Don't rush. This is the foundation.

PHASE 2: USE CASES — WHAT can each persona do?
  For EACH persona, create use case nodes: happy path, error recovery,
  edge cases, abuse scenarios. 10-20 per persona.
  The engine will re-check with a fresh agent.

PHASE 3: JOURNEYS — HOW does each use case work?
  Step-by-step with [brackets] referencing services:
  "1. [Consumer] types description"
  "2. [Gateway] receives request"
  Include error paths. 10-25 steps.

PHASE 4: SERVICES EMERGE — from journey [brackets]
  Services you reference that don't exist → engine creates them.
  You do NOT pre-plan services from the spec.
  Services emerge from what journeys NEED.

=== WHAT THE ENGINE ENFORCES (you can't bypass this) ===

EXHAUSTION LIFECYCLE: For any node with expected_children:
  1. You list expected_children → create them
  2. Engine spawns a FRESH agent to re-read the spec
     "What concepts are NOT covered by these children?"
  3. If gaps found → more children added → cycle repeats
  4. After verified → ANOTHER fresh agent reviews
  5. Reviewer either approves or adds more

You CANNOT skip this. The engine does it automatically.
Setting children_verified=True triggers the reviewer.
The reviewer can reset it if they find gaps.

DEBATE TEAM: For persona/use-case discovery tasks marked debate=True:
  - 1 SOLVER proposes answers
  - 2 BREAKERS find flaws and gaps
  - They go back and forth until converged
  You don't control this — the engine runs it.

=== HOW TO CREATE A NODE ===

from genome5 import Node, Task

class MyService(Node):
    name = "Gateway API Service"        # exact name
    type = "service"
    level = 2                           # parent.level + 1
    description = "HTTP entry point"

    spec_reference = "docs/PANDO-PLAN.md:## 8. Gateway"

    expected_children = [               # exact child node names
        "Route Anonymous Build Request",
        "Handle Auth Failure",
    ]
    children_verified = False
    children_reviewed = False

    edges = {
        "parent": "Gateway Module",
        "owned_by": "Infrastructure Agent",
        "calls": ["Doorman Service"],
    }

    files = ["src/gateway/api.ts"]
    doc = "Gateway handles all HTTP requests."
    decisions = ["Express over Fastify — simpler"]
    knowledge = []

=== HOW TO CREATE A JOURNEY ===

class ConsumerBuildsApp(Node):
    name = "Consumer Builds App Journey"
    type = "journey"
    level = 4
    description = "Stranger gets a live app without signup"

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
        "E1. [Content Safety] blocks → rephrasing suggestion",
        "E2. [Build Service] crashes → [Recovery] resumes",
        "E3. Browser closes → [Claim Token] allows return",
    ]

Things in [brackets] MUST EXIST. If they don't, the engine creates them.

=== HOW TO CREATE A PERSONA ===

class Consumer(Node):
    name = "Consumer"
    type = "persona"
    level = 1
    description = "Builds apps by describing them in plain language"

    edges = {
        "parent": "Users Domain",
        "owned_by": "Planning Agent",
    }

    properties = {
        "goals": [
            "Build an app in under 5 minutes",
            "Get a live URL without signup",
            "Edit and iterate on their app",
        ],
    }

=== KEY RULES ===

1. ORDERING: Personas → Use Cases → Journeys → Services emerge.
   Do NOT create services directly from the spec. They emerge.

2. HIERARCHY: Every node has a parent. Level = parent.level + 1.

3. EXPECTED_CHILDREN: Exact node names. Engine checks existence.

4. JOURNEYS: Steps reference services in [brackets].
   Missing services → dangling edges → engine creates them.

5. SPEC_REFERENCE: Section headers, not line numbers.

6. IMPORT: 'from genome5 import Node, Task'

7. PYTHON: No leading zeros. encoding="utf-8".
""",
    ]
