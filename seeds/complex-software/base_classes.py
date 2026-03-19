"""Seed base classes — optional types agents can import.

from genome5.seeds import ServiceNode, PersonaNode, JourneyNode, etc.
NOT required. Agents can use plain Node. Seeds just save time.
"""

import os
import re
import subprocess
from genome5 import Node, Task


class ServiceNode(Node):
    """A system component (API, worker, service)."""
    type = "service"

    def validate(self, genome) -> list[Task]:
        tasks = super().validate(genome)

        # Check expected children
        if self.expected_children:
            existing = {n.name for n in self.children(genome)}
            for name in self.expected_children:
                if name not in existing:
                    tasks.append(Task(
                        f"Create: '{name}' (parent: '{self.name}', level: {self.level + 1})",
                        self.name, phase="planning", priority=3,
                        check=f"missing-child:{name[:30]}",
                    ))

        # Dev phase: check files exist
        for f in (self.files or []):
            if not os.path.exists(os.path.join(genome.project_dir, f)):
                tasks.append(Task(
                    f"'{self.name}': file '{f}' does not exist",
                    self.name, phase="dev", priority=7,
                    check="files-must-exist",
                ))

        if not self.get_owner(genome):
            tasks.append(Task(
                f"'{self.name}': no agent owns this node",
                self.name, phase="structural", priority=2,
                check="must-have-owner",
            ))

        return tasks


class PersonaNode(Node):
    """A human user or threat actor."""
    type = "persona"

    def validate(self, genome) -> list[Task]:
        tasks = super().validate(genome)

        goals = self.properties.get("goals") or getattr(self, "goals", None)
        if not goals:
            tasks.append(Task(
                f"'{self.name}': persona should have goals",
                self.name, phase="planning", priority=5,
                check="persona-no-goals",
            ))

        if not self.get_owner(genome):
            tasks.append(Task(
                f"'{self.name}': no agent owns this node",
                self.name, phase="structural", priority=2,
                check="must-have-owner",
            ))

        return tasks


class JourneyNode(Node):
    """Step-by-step flow. Steps reference services in [brackets]."""
    type = "journey"
    steps: list = []

    def __init__(self):
        super().__init__()
        self.steps = list(getattr(type(self), 'steps', []))

    def validate(self, genome) -> list[Task]:
        tasks = super().validate(genome)

        if not self.steps:
            tasks.append(Task(
                f"'{self.name}': journey has no steps",
                self.name, phase="planning", priority=5,
                check="journey-no-steps",
            ))

        return tasks

    @staticmethod
    def extract_node_name(step):
        match = re.search(r'\[(.+?)\]', step)
        return match.group(1) if match else None


class AgentNode(Node):
    """An AI agent."""
    type = "agent"
    model: str = "claude-sonnet-4-6"
    capabilities: list = []

    def __init__(self):
        super().__init__()
        self.capabilities = list(getattr(type(self), 'capabilities', []))

    def validate(self, genome) -> list[Task]:
        tasks = super().validate(genome)
        owned = self.get_owned_nodes(genome)
        if not owned:
            tasks.append(Task(
                f"'{self.name}': agent owns 0 nodes",
                self.name, phase="structural", priority=3, severity="warning",
                check="agent-no-nodes",
            ))
        return tasks

    def before_work(self, task, genome) -> list:
        context = [self]
        if task.get("node_name"):
            target = genome.get(task["node_name"])
            if target:
                context.append(target)
                context.extend(target.get_connections(genome))
        for node in genome.all_nodes():
            if node.knowledge and node.type in ("guide", "workflow"):
                context.append(node)
        return context


class UseCaseNode(Node):
    """Something a persona can do."""
    type = "use_case"

    def validate(self, genome) -> list[Task]:
        tasks = super().validate(genome)

        if self.expected_children:
            existing = {n.name for n in self.children(genome)}
            for name in self.expected_children:
                if name not in existing:
                    tasks.append(Task(
                        f"Create journey: '{name}' (parent: '{self.name}', level: {self.level + 1})",
                        self.name, phase="planning", priority=4,
                        check=f"missing-child:{name[:30]}",
                    ))

        if not self.get_owner(genome):
            tasks.append(Task(
                f"'{self.name}': no agent owns this node",
                self.name, phase="structural", priority=2,
                check="must-have-owner",
            ))

        return tasks


class TestNode(Node):
    """A test the engine runs. Results can't be faked."""
    type = "test"
    test_target: str = ""
    test_command: str = ""
    test_file: str = ""
    last_result: dict = {}

    @property
    def runnable(self):
        return bool(self.test_command or self.test_file)

    def validate(self, genome) -> list[Task]:
        tasks = super().validate(genome)

        if not self.test_command and not self.test_file:
            tasks.append(Task(
                f"'{self.name}': needs test_command or test_file",
                self.name, phase="test", priority=8,
                check="test-no-command",
            ))

        if self.last_result.get("success") is False:
            target = self.test_target or self.name
            error = self.last_result.get("error", "failed")
            tasks.append(Task(
                f"Test '{self.name}' FAILED: {error[:200]}",
                target, phase="test", priority=8,
                check="test-failed",
            ))

        return tasks

    def run(self, project_dir: str) -> dict:
        command = self.test_command
        if not command and self.test_file:
            ext_runners = {
                "spec.ts": "npx playwright test", "spec.js": "npx playwright test",
                "test.ts": "npx jest", "test.js": "npx jest",
                "py": "python -m pytest",
            }
            for suffix, runner in ext_runners.items():
                if self.test_file.endswith(suffix):
                    command = f"{runner} {self.test_file}"
                    break
            if not command:
                command = f"node {self.test_file}"

        if not command:
            return {"success": False, "error": "No test command"}

        try:
            result = subprocess.run(
                command, shell=True, cwd=project_dir,
                capture_output=True, text=True, timeout=120)
            self.last_result = {
                "success": result.returncode == 0,
                "output": result.stdout[-1000:] if result.stdout else "",
                "error": result.stderr[-500:] if result.stderr else "",
            }
            return self.last_result
        except subprocess.TimeoutExpired:
            self.last_result = {"success": False, "error": "Timed out (120s)"}
            return self.last_result
        except Exception as e:
            self.last_result = {"success": False, "error": str(e)[:500]}
            return self.last_result


class ConfigNode(Node):
    """Engine configuration."""
    type = "config"
    convergence: str = "strict"
    max_parallel: int = 1
    stuck_threshold: int = 5
    max_reverts: int = 3
    agent_timeout: int = 600
    snapshot_interval: int = 10
    max_cycles: int = 5000
    max_hours: int = 24

    def validate(self, genome):
        return []
