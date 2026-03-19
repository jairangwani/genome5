# Implementation Checklist — DO NOT COMMIT until ALL are done

## ENGINE (src/engine.py)
- [x] Convergence loop (load → validate → route → fix)
- [x] File-copy snapshots (SnapshotManager)
- [x] Git checkpoints every N cycles
- [x] Parallel dispatch with serial apply
- [x] Dispatch IDs prevent stale signals
- [x] Cycle detection (node_name, check_id, context)
- [x] Regression guard
- [x] Crash logging
- [x] Convergence budgets (cycles, hours)
- [x] HR Agent bootstrap
- [x] **DEBATE TEAM** — engine detects task.debate=True → runs run_debate()
- [x] **FRESH SESSION** — engine detects task.fresh_session=True → runs assign_task_fresh()

## LOADER (src/loader.py)
- [x] Walk plan/ recursively
- [x] AST validation before import
- [x] Load error tracking
- [x] Knowledge pruning to last 8
- [x] genome5 importable

## VALIDATOR (src/validator.py)
- [x] Load errors → structural tasks
- [x] Dangling edges
- [x] Level consistency
- [x] Staleness (info-level, one level deep)
- [x] **EXHAUSTION State 3** — engine fires when all children exist + not verified (fresh_session=True)
- [x] **EXHAUSTION State 4** — engine fires when verified + not reviewed (fresh_session=True)
- [x] Sibling comparison in reviewer task message

## AGENT MANAGER (src/agent_manager.py)
- [x] Persistent Claude Code sessions
- [x] NDJSON stdin/stdout
- [x] Dispatch IDs
- [x] Timeout + respawn
- [x] Parallel dispatch
- [x] Windows taskkill
- [x] **assign_task_fresh()** — one-shot fresh session for exhaustion/review

## DEBATE TEAM (src/debate.py)
- [x] 1 Solver + 2 Breakers
- [x] Alternating rounds until CONVERGED
- [x] Context management (full context first rounds, summary later)
- [x] Returns solver's final output

## SEED: PLANNING WORKFLOW (seeds/complex-software/planning_workflow.py)
- [x] **USE-CASE-FIRST ORDERING** — Phase 1→2→3→4 with gates
- [x] Phase 1: personas (with exhaustion prompt)
- [x] Phase 2: use cases per persona (10-20 per persona)
- [x] Phase 3: journeys per use case
- [x] Phase 4: services review (emerge from journeys)

## SEED: AGENT GUIDE (seeds/complex-software/agent_guide.py)
- [x] Examples for node creation
- [x] Examples for journeys
- [x] Examples for personas
- [x] **USE-CASE-FIRST INSTRUCTIONS** — explicit ordering
- [x] **EXHAUSTION INSTRUCTIONS** — explains what engine enforces
- [x] **DEBATE TEAM INSTRUCTIONS** — explains when it fires

## NODE (src/node.py)
- [x] Mutable defaults fix (__init__)
- [x] children_verified field
- [x] children_reviewed field
- [x] Task.fresh_session field
- [x] Task.debate field
- [x] Task.context field

## TESTS (23 passing)
- [x] Node basics (name, description, mutable defaults, owner)
- [x] Genome (types, parent index)
- [x] Validator (dangling edges, level consistency)
- [x] Regression (fixed, not fixed, new criticals)
- [x] Loader (empty, load node, errors, prune knowledge)
- [x] Exhaustion State 3 fires (fresh_session=True)
- [x] Exhaustion State 4 fires (fresh_session=True)
- [x] Exhaustion complete (no tasks)
- [x] Task debate flag
- [x] Task fresh_session flag

## STATUS: READY TO COMMIT
All checklist items complete. 23 tests passing.
