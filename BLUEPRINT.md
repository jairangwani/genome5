# GENOME5 — THE FINAL PLAN

One document. Everything needed to build it.

---

## WHAT IS GENOME5

A system where AI agents plan, build, test, and maintain ANY project. The engine is a loop that loads Python node files, calls validate() on each, routes tasks to agents, and repeats until done. Agents are persistent Claude Code sessions. Nodes remember context. The hierarchy grows organically from use cases.

---

## THE FLOW (for any project)

```
1. PERSONAS      → WHO uses this? (debate team: 1 solver + 2 breakers)
2. USE CASES     → WHAT can each persona do? (debate team per persona)
3. JOURNEYS      → HOW does each use case work? (step by step)
4. SERVICES      → EMERGE from journey references [brackets]
5. HIERARCHY     → GROWS as services group into modules and domains
6. CODE          → Built to make journeys work
7. TESTS         → Replay journeys. Pass = done. Fail = fix.
```

Steps 1-2 are where the debate team ensures EXHAUSTIVE coverage.
Steps 3-5 are where nodes and hierarchy organize the work.
Steps 6-7 are where experience teaches what's missing.

---

## THE ENGINE

### What It Does

```python
while True:
    genome = load_all_python_files("plan/")
    tasks = []
    for node in genome.all_nodes():
        tasks.extend(node.validate(genome))

    if not tasks:
        print("CONVERGED")
        return

    if budget_exceeded():
        print("PAUSED — progress report written")
        return

    top = prioritize(tasks)[0]
    owner = find_owner(top)

    snapshot()                          # file-copy, not git per cycle
    result = send_to_agent(owner, top)  # persistent Claude Code session

    if regression(result):
        restore_snapshot()
    else:
        save()

    # git commit every N cycles for durable checkpoints
```

### What It Does NOT Do

- No domain knowledge. Does not know what a "persona" or "service" is.
- No opinions. Does not check for verb lists, persona types, or quality.
- No planning logic. All planning lives in node validate() methods.
- The engine is DUMB. Nodes are SMART.

### Engine Features (from battle-tested genome5 doc)

1. **File-copy snapshots** — not git per cycle. Git every N cycles for checkpoints. Fast rollback.
2. **AST validation** — before importing any node file, parse the AST. Reject dangerous code. Import whitelist. 5-second timeout.
3. **Parallel dispatch** — one task per distinct agent, think in parallel, apply serially.
4. **Dispatch IDs** — UUID per dispatch prevents stale completion signals from ghost reader threads.
5. **Cycle detection** — track (node_name, check_id, context). Same triple 3 times = skip. Prevents infinite loops.
6. **Regression guard** — if agent creates new critical errors without fixing assigned task, restore snapshot.
7. **Crash logging** — unhandled exceptions write to plan/engine-crash.log with traceback.
8. **Convergence budgets** — max cycles, max wall-clock hours. Pauses and reports, doesn't grind forever.
9. **Mutable defaults fix** — Node.__init__ creates per-instance copies of all lists/dicts.
10. **Near-duplicate detection** — Levenshtein distance < 3 between node names → reconciliation task. Pre-filtered for performance.
11. **Level consistency** — node.level must equal parent.level + 1. Engine enforces.
12. **Dangling edge detection** — edge references non-existent node → task to create it or remove edge.
13. **Staleness** — info-level only. One level deep. Content-hash to auto-dismiss unchanged nodes.
14. **Windows support** — forward slashes, UTF-8, long paths, taskkill for process cleanup.

---

## AGENTS

### Persistent Sessions

Each agent is a persistent Claude Code process. Spawned once, stays alive across tasks. Same conversation context. Communication via NDJSON stdin/stdout.

```python
args = [
    "claude",
    "--input-format", "stream-json",
    "--output-format", "stream-json",
    "--model", model,
    "--dangerously-skip-permissions",
    "--verbose",
    "--system-prompt", system_prompt,
]
proc = subprocess.Popen(args, stdin=PIPE, stdout=PIPE, stderr=PIPE)
```

Agents are NOT killed between tasks. They accumulate context. They remember what they built in previous tasks.

### Agent Timeout

Default 600 seconds. Configurable. On timeout: kill process, respawn on next task.

### How Agents Learn the System

**Layer 1: System prompt** — just identity: "You are Infrastructure Agent. [description]."

**Layer 2: Task message** — specific instructions for THIS task:
```
"Create child node with EXACTLY this name: 'Rate Limiter Service'
 Parent: 'Gateway Module'. Level: 2.
 Read spec section '## 8.1 Gateway' for context."
```

**Layer 3: Agent guide seed** — concrete examples of node structure, lifecycle states, edge types. Read before every task. Examples > abstract rules.

**Safety nets** — wrong Python = load error. Missing parent = dangling edge. Wrong level = structural error. Engine catches mistakes.

### Bootstrap

Engine creates HR Agent if no agents exist. HR Agent reads the spec/context.yaml and creates specialist agents.

---

## THE DEBATE TEAM

### When It's Used

For ANY open-ended question where "are we sure we covered everything?" matters:
- Discovering ALL personas (Step 1)
- Discovering ALL use cases per persona (Step 2)
- Reviewing architecture decisions
- Validating the final plan

NOT used for: writing code, creating specific journeys, fixing bugs.

### How It Works

```
1 SOLVER:   proposes the answer, integrates feedback
2 BREAKERS: find flaws and gaps, hint at solutions

Round 1: Solver proposes
Round 2: Breaker 1 attacks from logical angle
Round 3: Breaker 2 attacks from practical angle
Round 4: Solver integrates fixes
Round 5+: Breakers push until "CONVERGED — can't find more"
```

### Implementation

Three persistent Claude Code sessions. Each round: agent reads shared document + previous rounds. Appends response. Alternates until all say CONVERGED.

The solver's final output IS the result. Not a debate transcript — a solution.

---

## NODES

### What A Node Is

A Python file that REMEMBERS something and CHECKS itself:

```python
from genome5 import Node, Task

class GatewayService(Node):
    name = "Gateway API Service"
    type = "service"
    level = 2
    description = "HTTP entry point — routes requests to Doorman"

    spec_reference = "docs/PANDO-PLAN.md:## 8. Two-Tier Node Architecture"

    expected_children = [
        "Route Anonymous Build Request",
        "Route Authenticated Request",
        "Handle Rate Limit Exceeded",
    ]
    children_verified = False

    edges = {
        "parent": "Gateway Module",
        "owned_by": "Infrastructure Agent",
        "calls": ["Doorman Service", "Content Safety Service"],
    }

    files = ["src/gateway/api.ts"]

    doc = "Gateway is the HTTP entry point. All external requests enter here."
    decisions = ["Chose Express over Fastify — simpler, team familiar"]
    knowledge = []

    def validate(self, genome):
        tasks = super().validate(genome)

        # Check expected children exist
        existing = {n.name for n in self.children(genome)}
        for name in self.expected_children:
            if name not in existing:
                tasks.append(Task(
                    f"Create use case: '{name}' (parent: '{self.name}', level: 3)",
                    self.name, phase="planning"
                ))

        # Check source files exist (dev phase)
        for f in self.files:
            if not os.path.exists(os.path.join(genome.project_dir, f)):
                tasks.append(Task(
                    f"Implement: {f}", self.name, phase="dev"
                ))

        return tasks
```

### Node Base Class

```python
class Node:
    name: str = ""
    type: str = ""
    level: int = 0
    description: str = ""

    spec_reference: str = ""            # section header, not line numbers
    expected_children: list[str] = []   # exact child node names
    children_verified: bool = False

    properties: dict = {}
    edges: dict = {}                    # parent, owned_by, calls, depends_on
    files: list[str] = []              # source files (dev phase)

    doc: str = ""                       # PERMANENT
    decisions: list[str] = []          # PERMANENT
    knowledge: list[str] = []          # PRUNED to last 8

    def __init__(self):
        # Per-instance copies of mutable defaults
        self.expected_children = list(getattr(type(self), 'expected_children', []))
        self.edges = dict(getattr(type(self), 'edges', {}))
        self.files = list(getattr(type(self), 'files', []))
        self.decisions = list(getattr(type(self), 'decisions', []))
        self.knowledge = list(getattr(type(self), 'knowledge', []))
        self.properties = dict(getattr(type(self), 'properties', {}))

    def validate(self, genome) -> list[Task]:
        tasks = []
        if not self.name:
            tasks.append(Task("Node has no name", phase="structural", priority=1))
        if not self.description:
            tasks.append(Task(f"'{self.name}': no description",
                         self.name, severity="warning"))
        return tasks

    def children(self, genome):
        return [n for n in genome.all_nodes()
                if n.edges.get("parent") == self.name]

    def parent_node(self, genome):
        parent_name = self.edges.get("parent")
        return genome.get(parent_name) if parent_name else None

    def get_owner(self, genome):
        owner_name = self.edges.get("owned_by")
        return genome.get(owner_name) if owner_name else None
```

---

## THE HIERARCHY

### How It Grows (Bottom-Up)

```
Journeys reference services in [brackets]
         ↓
Services that don't exist → engine creates them (dangling edge)
         ↓
Services accumulate → agents group into modules
         ↓
Modules accumulate → agents group into domains
         ↓
Hierarchy emerges organically
```

### Levels

```
Level 0: Domains     — emerge from grouping modules
Level 1: Modules     — emerge from grouping services
Level 2: Services    — emerge from journey references
Level 3: Use Cases   — from debate team exhaustion
Level 4: Journeys    — step-by-step = test scenarios
```

Levels 3-4 created FIRST. Levels 0-2 grow from what's needed.

### Two Journey Types

1. **Persona journeys** — human triggers it: "Consumer builds app"
   Lives under: the persona node
2. **Operational journeys** — system event: "Node crashes, projects migrate"
   Lives under: the service that handles the event

Both get tested. Many events have both types.

### Impact Radius

When something changes, edges show EXACTLY what's affected:
- Change a service → journeys referencing it become stale → tests re-run → failures fixed
- Remove a persona → all their use cases flagged → agents update or deprecate
- Only the affected BRANCH changes. Other branches untouched.

### Delete / Merge / Restructure

- **Deprecate**: node gets deprecated flag. No more tasks generated. Stays in history.
- **Merge**: two overlapping services combined. Children re-parented. Old node deprecated.
- **Restructure**: move a service to different module. Change parent edge. Engine detects and propagates.

---

## SEED SYSTEM

### What Seeds Are

Optional starting-point node types. NOT frozen. Agents modify freely. Seeds save agents from reinventing common patterns.

### Complex Software Seed

```
seeds/complex-software/
  agent_guide.py          — how genome5 works (examples for every pattern)
  service_node.py         — ServiceNode with file-exists validation
  persona_node.py         — PersonaNode with coverage lifecycle
  journey_node.py         — JourneyNode with steps + [bracket] references
  use_case_node.py        — UseCaseNode with journey validation
  test_node.py            — TestNode with run() and runnable property
  config_node.py          — ConfigNode for engine settings
```

### Lifecycle Seeds

Seeds encode two lifecycles in their validate():

**Decomposition** (services, modules, domains):
```
State 1: expected_children empty → "list children from spec"
State 2: children missing → "create child X"
State 3: all exist → "re-read spec, what's missing?" (FRESH agent session)
State 4: verified → reviewer (ANOTHER fresh session)
```

**Coverage** (personas, security threats):
```
State 1: scan all services → "which does this persona use?"
State 2: create use cases for uncovered services
State 3: verify coverage → "any services missed?"
State 4: reviewer checks coverage completeness
```

### Other Seeds

```
seeds/book/        — BookNode, ChapterNode, SceneNode, CharacterNode
seeds/game/        — GameNode, MechanicNode, LevelNode, PlayerNode
seeds/blank/       — just base Node class
```

Agents can also write `class MyNode(Node)` with NO seed. Seeds are helpers, not requirements.

---

## FULL LIFECYCLE FOR PANDO

### Phase 1: PERSONAS (debate team)

```
Solver reads PANDO-PLAN.md → lists 15 personas
Breaker 1: "Missing: app visitors, migrating users, AI agents as users"
Breaker 2: "Missing: moderators, API integrators, compliance officer"
Solver: 25 personas. Breakers: CONVERGED.

Result: 25 persona nodes in plan/
```

### Phase 2: USE CASES (debate team, per persona)

```
For Consumer:
  Solver: 12 use cases
  Breakers push: offline, mobile, disputes, export, accessibility...
  Result: 28 use cases

For Node Operator:
  Solver: 8 use cases
  Breakers push: crash recovery, upgrade, monitoring, earnings...
  Result: 18 use cases

... repeat for all 25 personas ...
Result: 400-700 use case nodes
```

### Phase 3: JOURNEYS

```
For each use case, agent writes step-by-step journey:
  "Consumer builds app":
    1. [Consumer] opens pando.network
    2. [Gateway] receives request
    3. [Content Safety] scans
    4. [Doorman] classifies
    ...15-25 steps with error paths

Result: 400-700 journey nodes
Each step references services in [brackets]
```

### Phase 4: SERVICES EMERGE

```
Across all journeys, [brackets] mention ~50 unique services:
  [Gateway], [Doorman], [Content Safety], [Build Service],
  [Auth Service], [Ledger], [Marketplace], [Hosting], ...

Engine detects dangling edges → creates service nodes.
Each service grows as more journeys reference it.
Services group into modules → modules into domains.

Result: ~50 service nodes, ~15 module nodes, ~5 domain nodes
```

### Phase 5: CODE

```
Each service has:
  - Use cases as requirements
  - Journeys as acceptance criteria

Agent reads these, writes TypeScript.
One service at a time. Focused.

Result: src/ with implementation files
```

### Phase 6: TEST

```
Each journey = one test:
  POST /api/build → expect 200
  GET /api/stream → expect SSE events
  GET app.pando.network → expect 200

Test fails → task on the service → agent fixes → retest.
Test reveals missing service → CREATE it → retest.

Result: all journeys pass = PANDO WORKS
```

### Estimated Output

```
Personas:    25-30
Use Cases:   400-700
Journeys:    400-700
Services:    40-60
Modules:     10-20
Domains:     5-7
Total Nodes: 900-1500+

Timeline: days, not hours (with persistent agents)
```

---

## EXISTING CODEBASE (Bottom-Up)

Same system works when starting from code instead of spec:

```
1. Scan code → create service nodes for what EXISTS
2. Infer journeys from code ("what does this actually do?")
3. Infer personas from journeys ("who uses this?")
4. Debate team: "what's MISSING?"
5. Create missing use cases + journeys
6. Build missing code
7. Test ALL journeys
8. Converge
```

Same engine, same nodes. Different starting point.

---

## ENGINE SOURCE STRUCTURE

```
genome5/
  src/
    node.py              # Node base, Task class
    genome.py            # Genome graph, hierarchy helpers, parent-child index
    loader.py            # Load Python files, AST validation, prune knowledge
    validator.py         # Universal checks: load errors, dangling edges, level consistency
    engine.py            # Convergence loop, snapshots, parallel dispatch, budgets
    agent_manager.py     # Claude Code processes, NDJSON, persistent sessions, dispatch IDs
    regression.py        # Regression detection, snapshot management
    cli.py               # CLI: check, converge, init, status

  seeds/
    complex-software/    # Service, Persona, Journey, UseCase, Test nodes
    book/                # Book, Chapter, Scene, Character nodes
    blank/               # Just base Node

  tests/                 # Engine tests
```

---

## PROJECT STRUCTURE

```
my-project/
  plan/
    context.yaml         # seed type, spec reference, description
    hr_agent.py          # bootstrapped by engine
    (agents create everything else — organize however they want)

  docs/
    spec.md              # requirements / spec

  src/                   # created during dev phase
  tests/                 # created during test phase
```

---

## CONFIG

```python
class ProjectConfig(Node):
    name = "Project Config"
    type = "config"

    max_parallel = 2          # agents thinking simultaneously
    stuck_threshold = 5       # fails before engine gives up on a task
    max_reverts = 3           # per-task revert limit
    agent_timeout = 600       # seconds per task
    convergence = "strict"    # 0 errors AND 0 warnings
    snapshot_interval = 10    # git commit every N cycles
    max_cycles = 5000         # total budget
    max_hours = 24            # wall clock budget
```

---

## OPEN SYSTEM — NO RIGID GATES

The system has NO phase gates. All work can happen simultaneously:
- New personas can be created ANYTIME (during journeys, dev, test)
- New use cases can be added ANYTIME
- Services emerge organically from journey [brackets]
- The debate team fires for INITIAL exhaustive discovery
- After convergence, system stays open for ongoing evolution

WAKE-UP LOGIC: If new personas appear after the persona debate converged,
the debate RE-OPENS to verify completeness. Same for use cases.
The system tracks persona_count_at_convergence — if count grows, debate wakes up.

DEBATE CONVERGENCE: All 3 agents (solver + 2 breakers) must say CONVERGED.
If debate hits 50 rounds without convergence, task re-fires next cycle.
Unconverged debates do NOT produce nodes.

ALL MODELS: claude-opus-4-6. Hardcoded. Cannot be overridden by agents.

---

## CHECKLIST: ARE WE BUILDING IT RIGHT?

When reviewing progress, verify:

- [ ] Agents are PERSISTENT sessions (not killed between tasks)
- [ ] Started with personas (not architecture)
- [ ] Debate team used for personas and use cases
- [ ] Debate CONVERGED (all 3 agreed) before phase marked done
- [ ] Each persona has 10+ use cases
- [ ] Each use case has a journey with error steps
- [ ] Journeys reference services in [brackets]
- [ ] Services EMERGED from journeys (not pre-planned)
- [ ] Hierarchy GREW from services (not imposed top-down)
- [ ] NO rigid gates — new nodes can be created anytime
- [ ] Wake-up works — new persona triggers debate re-open
- [ ] Tests REPLAY journeys
- [ ] Test failures CREATE new nodes (self-healing)
- [ ] ALL models are Opus (no Sonnet anywhere)
- [ ] Engine has NO domain knowledge (nodes are smart, engine is dumb)
- [ ] File-copy snapshots (not git per cycle)
- [ ] Debate log shows rounds and convergence status
