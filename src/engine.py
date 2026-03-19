"""genome5 Engine — the convergence loop.

Load nodes -> validate -> route -> fix -> converge.
File-copy snapshots. Parallel dispatch. Cycle detection. Budgets.
The engine is DUMB. Nodes are SMART.
"""

import os
import subprocess
import yaml
import time

from src.loader import load_genome
from src.validator import validate_genome, prioritize
from src.regression import detect_regression, log_regression, load_regression_history, SnapshotManager
from src.node import Task


def check(project_dir: str) -> tuple:
    genome = load_genome(project_dir)
    issues = validate_genome(genome)
    _write_status(genome, issues)
    _write_issues(genome.plan_dir, issues)
    return genome, issues


def converge(project_dir: str, agent_manager):
    """Main convergence loop."""

    _bootstrap_hr_agent(project_dir)

    genome, issues = check(project_dir)
    config = _load_config(genome)
    max_parallel = config.get("max_parallel", 1)
    snapshot_mgr = SnapshotManager(project_dir, config.get("snapshot_interval", 10))

    snapshot_mgr.force_checkpoint("genome5: bootstrap")

    print(f"  Config: max_parallel={max_parallel}, timeout={config.get('agent_timeout', 600)}")

    stuck_count = 0
    last_error_count = float("inf")
    revert_counts: dict[str, int] = {}
    cycle_tracker: dict[tuple, int] = {}  # (node, check, context) → count
    last_feedback = ""
    pending: dict[str, dict] = {}
    start_time = time.time()
    total_cycles = 0

    while True:
        # Budget check
        total_cycles += 1
        elapsed_hours = (time.time() - start_time) / 3600
        if total_cycles > config.get("max_cycles", 5000):
            print(f"\nPAUSED: cycle budget ({config['max_cycles']}) exceeded.")
            agent_manager.kill()
            return
        if elapsed_hours > config.get("max_hours", 24):
            print(f"\nPAUSED: time budget ({config['max_hours']}h) exceeded.")
            agent_manager.kill()
            return

        # Phase check: only when no agents pending
        if not pending:
            genome, issues = check(project_dir)

            # Run runnable nodes (tests)
            ran_any = False
            for node in genome.all_nodes():
                if not getattr(node, "runnable", False):
                    continue
                print(f"  Running: {node.name}")
                ran_any = True
                try:
                    result = node.run(project_dir)
                    print(f"  {node.name}: {'PASS' if result.get('success') else 'FAIL'}")
                except Exception as e:
                    print(f"  {node.name}: ERROR ({e})")

            if ran_any:
                issues = validate_genome(genome)

            errors = [i for i in issues if i.severity == "error"]
            warnings = [i for i in issues if i.severity == "warning"]

            print(f"\n-- Cycle {total_cycles} | {len(errors)} errors, "
                  f"{len(warnings)} warnings, {len(issues)} total --")

            # Converged?
            if config.get("convergence") == "strict":
                if not errors and not warnings:
                    print("\nOK: Converged (strict).")
                    snapshot_mgr.force_checkpoint("genome5: converged")
                    agent_manager.kill()
                    return
            else:
                if not errors:
                    print("\nOK: Converged.")
                    snapshot_mgr.force_checkpoint("genome5: converged")
                    agent_manager.kill()
                    return

        # Dispatch
        if not pending:
            # Filter cycling checks
            cycling = {k for k, v in cycle_tracker.items() if v >= 3}
            eligible = [i for i in issues
                        if i.severity in ("error", "warning")
                        and revert_counts.get(i.message, 0) < config.get("max_reverts", 3)
                        and (i.node_name, i.check, i.context) not in cycling]

            if not eligible:
                print(f"\nFAIL: All tasks skipped or cycling. {len(issues)} remain.")
                agent_manager.kill()
                return

            snapshot_mgr.snapshot()

            dispatched: set[str] = set()
            for task in eligible:
                owner = _find_owner(task, genome)
                if not owner or owner.name in dispatched:
                    continue

                context_nodes = owner.before_work({"node_name": task.node_name}, genome) if hasattr(owner, "before_work") else []
                context_files = [n._source_file for n in context_nodes if n and n._source_file]
                reg_history = load_regression_history(genome.plan_dir)

                print(f"  -> {owner.name}: {task.message[:80]}")

                # Handle debate tasks — collect all debate-eligible tasks and run in parallel
                if task.debate:
                    from src.debate import run_debate
                    import concurrent.futures

                    # Collect ALL debate tasks for this dispatch (up to max_parallel)
                    debate_batch = [(task, owner, context_files)]
                    for other_task in eligible:
                        if not other_task.debate or other_task is task:
                            continue
                        other_owner = _find_owner(other_task, genome)
                        if not other_owner or other_owner.name in dispatched:
                            continue
                        other_context = []
                        if hasattr(other_owner, "before_work"):
                            other_context = [n._source_file for n in
                                           other_owner.before_work({"node_name": other_task.node_name}, genome)
                                           if n and n._source_file]
                        debate_batch.append((other_task, other_owner, other_context))
                        dispatched.add(other_owner.name)
                        if len(debate_batch) >= max_parallel:
                            break

                    def _run_one_debate(args):
                        dtask, downer, dctx = args
                        print(f"  DEBATE: {dtask.node_name or dtask.message[:40]}...")
                        result = run_debate(
                            project_dir=project_dir,
                            topic=dtask.message,
                            context_files=dctx,
                            solver_instructions=dtask.suggestion or dtask.message,
                            model=getattr(downer, "model", "claude-opus-4-6"),
                            timeout=config.get("agent_timeout", 600),
                        )
                        return dtask, downer, result

                    print(f"  Running {len(debate_batch)} debates in parallel...")

                    with concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel) as pool:
                        futures = [pool.submit(_run_one_debate, args) for args in debate_batch]
                        for future in concurrent.futures.as_completed(futures):
                            dtask, downer, debate_result = future.result()
                            print(f"  Debate done for {dtask.node_name or '?'}: {len(debate_result)} chars")

                            # Check if debate created files
                            debate_genome = load_genome(project_dir)
                            if len(debate_genome.nodes) == len(genome.nodes):
                                print(f"  Debate text → passing to agent...")
                                snapshot_mgr.snapshot()
                                followup = Task(
                                    f"The debate team produced this analysis. Create the "
                                    f"nodes described:\n\n{debate_result[:3000]}",
                                    dtask.node_name, phase=dtask.phase, priority=dtask.priority,
                                    suggestion=dtask.suggestion,
                                )
                                agent_manager.assign_task({
                                    "issue": followup,
                                    "context_files": dctx,
                                    "regression_history": reg_history,
                                    "feedback": "",
                                    "agent_node": downer,
                                })

                    snapshot_mgr.checkpoint(f"genome5: {len(debate_batch)} parallel debates")
                    continue

                # Handle fresh_session tasks (new agent, not persistent)
                if task.fresh_session:
                    print(f"  FRESH SESSION for exhaustion/review")
                    result = agent_manager.assign_task_fresh({
                        "issue": task,
                        "context_files": context_files,
                        "regression_history": reg_history,
                        "feedback": last_feedback,
                        "agent_node": owner,
                    })
                    # Fresh session ran synchronously
                    if result.get("success"):
                        print(f"  Fresh session done.")
                    else:
                        print(f"  Fresh session failed: {result.get('error', '?')}")
                    snapshot_mgr.checkpoint(f"genome5: fresh-{owner.name}")
                    continue

                # Normal persistent session task
                handle = agent_manager.assign_task_async({
                    "issue": task,
                    "context_files": context_files,
                    "regression_history": reg_history,
                    "feedback": last_feedback,
                    "agent_node": owner,
                })

                if handle and not handle.get("error"):
                    pending[owner.name] = {
                        "handle": handle, "task": task,
                        "before_issues": list(issues),
                        "owner": owner, "before_genome": genome,
                    }
                    dispatched.add(owner.name)

                if len(dispatched) >= max_parallel:
                    break

            if not pending:
                stuck_count += 1
                if stuck_count >= config.get("stuck_threshold", 5):
                    print(f"\nFAIL: Stuck.")
                    agent_manager.kill()
                    return
                continue

        # Collect
        finished_name, dispatch_id = agent_manager.wait_for_any(
            timeout=config.get("agent_timeout", 600))

        if finished_name is None:
            for name in list(pending.keys()):
                agent_manager.kill(name)
            pending.clear()
            stuck_count += 1
            if stuck_count >= config.get("stuck_threshold", 5):
                print(f"\nFAIL: Agents timing out.")
                agent_manager.kill()
                return
            continue

        if finished_name not in pending:
            continue

        expected_id = pending[finished_name].get("handle", {}).get("dispatch_id", "")
        if dispatch_id and expected_id and dispatch_id != expected_id:
            continue

        info = pending.pop(finished_name)
        result = agent_manager.collect_result(info["handle"], timeout=10)

        print(f"  {finished_name} done.")

        if not result.get("success"):
            print(f"  Failed: {result.get('error', '?')}")
            stuck_count += 1
            if stuck_count >= config.get("stuck_threshold", 5) and not pending:
                print(f"\nFAIL: Stuck.")
                agent_manager.kill()
                return
            continue

        # Apply
        top = info["task"]
        before_issues = info["before_issues"]

        after_genome, after_issues = check(project_dir)
        after_errors = [i for i in after_issues if i.severity == "error"]

        # Regression
        regression = detect_regression(top, before_issues, after_issues)
        if regression:
            print(f"  REGRESSION: {regression}")
            log_regression(after_genome.plan_dir, top, regression)
            revert_counts[top.message] = revert_counts.get(top.message, 0) + 1
            if not pending:
                if snapshot_mgr.restore():
                    print(f"  Reverted.")
                else:
                    print(f"  WARNING: Could not revert.")
            continue

        # Cycle detection
        after_msgs = {i.message for i in after_issues}
        assigned_fixed = top.message not in after_msgs
        if assigned_fixed and top.check:
            check_still = any(t.check == top.check and t.node_name == top.node_name for t in after_issues)
            if check_still:
                key = (top.node_name, top.check, top.context)
                cycle_tracker[key] = cycle_tracker.get(key, 0) + 1
                if cycle_tracker[key] >= 3:
                    print(f"  CYCLE: ({top.node_name}, {top.check}) skipped.")
            else:
                cycle_tracker.pop((top.node_name, top.check, top.context), None)

        snapshot_mgr.checkpoint(f"genome5: {finished_name}")

        # Feedback
        before_msgs = {i.message for i in before_issues}
        resolved = [i for i in before_issues if i.message not in after_msgs]
        new_issues = [i for i in after_issues if i.message not in before_msgs]
        parts = []
        if resolved:
            parts.append(f"RESOLVED: {'; '.join(i.message[:60] for i in resolved[:3])}")
        if new_issues:
            parts.append(f"NEW: {'; '.join(i.message[:60] for i in new_issues[:3])}")
        last_feedback = "\n".join(parts) if parts else ""

        # Progress
        if assigned_fixed:
            print(f"  FIXED: {top.message[:80]}")
            stuck_count = 0
        else:
            print(f"  NOT FIXED: {top.message[:80]}")
            stuck_count += 1

        if len(after_errors) < last_error_count:
            last_error_count = len(after_errors)
            stuck_count = 0

        if stuck_count >= config.get("stuck_threshold", 5) and not pending:
            print(f"\nFAIL: No progress for {config['stuck_threshold']} passes.")
            agent_manager.kill()
            return


# -- Bootstrap --

def _bootstrap_hr_agent(project_dir: str):
    plan_dir = os.path.join(project_dir, "plan")
    os.makedirs(plan_dir, exist_ok=True)

    for root, dirs, files in os.walk(plan_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.endswith(".py") and not f.startswith("_"):
                try:
                    with open(os.path.join(root, f), encoding="utf-8") as fh:
                        content = fh.read()
                        if "type = \"agent\"" in content or "AgentNode" in content:
                            return
                except Exception:
                    pass

    print("  Bootstrapping HR Agent...")

    hr_code = '''"""HR Agent — creates the agent team."""
from genome5 import Node, Task


class HRAgent(Node):
    name = "HR Agent"
    type = "agent"
    level = 0
    description = (
        "Creates specialist agents. Assigns node ownership. "
        "Reads project context and builds the right team."
    )
    model = "claude-opus-4-6"
    capabilities = ["team-management"]
    edges = {}

    knowledge = [
        "Bootstrapped by genome5. Read plan/context.yaml and the agent guide.",
        "Create domain-specific agents. Assign ownership via owned_by edges.",
    ]

    def validate(self, genome):
        tasks = []
        agents = genome.nodes_by_type("agent")
        if len(agents) == 1 and agents[0].name == self.name:
            tasks.append(Task(
                f"{self.name}: create specialist agents for this project",
                self.name, phase="structural", priority=3,
                check="hr-create-team",
            ))
        return tasks
'''

    with open(os.path.join(plan_dir, "hr_agent.py"), "w", encoding="utf-8") as f:
        f.write(hr_code)

    # Copy seeds
    _seed_project(plan_dir)


def _seed_project(plan_dir: str):
    ctx_path = os.path.join(plan_dir, "context.yaml")
    seed_name = "blank"
    if os.path.exists(ctx_path):
        try:
            with open(ctx_path, encoding="utf-8") as f:
                ctx = yaml.safe_load(f) or {}
            seed_name = ctx.get("seed", "blank")
        except Exception:
            pass

    engine_dir = os.path.dirname(os.path.abspath(__file__))
    seed_dir = os.path.join(engine_dir, "..", "seeds", seed_name)
    if not os.path.exists(seed_dir):
        seed_dir = os.path.join(engine_dir, "..", "seeds", "blank")
    if not os.path.exists(seed_dir):
        return

    import shutil
    for fname in os.listdir(seed_dir):
        if fname.endswith(".py") and not fname.startswith("_") and fname != "base_classes.py":
            src = os.path.join(seed_dir, fname)
            dst = os.path.join(plan_dir, fname)
            if not os.path.exists(dst):
                shutil.copy2(src, dst)

    print(f"  Seeded: {seed_name}")


# -- Helpers --

def _find_owner(task, genome):
    if task.node_name:
        node = genome.get(task.node_name)
        if node:
            owner = node.get_owner(genome)
            if owner:
                return owner
    agents = genome.nodes_by_type("agent")
    return agents[0] if agents else None


def _load_config(genome) -> dict:
    defaults = {
        "convergence": "strict",
        "stuck_threshold": 5,
        "max_reverts": 3,
        "agent_timeout": 600,
        "max_parallel": 1,
        "snapshot_interval": 10,
        "max_cycles": 5000,
        "max_hours": 24,
    }
    for node in genome.nodes_by_type("config"):
        for key in defaults:
            if hasattr(node, key):
                defaults[key] = getattr(node, key)
    return defaults


def _write_status(genome, tasks):
    errors = [t for t in tasks if t.severity == "error"]
    warnings = [t for t in tasks if t.severity == "warning"]
    status = {
        "generator": "genome5",
        "counts": {"nodes": len(genome.nodes)},
        "issues": {"total": len(tasks), "errors": len(errors), "warnings": len(warnings)},
        "converged": not errors and not warnings,
    }
    with open(os.path.join(genome.plan_dir, "status.yaml"), "w", encoding="utf-8") as f:
        yaml.dump(status, f, default_flow_style=False)


def _write_issues(plan_dir, tasks):
    data = [{"priority": f"P{t.priority}", "phase": t.phase, "severity": t.severity,
             "node": t.node_name or None, "message": t.message} for t in tasks[:100]]
    with open(os.path.join(plan_dir, "issues.yaml"), "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False)
