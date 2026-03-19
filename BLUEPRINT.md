# GENOME5 — THE FINAL PLAN

One document. Everything needed to build and run it.

---

## WHAT IS GENOME5

A system where AI agents plan, build, test, and maintain ANY project. The engine loads Python node files, calls validate() on each, routes tasks to agents, and repeats until done. Agents are persistent Claude Code Opus 4.6 sessions. Nodes remember context. The hierarchy grows organically. The system stays OPEN — new nodes can be created anytime, no phase gates.

---

## CORE PRINCIPLES

1. **Everything is a node** — .py file with name, edges, validate()
2. **Engine is dumb, nodes are smart** — engine just loads, validates, routes, loops
3. **Clean state separation** — engine state in engine_state.yaml, node content in .py files. Engine NEVER edits .py files. Only agents write .py files.
4. **Use-case-first** — personas → use cases → journeys → services EMERGE
5. **Debate team for exhaustive discovery** — 1 solver + 2 breakers, persistent sessions, must all CONVERGE
6. **Open system, no rigid gates** — new personas/UCs/services anytime
7. **Wake-up on change** — new persona appears → debate re-opens
7. **Ripple effect through nodes** — edges + staleness propagate changes automatically
8. **Always Opus 4.6** — hardcoded, cannot be overridden
9. **Experience teaches** — test failures create new nodes, system self-heals

---

## THE FLOW

```
INITIAL DISCOVERY (debate team, comprehensive):
  1. Debate: WHO uses this? → personas (all 3 must converge)
  2. Debate: WHAT can each persona do? → use cases (all 3 must converge, per persona)
  3. HOW does each use case work? → journeys (single agent, specific)
  4. Services EMERGE from journey [brackets] → dangling edges → created

ONGOING (open system, no gates):
  - New persona discovered during journey? → create it → debate wakes up
  - Test reveals missing scenario? → new use case + journey
  - Admin adds requirement? → new nodes, ripple through edges
  - System NEVER says "that phase is closed"
```

---

## THE DEBATE TEAM

### When It Fires
- Initial persona discovery (debate=True on task)
- Initial use case discovery per persona (debate=True)
- Any task where an agent sets debate=True (open to any node's validate())

### How It Works
```
1 SOLVER: proposes answer, integrates feedback
2 BREAKERS: find flaws and gaps, hint at solutions

Rounds alternate until ALL THREE say CONVERGED.
Max 50 rounds. If not converged → task re-fires next cycle.
Unconverged debates do NOT produce nodes.
All rounds logged to plan/debate_log.md.
```

### Convergence Enforcement
- Engine checks: did all 3 say CONVERGED?
- If YES → nodes created, convergence status saved to workflow node
- If NO → task stays in queue, debate re-runs next cycle
- Planning workflow tracks: persona_debate_converged, persona_count_at_convergence, per-persona UC convergence

### Wake-Up Logic
- Engine tracks persona count when debate converged
- If new personas appear later → persona_debate_converged resets to False
- Debate re-opens to verify the new list is comprehensive
- Same mechanism available for use cases

### Parallel Debates
- Multiple debates run simultaneously via ThreadPoolExecutor
- max_parallel debates at once (default 2)
- Each debate writes to different files (different personas) → no conflicts

---

## THE ENGINE

### Core Loop
```python
while True:
    genome = load_all_python_files("plan/")
    tasks = validate_all(genome)    # universal checks + per-node validate()

    if no tasks: CONVERGED
    if budget_exceeded: PAUSED

    # Debate tasks: run 1+2 debate, must converge
    # Fresh session tasks: one-shot agent for exhaustion checks
    # Normal tasks: persistent agent session

    snapshot()
    result = dispatch(task)
    if regression: restore()
    else: checkpoint()
```

### Engine Features
1. **File-copy snapshots** — not git per cycle. Git every N cycles for checkpoints.
2. **AST validation** — parse before import. Reject dangerous code. Import whitelist.
3. **Parallel dispatch** — one task per distinct agent, think in parallel, apply serially.
4. **Dispatch IDs** — UUID prevents stale completion signals from ghost threads.
5. **Cycle detection** — (node_name, check_id, context) triple. 3 repeats = skip.
6. **Regression guard** — new critical errors without fixing assigned task → revert.
7. **Crash logging** — plan/engine-crash.log with full traceback.
8. **Convergence budgets** — max_cycles, max_hours. Pauses and reports.
9. **Mutable defaults** — Node.__init__ creates per-instance copies.
10. **Level consistency** — node.level must equal parent.level + 1.
11. **Dangling edges** — reference to non-existent node → task to create it.
12. **Staleness** — info-level only. One level deep.
13. **Debate handling** — task.debate=True → run_debate(), must converge.
14. **Fresh sessions** — task.fresh_session=True → one-shot agent, no prior context.
15. **Exhaustion lifecycle** — engine-enforced States 3+4 for expected_children nodes.
16. **Debate convergence tracking** — saves to workflow node file on disk.

### Engine State Management
Engine stores ALL its state in `plan/engine_state.yaml`:
- Debate convergence per check ID (converged: true/false, persona count, time)
- Engine NEVER edits .py node files — only agents do
- Planning workflow READS engine_state.yaml to check convergence
- Clean separation: engine owns engine state, agents own node content

### What Engine Does NOT Do
- No domain knowledge. Doesn't know what "persona" or "service" means.
- No opinions. No verb lists, no type checks, no quality judgments.
- No planning logic. All planning lives in node validate() methods.
- No .py file editing. Engine reads .py files, never writes them.

---

## AGENTS

### Model
ALL agents use claude-opus-4-6. Hardcoded as DEFAULT_MODEL constant. Agent node model field is IGNORED. Cannot be overridden.

### Persistent Sessions
Each agent is a long-lived Claude Code process. NOT killed between tasks. Accumulates context. NDJSON stdin/stdout communication.

### Fresh Sessions
For exhaustion State 3 (re-read spec) and State 4 (reviewer). One-shot process with --dangerously-skip-permissions. Different LLM sampling paths. Killed after task completes.

### Agent Instructions (3 layers)
1. **System prompt** — identity only: "You are [name]. [description]."
2. **Task message** — specific instructions for THIS task
3. **Agent guide seed** — concrete examples of every pattern

### Bootstrap
Engine creates HR Agent if no agents exist. HR Agent reads spec + context.yaml, creates specialists.

---

## EXHAUSTION LIFECYCLE (engine-enforced)

For any node with expected_children, the engine automatically runs:

```
State 2: children missing → task to create them (from node validate())
State 3: all exist + NOT verified → FRESH agent re-reads spec
         Shows descriptions (not names) to avoid confirmation bias.
         Expands spec reading range ±20 lines.
State 4: verified + NOT reviewed → FRESH reviewer with sibling comparison.
```

This is in the ENGINE (src/validator.py), not the seeds. Cannot be bypassed.

---

## NODES

### Base Class
```python
class Node:
    name, type, level, description
    spec_reference          # section header anchors
    expected_children       # exact child node names
    children_verified       # True after exhaustion State 3
    children_reviewed       # True after State 4 reviewer
    edges                   # parent, owned_by, calls, depends_on
    files                   # source files (dev phase)
    doc, decisions, knowledge  # structured memory

    def validate(self, genome) → list[Task]
    def children(self, genome) → list[Node]
    def parent_node(self, genome) → Node
    def get_owner(self, genome) → Node
```

### Task
```python
class Task:
    message, node_name, phase, priority, severity
    check, suggestion, context
    fresh_session: bool     # engine spawns fresh agent
    debate: bool            # engine runs 1+2 debate
```

---

## HIERARCHY

Grows BOTTOM-UP from journey references:
```
Journeys reference [services] → dangling edges → services created
Services group into modules → modules into domains
```

Two journey types:
1. **Persona journeys** — human triggers: "Consumer builds app"
2. **Operational journeys** — system event: "Node crashes, projects migrate"

Impact radius isolated by edges — change one branch, others untouched.

---

## SEED SYSTEM

Seeds are examples, NOT law. Agents modify freely.

```
seeds/complex-software/
  agent_guide.py          — how genome5 works (concrete examples)
  base_classes.py         — ServiceNode, PersonaNode, JourneyNode, etc.
  planning_workflow.py    — use-case-first flow with debate + wake-up
```

Seeds copied to plan/ at bootstrap. base_classes.py stays in seeds/ (imported, not copied).

---

## FULL LIFECYCLE FOR PANDO

```
1. DEBATE: Discover ALL personas (47 found for Pando, all 3 converged)
2. DEBATE per persona: Discover ALL use cases (30-40 per persona)
3. JOURNEYS: Step-by-step for each use case (10-25 steps, [brackets])
4. SERVICES EMERGE: dangling edges from [brackets] → auto-created
5. CODE: Each service has use cases as requirements, journeys as acceptance criteria
6. TEST: Replay journeys. Fail → fix → retest. Missing scenario → new UC.

ONGOING: new personas, use cases, services created anytime.
Wake-up: debate re-opens if new personas appear.
Ripple: edges propagate changes through the entire system.
```

Expected output for Pando: 1000+ use cases, 1000+ journeys, 50+ services.

---

## ENGINE SOURCE

```
genome5/
  src/
    node.py, genome.py, loader.py, validator.py
    engine.py, agent_manager.py, regression.py
    debate.py, cli.py
  seeds/complex-software/
    agent_guide.py, base_classes.py, planning_workflow.py
  tests/test_core.py (23 tests)
```

---

## CONFIG

```python
max_parallel = 2, agent_timeout = 600, max_cycles = 5000
max_hours = 24, snapshot_interval = 10, convergence = "strict"
```

---

## CHECKLIST: ARE WE BUILDING IT RIGHT?

- [ ] ALL models Opus 4.6 (no Sonnet anywhere)
- [ ] Debate team used for persona + use case discovery
- [ ] Debate CONVERGED (all 3 agreed) — check debate_log.md
- [ ] NO rigid gates — new nodes created anytime
- [ ] Wake-up works — new persona → debate re-opens
- [ ] Personas created BEFORE services (use-case-first)
- [ ] Services EMERGED from journey [brackets] (not pre-planned)
- [ ] Exhaustion lifecycle engine-enforced (States 3+4, fresh sessions)
- [ ] Persistent agent sessions (not killed between tasks)
- [ ] File-copy snapshots (not git per cycle)
- [ ] Debate log records rounds + convergence status
- [ ] Ripple effect works — change propagates through edges
- [ ] Test failures create new nodes (self-healing)
