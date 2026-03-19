# GENOME5 SELF-REVIEW -- Final Pre-Launch Audit

All 15 files read in full. 23 tests confirmed passing.
Review date: 2026-03-19

---

## CRITICAL ISSUES

### C1. Near-Duplicate Detection Missing from Code
**File:** `src/validator.py`
**Blueprint says (item 10):** "Near-duplicate detection -- Levenshtein distance < 3 between node names -> reconciliation task. Pre-filtered for performance."
**What's there:** Nothing. The function does not exist. The checklist does not mention it either.
**Impact:** Two agents could independently create "Auth Service" and "Auth Services" and the engine would never notice. Over hundreds of nodes, near-duplicates will silently fragment the plan.
**Fix:** Add `_check_near_duplicates(genome)` to `validate_genome()`. Use a simple Levenshtein implementation (no external import needed -- can be done in ~15 lines). Pre-filter by length difference > 3 to avoid O(n^2) on large graphs.

### C2. Content-Hash Staleness Dismissal Missing
**File:** `src/validator.py`, line 93-104
**Blueprint says (item 13):** "Content-hash to auto-dismiss unchanged nodes."
**What's there:** `_check_staleness` compares `_mtime` only. There is no content hash anywhere.
**Impact:** Every time a parent is touched (even whitespace change), all children get staleness warnings. Over hundreds of nodes this generates noise that drowns real issues. Agents waste cycles on false staleness.
**Fix:** In `loader.py`, compute `hashlib.md5(source.encode()).hexdigest()` and store it as `node._content_hash`. In `_check_staleness`, compare content hashes rather than (or in addition to) mtimes. Dismiss staleness when content hash is unchanged.

### C3. Debate Team Uses One-Shot Sessions, NOT Persistent Sessions
**File:** `src/debate.py`, lines 86-101
**Blueprint says (Debate Team section):** "Three persistent Claude Code sessions."
**What's there:** `call_agent()` uses `subprocess.run()` -- a one-shot call per turn. Each round spawns a new process, discards it, and passes the full debate history as text in the prompt.
**Impact:** This fundamentally works (the debate history is passed), but:
  - Each round pays full Claude startup cost (~5-10s).
  - For 12 rounds, that's 12 process spawns instead of 3.
  - History grows linearly in prompt size (no truncation after round 2 for context).
  - The blueprint explicitly says "persistent sessions."
**Fix:** Either (a) accept this as a deliberate simplification and update the blueprint, or (b) use `AgentManager._get_or_spawn()` with unique debate agent names like "SOLVER", "BREAKER 1", "BREAKER 2" to get persistent sessions. Option (a) is safer for launch; the current approach works correctly, just slower.

### C4. Debate Does Not Produce Node FILES -- And the Fallback Has a Bug
**File:** `src/engine.py`, lines 132-167
**What happens:** After `run_debate()` returns, the engine reloads the genome and compares node counts. If no new nodes were created, it creates a followup Task and calls `agent_manager.assign_task()` (synchronous).
**Bug:** The synchronous `assign_task()` call at line 158 happens INSIDE the dispatch loop (lines 119-206). After `assign_task()` completes synchronously, execution falls through to `continue` at line 167, then the outer for-loop continues dispatching more tasks. This means:
  1. The debate followup runs synchronously, blocking the entire dispatch loop.
  2. Nothing puts the debate result into `pending`, so the collect phase never fires for it.
  3. No regression check is performed on the debate followup result.
  4. No snapshot is taken before the debate followup runs.
**Impact:** If the debate followup agent damages the plan, there is no rollback. The regression guard is bypassed for all debate results.
**Fix:** Either (a) put the debate followup into `pending` like normal tasks and let the collect phase handle it, or (b) at minimum take a snapshot before the synchronous call and run regression detection afterward. Option (b) is simpler:
```python
snapshot_mgr.snapshot()  # before the sync call
result = agent_manager.assign_task({...})
# run regression detection
after_genome, after_issues = check(project_dir)
regression = detect_regression(followup, list(issues), after_issues)
if regression:
    snapshot_mgr.restore()
```

### C5. `_seed_project` Only Copies .py Files from Seeds, Misses planning_workflow.py and agent_guide.py
**File:** `src/engine.py`, lines 375-401
**What happens:** `_seed_project()` copies `.py` files from `seeds/{seed_name}/` to `plan/`. The seed dir for "complex-software" contains `planning_workflow.py`, `base_classes.py`, and `agent_guide.py`.
**But:** `base_classes.py` should NOT be copied to `plan/` -- it is imported by loader.py as `genome5.seeds`. If it gets copied to `plan/`, the loader will try to load it as a node file. The `_find_node_class()` function looks for `Node` subclasses defined in the module. `base_classes.py` defines `ServiceNode`, `PersonaNode`, `JourneyNode`, `AgentNode`, `UseCaseNode`, `TestNode`, `ConfigNode` -- ALL of which have `obj.__module__ == module.__name__` when loaded from plan/. But none have a non-empty `name`, so `_load_node_from_file` will return `(None, None)` at line 117. This is a silent no-op, not a crash, but it's confusing.
**The Real Problem:** `planning_workflow.py` and `agent_guide.py` DO have `name` attributes and WILL be loaded as nodes. This is correct -- they are meant to be in `plan/`. But `base_classes.py` will be copied and silently ignored. Wasted I/O.
**Fix:** In `_seed_project`, skip `base_classes.py`:
```python
if fname.endswith(".py") and not fname.startswith("_") and fname != "base_classes.py":
```
Or better: add a `__init__.py` flag or naming convention (prefix with `_`) for seed files that are library-only.

---

## HIGH ISSUES

### H1. `_reader` Thread Never Terminates on Agent Respawn
**File:** `src/agent_manager.py`, lines 195-218
**What happens:** When `_send_async` is called, it spawns a daemon thread that reads from `proc.stdout` until it gets a "result" message or EOF. If the agent times out (line 61-68), the process is killed and `info["alive"]` is set to False.
**But:** The old `_reader` thread for the killed process may still be blocking on `proc.stdout.readline()`. When the process is killed, readline() should return empty bytes (EOF), which triggers line 200-201 and puts an error into `result_q` and `completion_q`.
**Edge case:** On Windows, killing a process with `taskkill /T /F` sometimes leaves zombie pipes. If `readline()` hangs forever on a dead pipe, the thread leaks. Over many agent respawns, this could accumulate threads.
**Impact:** Thread leak over long runs (hours). May cause memory growth or file descriptor exhaustion.
**Fix:** Add a timeout mechanism to the reader thread. The simplest approach: before spawning the reader, store a reference to it. On kill, close the stdout pipe explicitly:
```python
proc.stdout.close()  # forces readline() to return EOF
```
Add this in the `kill()` method before `proc.kill()`.

### H2. Race Condition in Parallel Dispatch: `dispatched` Set vs `pending` Dict
**File:** `src/engine.py`, lines 119-206
**What happens:** The dispatch loop tracks `dispatched` (a set of agent names) and `pending` (a dict of agent names). When dispatching, it checks `owner.name in dispatched` to avoid double-dispatch. But `dispatched` is a local variable that only lives during one dispatch pass. `pending` persists across cycles.
**Scenario:** Agent A finishes. Collect phase runs. `pending` now has only Agent B. Next dispatch pass: `dispatched` is empty. If a new task targets Agent A (which is now free), it will be dispatched -- but Agent B's result hasn't been collected yet.
**But wait:** The code at line 104 checks `if not pending:` before entering dispatch. So dispatch only runs when ALL agents are done. This means max_parallel > 1 is partially broken: the engine dispatches N tasks, then waits for ALL to finish before dispatching again. It does not dispatch new tasks as agents finish.
**Impact:** With `max_parallel=2`, if Agent A finishes in 30s and Agent B takes 300s, Agent A sits idle for 270s. The engine is not truly parallel -- it's batched.
**Fix:** Change the loop structure to dispatch new tasks whenever an agent finishes, not just when all are done. This requires moving the dispatch logic inside the collect phase, or maintaining the pending dict across cycles more carefully.

### H3. `owned_by` Edges Skip Dangling Edge Check
**File:** `src/validator.py`, lines 63-64
**What happens:** `_check_dangling_edges` explicitly skips `owned_by` edges: `if etype.startswith("_") or etype == "owned_by": continue`.
**Impact:** If an agent is deleted or renamed, all nodes with `owned_by: "Old Agent Name"` will silently have no owner. The `_find_owner()` fallback in engine.py will route tasks to the first agent found, which may be the wrong agent.
**Fix:** Remove the `owned_by` skip. Dangling `owned_by` edges are just as important as dangling `calls` edges. The skip was likely added to avoid noise during bootstrap when agents haven't been created yet, but the engine bootstraps HR Agent before validation runs, so this is no longer necessary.

### H4. `TestNode.run()` Mutates `self.last_result` But Node Is Reloaded From Disk
**File:** `seeds/complex-software/base_classes.py`, lines 196-229
**What happens:** `TestNode.run()` stores results in `self.last_result`. But the node was loaded from a `.py` file on disk. On the next engine cycle, the genome is rebuilt from disk, and the in-memory `last_result` is lost. The test result only persists if the agent modifies the `.py` file to include the result.
**Impact:** Test results are lost between cycles. The test will re-run every cycle (since `runnable=True` and `last_result` is always `{}`). If tests are expensive (e.g., Playwright), this wastes enormous time.
**Fix:** Either (a) have `TestNode.run()` write results back to the `.py` file (fragile), or (b) have the engine persist test results in a separate `test_results.yaml` file that survives reloads, or (c) have the engine track which tests passed in the current session. Option (c) is simplest:
```python
# In engine.py, track test results
test_results: dict[str, dict] = {}
# After node.run():
test_results[node.name] = result
# Before running: skip if test_results[node.name]["success"] == True
```

### H5. `_find_owner` Falls Back to First Agent -- Regardless of Capabilities
**File:** `src/engine.py`, lines 406-414
**What happens:** If a task's node has no `owned_by` edge, `_find_owner` returns `agents[0]` -- the first agent found. This could be HR Agent, Agent Guide, or any agent alphabetically first.
**Impact:** Tasks for unowned nodes (like load errors, or nodes created by debate but without ownership) will always go to the same fallback agent, regardless of whether that agent is appropriate. In the worst case, HR Agent gets asked to fix code.
**Fix:** Add capability matching. Or at minimum, prefer agents with `team-management` capability for structural tasks and other agents for domain tasks:
```python
if not owner:
    if task.phase == "structural":
        for a in agents:
            if "team-management" in getattr(a, "capabilities", []):
                return a
    return agents[0] if agents else None
```

### H6. No `--dangerously-skip-permissions` on Fresh Sessions
**File:** `src/agent_manager.py`, lines 102-107
**What happens:** `assign_task_fresh` runs `subprocess.run(["claude", "--output-format", "text", "--model", model], ...)`. No `--dangerously-skip-permissions` flag.
**But:** Persistent sessions at line 157 DO have `--dangerously-skip-permissions`.
**Impact:** Fresh sessions (used for exhaustion State 3 and State 4) will be blocked by Claude's permission system. The agent cannot write files, so it cannot modify nodes to set `children_verified = True` or add new children to `expected_children`. The fresh session will output text but make no changes.
**Fix:** Add `--dangerously-skip-permissions` to the fresh session command:
```python
result = subprocess.run(
    ["claude", "--output-format", "text", "--model", model,
     "--dangerously-skip-permissions"],
    ...
)
```

### H7. `_ensure_genome5_importable` Seeds Module Loads `base_classes.py` Without AST Validation
**File:** `src/loader.py`, lines 137-166
**What happens:** `_ensure_genome5_importable` loads `seeds/base_classes.py` via `exec(code, seeds_mod.__dict__)`. This bypasses the AST validation that all other node files go through.
**Impact:** If `base_classes.py` is modified (it's a seed, not frozen), malicious or buggy imports could execute. Also, `base_classes.py` imports `subprocess` (line 9) which is NOT in `ALLOWED_IMPORTS`. If an agent copies base_classes.py patterns and includes `import subprocess`, AST validation will reject it. But the seed itself uses it.
**Fix:** Either (a) add `subprocess` to `ALLOWED_IMPORTS` for node files, or (b) remove the `import subprocess` from base_classes.py and move the `TestNode.run()` subprocess call to the engine. Option (b) is cleaner architecturally -- the engine should run tests, not nodes.

---

## MEDIUM ISSUES

### M1. `properties` Dict Not Deep-Copied
**File:** `src/node.py`, line 78
**What happens:** `self.properties = dict(getattr(type(self), 'properties', {}))`. This is a shallow copy. If a property value is a list (e.g., `properties = {"goals": ["a", "b"]}`), the inner list is shared across instances.
**Impact:** Unlikely to cause issues in practice since nodes are loaded fresh each cycle, but it violates the principle established by the other mutable default fixes.
**Fix:** Use `copy.deepcopy` or manually deep-copy:
```python
import copy
self.properties = copy.deepcopy(getattr(type(self), 'properties', {}))
```

### M2. `init` Command Leaks File Handle
**File:** `src/cli.py`, line 72
**What happens:** `yaml.dump(..., open(ctx_path, "w", encoding="utf-8"), ...)` -- the file is opened inline without a `with` statement. On CPython, the refcount GC will close it, but it's a resource leak on other implementations.
**Fix:**
```python
with open(ctx_path, "w", encoding="utf-8") as f:
    yaml.dump({"seed": seed, "description": "New genome5 project"}, f, default_flow_style=False)
```

### M3. Convergence Check Ignores `info` Severity Tasks
**File:** `src/engine.py`, lines 90-101
**What happens:** Convergence checks for `strict` mode require zero errors AND zero warnings. But `eligible` filtering at line 107 only dispatches `error` and `warning` tasks. Info tasks are never dispatched.
**Edge Case:** If all errors and warnings are fixed, but info tasks remain, convergence is declared. This is correct behavior per the blueprint. However, info tasks from staleness checks will accumulate indefinitely in `issues.yaml`. This is noise, not a bug.

### M4. Cycle Detection Key Uses `context` Field Which Is Almost Always Empty
**File:** `src/engine.py`, line 277, `src/node.py`, line 31
**What happens:** Cycle detection key is `(node_name, check, context)`. The `context` field on Task defaults to `""` and is almost never set by any validate() method.
**Impact:** The cycle detection works, but the `context` field adds no value. All cycle keys are effectively `(node_name, check, "")`. This means if two different situations produce the same `(node_name, check)` but with different causes, the cycle detector will conflate them.
**Fix:** Either remove `context` from the cycle key (simplify), or have templates actually populate it. For example, exhaustion checks could set `context=f"children:{len(existing)}"` so that cycle detection distinguishes "3 children exist" from "5 children exist."

### M5. `planning_workflow.py` Phase Completion Uses Agent `doc` Field -- Fragile Signal
**File:** `seeds/complex-software/planning_workflow.py`, lines 43-45, 91-93, 142-144
**What happens:** Phase completion is detected by checking if ANY agent's `doc` field starts with "Personas complete" (case-insensitive). The agent must know to write this exact prefix.
**Impact:** If an agent writes "All personas are complete" or "personas: complete", the gate never opens. The system stalls. The agent guide does mention this convention (line 56-57 of agent_guide.py: "set your doc field to 'Personas complete. [count] personas created.'"), but it's a single sentence that the agent must remember.
**Fix:** Consider using a more structured signal. For example, a dedicated field on the PlanningWorkflow node: `persona_phase_complete = False`. Or check for a wider set of patterns. At minimum, add the expected doc prefix strings to the task suggestion text that gets sent to agents.

### M6. Debate Convergence Requires All 3 Roles to Have Responded AND All Say CONVERGED
**File:** `src/debate.py`, lines 141-155
**What happens:** After any response contains "CONVERGED", the code checks if all roles' LATEST responses contain "CONVERGED". But for this to be true, each role must have responded at least once with CONVERGED.
**Edge case:** The round order is Solver(1), Breaker1(2), Breaker2(3), Solver(4), Breaker1(5), Breaker2(6), ... If the Solver says CONVERGED in round 4, but Breaker1 and Breaker2 haven't said it yet, the debate continues. Then Breaker1 says CONVERGED in round 5. But Breaker2 said something non-CONVERGED in round 3. Round 6: Breaker2 says CONVERGED. Now all are converged.
**But:** The check at line 153 requires `round_num >= 4`. If all three converge in their FIRST responses (rounds 1-3), the minimum is round 3, which is < 4. The debate would continue unnecessarily.
**Impact:** Minor. The debate might run 1-3 extra rounds. This is actually a feature (prevents premature convergence).

### M7. `agent_manager._build_prompt` Includes Agent Guide Implicitly But Not Explicitly
**File:** `src/agent_manager.py`, lines 230-277
**What happens:** The prompt is built from the task. Context files include the agent's source file and connected nodes. In `base_classes.py:AgentNode.before_work()` (line 130-132), workflow and guide nodes are added to context. So the agent guide IS included.
**But:** The prompt itself (line 233-243) gives a very terse 4-line explanation of genome5. The agent guide is just listed as a file to read. There is no guarantee the agent will actually read it -- especially in fresh sessions where the agent has no prior context.
**Fix:** Include the key principles from the agent guide directly in the prompt for fresh sessions. Or at minimum, add "READ THESE FILES FIRST -- they contain critical instructions" with emphasis.

### M8. `TestNode.last_result` Uses Mutable Default Dict
**File:** `seeds/complex-software/base_classes.py`, line 169
**What happens:** `last_result: dict = {}` is a class-level mutable default. Unlike the base `Node` class, `TestNode.__init__` does not create a per-instance copy of `last_result`.
**Impact:** If two TestNode instances exist (unlikely in practice since each node file defines one class), they would share `last_result`. More importantly, modifications to `last_result` via `self.last_result = {...}` (assignment, not mutation) create an instance attribute, so this is actually fine for the `run()` method which does `self.last_result = {...}`. But `.get("success")` in `validate()` reads from the class dict if no instance attribute exists, which returns `None`, not `False`. So the validate check `self.last_result.get("success") is False` correctly returns False only when `run()` has been called. This is correct behavior but confusing.

### M9. No Handling for Multiple Node Classes in One File
**File:** `src/loader.py`, lines 123-132
**What happens:** `_find_node_class` returns the FIRST `Node` subclass found. If a file defines multiple node classes (e.g., a helper class and the actual node), only the first is loaded.
**Impact:** Agents might define helper base classes in the same file. The wrong class could be picked. `dir()` returns names in alphabetical order, so `class AHelper(Node)` would be found before `class ZActualNode(Node)`.
**Fix:** Either (a) document that only one Node subclass per file is supported, or (b) prefer the class with a non-empty `name` attribute. The current code already filters for `instance.name` at line 114, but `_find_node_class` returns the class, not the instance. If `AHelper` has `name = ""` and `ZActualNode` has `name = "Real"`, the current code will instantiate `AHelper`, find no name, and return `(None, None)` -- missing `ZActualNode` entirely.
**Fix (concrete):** Change `_find_node_class` to iterate all classes and prefer the one with a non-empty `name`:
```python
def _find_node_class(module) -> type | None:
    candidates = []
    for attr_name in dir(module):
        obj = getattr(module, attr_name)
        if (isinstance(obj, type) and issubclass(obj, Node)
                and obj is not Node and obj.__module__ == module.__name__):
            candidates.append(obj)
    # Prefer classes with a name set
    for cls in candidates:
        if getattr(cls, 'name', ''):
            return cls
    return candidates[0] if candidates else None
```

### M10. `genome5.seeds` Module Not Populated with Correct Seed
**File:** `src/loader.py`, lines 150-166
**What happens:** `_ensure_genome5_importable` always loads `seeds/base_classes.py` from the genome5 engine directory. It does NOT load seed-specific base classes from the project's configured seed.
**Impact:** This works for `complex-software` seed because `base_classes.py` is in that directory. But the code assumes the file is at `seeds/base_classes.py` -- but it's actually at `seeds/complex-software/base_classes.py`. The path constructed at line 155 resolves to `genome5/seeds/base_classes.py` which does NOT exist.
**Wait -- let me recheck:** Line 154: `seeds_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seeds")`. `__file__` is `src/loader.py`, so `os.path.dirname(os.path.dirname(...))` is the genome5 root. `seeds_dir` = `genome5/seeds/`. Line 156: `seed_classes_file = os.path.join(seeds_dir, "base_classes.py")` = `genome5/seeds/base_classes.py`. This file does NOT exist -- it's at `genome5/seeds/complex-software/base_classes.py`.
**Impact: CRITICAL.** `from genome5.seeds import ServiceNode` will fail for agents. The import will succeed (the module exists), but `ServiceNode` will not be in it. Agents will get `ImportError: cannot import name 'ServiceNode' from 'genome5.seeds'`.
**Fix:** Change the path to search seed subdirectories, or load from the correct location:
```python
# Option: search all seed directories for base_classes.py
for seed_subdir in os.listdir(seeds_dir):
    candidate = os.path.join(seeds_dir, seed_subdir, "base_classes.py")
    if os.path.exists(candidate):
        # load it
        break
```
Or better: use the project's configured seed name to locate the right base_classes.py.

**SEVERITY UPGRADE: This is actually CRITICAL. Agents using seed classes will crash on import.**

---

## ADDITIONAL OBSERVATIONS

### O1. Blueprint Mentions "5-second timeout" for AST Validation -- Not Implemented
**File:** `src/loader.py`, line 61-89
**Blueprint says:** "5-second timeout" for AST validation.
**What's there:** No timeout. `ast.parse()` is synchronous with no timeout.
**Impact:** Minimal. Python AST parsing is fast even for large files. Not a real risk.

### O2. Blueprint Mentions 10 Engine Features -- Item 10 (Near-Duplicate) Missing
Cross-reference with C1 above. The blueprint lists 14 features. Items actually implemented:
1. File-copy snapshots -- YES
2. AST validation -- YES
3. Parallel dispatch -- PARTIAL (H2: batched, not truly parallel)
4. Dispatch IDs -- YES
5. Cycle detection -- YES
6. Regression guard -- YES (but bypassed for debate, see C4)
7. Crash logging -- YES
8. Convergence budgets -- YES
9. Mutable defaults fix -- YES
10. Near-duplicate detection -- NO (C1)
11. Level consistency -- YES
12. Dangling edge detection -- YES
13. Staleness -- PARTIAL (no content hash, see C2)
14. Windows support -- YES

### O3. No `book/` or `game/` Seeds Exist
**Blueprint says:** `seeds/book/`, `seeds/game/`, `seeds/blank/` exist.
**Actual:** Only `seeds/complex-software/` and `seeds/blank/` (with just `__init__.py`) exist.
**Impact:** None for launch. Just incomplete relative to blueprint.

### O4. `engine.py` Runs Tests Inside the Convergence Loop
**File:** `src/engine.py`, lines 67-81
**What happens:** Every time `pending` is empty, the engine runs ALL `runnable` nodes. Tests run before dispatch, not as separate tasks.
**Impact:** This is correct per the blueprint lifecycle. But if a test modifies state (e.g., creates database records), running it every cycle could have side effects. The `ran_any` flag triggers re-validation, which is good.

### O5. Debate Agents Get `--dangerously-skip-permissions` but Fresh Sessions Do Not
Cross-reference with H6. This inconsistency is confusing: debate agents (line 89 of debate.py) CAN write files, but exhaustion/review fresh sessions (line 103 of agent_manager.py) CANNOT.

---

## SUMMARY OF FIXES BY PRIORITY

### Must Fix Before Launch (CRITICAL):
1. **M10 (upgraded to CRITICAL):** `genome5.seeds` import path is wrong -- `base_classes.py` not found at `seeds/base_classes.py`. Agents will crash.
2. **H6:** Fresh sessions lack `--dangerously-skip-permissions`. Exhaustion lifecycle cannot modify files.
3. **C4:** Debate followup bypasses regression guard. No snapshot before sync call.

### Should Fix Before Launch (HIGH):
4. **C1:** Near-duplicate detection missing entirely.
5. **C2:** Content-hash staleness missing -- false staleness noise.
6. **H3:** `owned_by` edges skip dangling check -- deleted agents create orphans.
7. **H4:** TestNode results lost between cycles -- tests re-run every cycle.
8. **H7:** `base_classes.py` imports `subprocess` but it's not in `ALLOWED_IMPORTS`.
9. **M9:** Multiple Node classes per file -- wrong class picked if alphabetically first.

### Nice to Fix (MEDIUM):
10. **C3:** Debate uses one-shot sessions instead of persistent (works but slow).
11. **H1:** Reader threads may leak on Windows pipe zombies.
12. **H2:** Parallel dispatch is batched, not truly parallel.
13. **H5:** `_find_owner` fallback ignores capabilities.
14. **M1:** Properties dict shallow-copied.
15. **M2:** File handle leak in CLI init command.
16. **M4:** Cycle detection `context` field unused.
17. **M5:** Phase completion uses fragile string matching on agent doc field.

### Informational:
18. **O1:** AST timeout not implemented (low risk).
19. **O2:** 12 of 14 blueprint features implemented.
20. **O3:** Book/game seeds not created (not needed for launch).

---

## VERDICT

**Not ready for launch.** Three issues will cause runtime failures:

1. `from genome5.seeds import ServiceNode` will crash because the path resolution is wrong (M10).
2. Fresh sessions cannot write files because `--dangerously-skip-permissions` is missing (H6).
3. Debate followups bypass regression protection (C4).

Fix these three and the system will run. The other issues will cause inefficiency, noise, or edge-case bugs, but won't prevent operation.
