"""Regression detection + snapshot management.

File-copy snapshots for fast rollback (not git per cycle).
Git commits every N cycles for durable checkpoints.
"""

import os
import shutil
import subprocess
import yaml

from src.node import Task


def detect_regression(assigned_task: Task, before: list[Task], after: list[Task]) -> str | None:
    before_msgs = {t.message for t in before}
    after_msgs = {t.message for t in after}

    assigned_fixed = assigned_task.message not in after_msgs
    if assigned_fixed:
        return None

    new_critical = [
        t for t in after
        if t.severity == "error" and t.priority <= 2
        and t.message not in before_msgs
    ]

    if new_critical:
        msgs = "; ".join(t.message[:80] for t in new_critical[:3])
        return f"Did not fix task AND created new critical errors: {msgs}"

    return None


class SnapshotManager:
    """Two-tier snapshots: file-copy for per-task, git for durable checkpoints."""

    def __init__(self, project_dir: str, git_interval: int = 10):
        self.project_dir = project_dir
        self.plan_dir = os.path.join(project_dir, "plan")
        self.snapshot_dir = os.path.join(project_dir, "_snapshots")
        self.git_interval = git_interval
        self.cycle_count = 0

    def snapshot(self):
        """Fast file-copy snapshot of plan/."""
        if os.path.exists(self.snapshot_dir):
            shutil.rmtree(self.snapshot_dir)
        shutil.copytree(self.plan_dir, self.snapshot_dir,
                       ignore=shutil.ignore_patterns("__pycache__"))

    def restore(self):
        """Restore plan/ from file-copy snapshot."""
        if not os.path.exists(self.snapshot_dir):
            return False
        if os.path.exists(self.plan_dir):
            shutil.rmtree(self.plan_dir)
        shutil.copytree(self.snapshot_dir, self.plan_dir)
        return True

    def checkpoint(self, message: str = "genome5: checkpoint"):
        """Git commit for durable checkpoint. Called every N cycles."""
        self.cycle_count += 1
        if self.cycle_count % self.git_interval == 0:
            self._git_commit(message)

    def force_checkpoint(self, message: str):
        """Immediate git commit (bootstrap, convergence, etc.)."""
        self._git_commit(message)

    def _git_commit(self, message: str):
        try:
            subprocess.run(["git", "add", "-A"], cwd=self.project_dir,
                          capture_output=True, timeout=30)
            subprocess.run(["git", "commit", "-m", message, "--allow-empty"],
                          cwd=self.project_dir, capture_output=True, timeout=30)
        except Exception:
            pass


def log_regression(plan_dir: str, task: Task, description: str):
    log_path = os.path.join(plan_dir, "regression_log.yaml")
    entry = {"task": task.message[:200], "node": task.node_name, "regression": description[:300]}

    existing = []
    if os.path.exists(log_path):
        try:
            with open(log_path, encoding="utf-8") as f:
                existing = yaml.safe_load(f) or []
        except Exception:
            existing = []

    existing.append(entry)
    with open(log_path, "w", encoding="utf-8") as f:
        yaml.dump(existing, f, default_flow_style=False)


def load_regression_history(plan_dir: str) -> str:
    log_path = os.path.join(plan_dir, "regression_log.yaml")
    if not os.path.exists(log_path):
        return ""
    try:
        with open(log_path, encoding="utf-8") as f:
            entries = yaml.safe_load(f) or []
    except Exception:
        return ""
    if not entries:
        return ""
    recent = entries[-5:]
    lines = ["RECENT REGRESSIONS (avoid these):"]
    for e in recent:
        lines.append(f"  - {e.get('task', '')[:100]}")
    return "\n".join(lines)
