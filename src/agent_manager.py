"""Agent Manager — persistent Claude Code sessions.

Each agent is a long-lived process. NOT killed between tasks.
Communication via NDJSON stdin/stdout. Dispatch IDs prevent stale signals.
"""

import json
import subprocess
import os
import threading
import queue
import uuid


class AgentManager:
    def __init__(self, project_dir: str, task_timeout: int = 600):
        self.project_dir = project_dir
        self.task_timeout = task_timeout
        self.agents: dict[str, dict] = {}
        self.completion_queue: queue.Queue = queue.Queue()

    def assign_task(self, task: dict) -> dict:
        """Sync: dispatch + collect."""
        handle = self.assign_task_async(task)
        if not handle or handle.get("error"):
            return {"success": False, "error": handle.get("error", "no handle") if handle else "no handle"}
        return self.collect_result(handle)

    def assign_task_async(self, task: dict) -> dict | None:
        """Dispatch task, return immediately."""
        agent_node = task.get("agent_node")
        if not agent_node:
            return {"error": "No agent node provided"}

        name = agent_node.name
        process = self._get_or_spawn(agent_node)
        if not process:
            return {"error": f"Failed to spawn '{name}'"}

        prompt = self._build_prompt(task)
        return self._send_async(name, prompt)

    def collect_result(self, handle: dict, timeout: float = None) -> dict:
        if handle.get("error"):
            return {"success": False, "error": handle["error"]}

        name = handle["agent_name"]
        result_queue = handle["result_queue"]
        info = self.agents.get(name)
        t = timeout or self.task_timeout

        try:
            item = result_queue.get(timeout=t)
            if item["type"] == "result":
                return {"success": True, "text": self._extract_text(item["msg"])}
            else:
                if info:
                    info["alive"] = False
                return {"success": False, "error": item["error"]}
        except queue.Empty:
            print(f"  TIMEOUT: '{name}' after {t}s")
            if info:
                try:
                    info["process"].kill()
                except Exception:
                    pass
                info["alive"] = False
            return {"success": False, "error": f"'{name}' timed out after {t}s"}

    def wait_for_any(self, timeout: float = None) -> tuple[str, str] | tuple[None, None]:
        """Block until any agent finishes. Returns (name, dispatch_id)."""
        try:
            item = self.completion_queue.get(timeout=timeout or self.task_timeout)
            if isinstance(item, tuple):
                return item
            return item, ""
        except queue.Empty:
            return None, None

    def assign_task_fresh(self, task: dict) -> dict:
        """Run task in a FRESH agent session — new process, no prior context.

        Used for exhaustion State 3 (re-read spec) and State 4 (reviewer).
        The fresh session ensures different LLM sampling paths.
        Process is killed after the task completes.
        """
        agent_node = task.get("agent_node")
        if not agent_node:
            return {"success": False, "error": "No agent node provided"}

        name = agent_node.name
        model = getattr(agent_node, "model", "claude-opus-4-6")
        desc = getattr(agent_node, "description", "")
        prompt = self._build_prompt(task)

        # One-shot: spawn, send, receive, kill
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)

        try:
            result = subprocess.run(
                ["claude", "--output-format", "text", "--model", model,
                 "--dangerously-skip-permissions"],
                input=prompt, capture_output=True, text=True,
                timeout=self.task_timeout, cwd=self.project_dir,
                env=env, encoding="utf-8", errors="replace",
            )
            if result.returncode == 0 and result.stdout.strip():
                return {"success": True, "text": result.stdout.strip()}
            return {"success": False, "error": result.stderr[:200] if result.stderr else "no output"}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Fresh session timed out after {self.task_timeout}s"}
        except Exception as e:
            return {"success": False, "error": str(e)[:200]}

    def kill(self, name: str = None):
        targets = [name] if name else list(self.agents.keys())
        for n in targets:
            info = self.agents.get(n)
            if info and info.get("process"):
                try:
                    proc = info["process"]
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                                       capture_output=True, timeout=10)
                    else:
                        proc.kill()
                except Exception:
                    pass
            if n in self.agents:
                del self.agents[n]

    def _get_or_spawn(self, agent_node) -> dict | None:
        name = agent_node.name
        info = self.agents.get(name)
        if info and info.get("alive"):
            return info

        model = getattr(agent_node, "model", "claude-opus-4-6")
        desc = getattr(agent_node, "description", "")

        env = {**os.environ}
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)

        system_prompt = (
            f'You are "{name}". {desc} '
            f'Read ALL files listed in each task. They contain genome5 instructions and context.'
        )

        args = [
            "claude",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--model", model,
            "--dangerously-skip-permissions",
            "--verbose",
            "--system-prompt", system_prompt,
        ]

        try:
            proc = subprocess.Popen(
                args, cwd=self.project_dir, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            info = {"process": proc, "name": name, "alive": True}
            self.agents[name] = info
            return info
        except Exception as e:
            print(f"  Failed to spawn {name}: {e}")
            return None

    def _send_async(self, name: str, message: str) -> dict:
        info = self.agents.get(name)
        if not info or not info.get("alive"):
            return {"error": f"'{name}' not alive"}

        proc = info["process"]
        ndjson = json.dumps({
            "type": "user",
            "message": {"role": "user", "content": message},
        })

        try:
            proc.stdin.write((ndjson + "\n").encode())
            proc.stdin.flush()
        except (BrokenPipeError, OSError):
            info["alive"] = False
            return {"error": f"'{name}' stdin broken"}

        result_q = queue.Queue()
        completion_q = self.completion_queue
        dispatch_id = str(uuid.uuid4())[:8]

        def _reader():
            try:
                while True:
                    line = proc.stdout.readline()
                    if not line:
                        result_q.put({"type": "error", "error": "stdout closed"})
                        completion_q.put((name, dispatch_id))
                        return
                    line = line.decode().strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                        if msg.get("type") == "result":
                            result_q.put({"type": "result", "msg": msg})
                            completion_q.put((name, dispatch_id))
                            return
                    except json.JSONDecodeError:
                        continue
            except Exception as e:
                result_q.put({"type": "error", "error": str(e)})
                completion_q.put((name, dispatch_id))

        threading.Thread(target=_reader, daemon=True).start()
        return {"agent_name": name, "result_queue": result_q, "dispatch_id": dispatch_id}

    def _extract_text(self, msg: dict) -> str:
        if isinstance(msg.get("result"), str):
            return msg["result"]
        if isinstance(msg.get("text"), str):
            return msg["text"]
        if isinstance(msg.get("content"), list):
            return "\n".join(c.get("text", "") for c in msg["content"] if c.get("text"))
        return json.dumps(msg)

    def _build_prompt(self, task: dict) -> str:
        issue = task["issue"]
        lines = [
            "GENOME5 — You are an AI agent. Everything is a Python node in plan/.",
            "IMPORT: from genome5 import Node, Task",
            "  Or from genome5.seeds import ServiceNode (optional seed types)",
            "Every node has: name, type, level, description, edges, validate().",
            "You can create, modify, or delete ANY node you own.",
            "After fixing, update knowledge. Reflect: should you improve your validate()?",
            "",
            "TASK: " + (f'Fix issue on "{issue.node_name}"' if issue.node_name else "Fix project issue"),
            f"ISSUE: {issue.message}",
            f"PRIORITY: P{issue.priority} ({issue.severity})",
        ]

        if issue.suggestion:
            lines.append(f"SUGGESTION: {issue.suggestion}")

        context_files = list(task.get("context_files", []))
        ctx_path = os.path.join(self.project_dir, "plan", "context.yaml")
        if os.path.exists(ctx_path):
            try:
                import yaml
                with open(ctx_path, encoding="utf-8") as cf:
                    ctx = yaml.safe_load(cf) or {}
                ref = ctx.get("planning", {}).get("reference", "")
                if ref:
                    ref_path = os.path.join(self.project_dir, ref)
                    if os.path.exists(ref_path) and ref_path not in context_files:
                        context_files.insert(0, ref_path)
            except Exception:
                pass

        lines.append("\nFILES TO READ:")
        for f in context_files:
            rel = os.path.relpath(f, self.project_dir)
            lines.append(f"  {rel}")

        if task.get("feedback"):
            lines.append(f"\nFEEDBACK:\n{task['feedback']}")
        if task.get("regression_history"):
            lines.append(f"\n{task['regression_history']}")

        agent_node = task.get("agent_node")
        if agent_node and "team-management" in getattr(agent_node, "capabilities", []):
            lines.append("\nHR: Create specialists. Assign ownership. Name descriptively.")

        return "\n".join(lines)


def create_agent_manager(project_dir: str) -> AgentManager:
    return AgentManager(project_dir)
