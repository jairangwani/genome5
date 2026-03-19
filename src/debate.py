"""Debate Team — 1 Solver + 2 Breakers using PERSISTENT sessions.

ALL THREE must say CONVERGED (last line) for the debate to end.
Max 50 rounds. Every round logged to plan/debate_log.md.
Persistent sessions: agents write files directly, accumulate context.
Returns (result_text, converged_bool).
"""

import os
import json
import subprocess
import threading
import queue
import uuid
import datetime

MAX_ROUNDS = 50
DEFAULT_MODEL = "claude-opus-4-6"


def run_debate(project_dir: str, topic: str, context_files: list[str],
               solver_instructions: str, breaker1_focus: str = "logical flaws",
               breaker2_focus: str = "practical gaps", model: str = DEFAULT_MODEL,
               timeout: int = 300) -> tuple[str, bool]:
    """Run a 1+2 debate with PERSISTENT sessions. Returns (result, converged)."""

    log_path = os.path.join(project_dir, "plan", "debate_log.md")
    debate_id = datetime.datetime.now().strftime("%H:%M:%S")
    topic_short = topic[:60].replace('\n', ' ')

    def _log(msg: str):
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")

    _log(f"\n{'='*60}")
    _log(f"## DEBATE [{debate_id}]: {topic_short}")
    _log(f"Model: {model} | Max rounds: {MAX_ROUNDS} | Persistent sessions")
    _log(f"{'='*60}\n")

    # Spawn 3 persistent sessions
    agents = {}
    for role_name, role_desc in [
        ("SOLVER", f"You PROPOSE answers and integrate feedback. {solver_instructions}"),
        ("BREAKER 1", f"You find LOGICAL FLAWS. Focus on: {breaker1_focus}. Hint at solutions."),
        ("BREAKER 2", f"You find PRACTICAL GAPS. Focus on: {breaker2_focus}. Hint at what's missing."),
    ]:
        agents[role_name] = _spawn_persistent(project_dir, role_name, role_desc, model)

    debate_history = []
    role_converged = {"SOLVER": False, "BREAKER 1": False, "BREAKER 2": False}
    final_converged = False

    for round_num in range(1, MAX_ROUNDS + 1):
        if round_num % 3 == 1:
            role = "SOLVER"
            if round_num == 1:
                # First round: give full context
                context_text = ""
                for cf in context_files:
                    if os.path.exists(cf):
                        try:
                            with open(cf, "r", encoding="utf-8") as f:
                                context_text += f"\n=== {os.path.basename(cf)} ===\n{f.read()[:8000]}\n"
                        except Exception:
                            pass
                prompt = (
                    f"TOPIC: {topic}\n\n"
                    f"CONTEXT:\n{context_text}\n\n"
                    f"You are the SOLVER. Propose your answer. Create node files directly in plan/. "
                    f"When you're done and genuinely can't improve further, end with CONVERGED on its own line."
                )
            else:
                prompt = (
                    f"Integrate the breakers' feedback. Address every point. "
                    f"Update or create node files as needed. "
                    f"When genuinely done, end with CONVERGED on its own line."
                )
        elif round_num % 3 == 2:
            role = "BREAKER 1"
            prompt = (
                f"Review the solver's work. Read the node files in plan/. "
                f"Find logical flaws. Hint at solutions. Don't repeat previous points. "
                f"When you genuinely can't find more, end with CONVERGED on its own line."
            )
        else:
            role = "BREAKER 2"
            prompt = (
                f"Review solver's work AND breaker 1's points. Read node files. "
                f"Find practical gaps both missed. Hint at what's missing. "
                f"When genuinely done, end with CONVERGED on its own line."
            )

        print(f"  Debate [{debate_id}] round {round_num}/{MAX_ROUNDS}: {role}...")
        response = _send_to_persistent(agents[role], prompt, timeout)

        last_line = response.rstrip().split('\n')[-1].strip().rstrip('.,!;:')
        has_converged = last_line == "CONVERGED"
        if has_converged:
            role_converged[role] = True

        conv_marker = " [CONVERGED]" if has_converged else ""
        _log(f"### Round {round_num}: {role}{conv_marker}")
        _log(f"{response[:800]}{'...' if len(response) > 800 else ''}\n")

        debate_history.append({"role": role, "round": round_num, "content": response})

        # Check ALL THREE converged
        if all(role_converged.values()) and round_num >= 4:
            final_converged = True
            print(f"  Debate [{debate_id}] ALL 3 CONVERGED after {round_num} rounds!")
            _log(f"\n**RESULT: CONVERGED after {round_num}/{MAX_ROUNDS} rounds.**")
            _log(f"  SOLVER: converged={role_converged['SOLVER']}")
            _log(f"  BREAKER 1: converged={role_converged['BREAKER 1']}")
            _log(f"  BREAKER 2: converged={role_converged['BREAKER 2']}\n")
            break

        if has_converged and not all(role_converged.values()):
            _log(f"  ({role} converged but waiting for others...)\n")

    if not final_converged:
        print(f"  Debate [{debate_id}] hit MAX_ROUNDS ({MAX_ROUNDS}).")
        _log(f"\n**RESULT: MAX ROUNDS ({MAX_ROUNDS}) reached. Did NOT converge.**")
        _log(f"  SOLVER: converged={role_converged['SOLVER']}")
        _log(f"  BREAKER 1: converged={role_converged['BREAKER 1']}")
        _log(f"  BREAKER 2: converged={role_converged['BREAKER 2']}\n")

    _log(f"Total rounds: {len(debate_history)} | Final converged: {final_converged}\n")

    # Kill all debate agents
    for role_name, info in agents.items():
        try:
            proc = info["process"]
            if os.name == "nt":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                               capture_output=True, timeout=10)
            else:
                proc.kill()
        except Exception:
            pass

    solver_responses = [e["content"] for e in debate_history if e["role"] == "SOLVER"]
    result = solver_responses[-1] if solver_responses else "No solver output."
    return result, final_converged


def _spawn_persistent(project_dir: str, role: str, description: str, model: str) -> dict:
    """Spawn a persistent Claude Code session for a debate agent."""
    env = {**os.environ}
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)

    system_prompt = (
        f'You are "{role}" in a debate team. {description} '
        f'You can read and write files in plan/. Create .py node files directly.'
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

    proc = subprocess.Popen(
        args, cwd=project_dir, env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return {"process": proc, "name": role}


def _send_to_persistent(agent_info: dict, message: str, timeout: int) -> str:
    """Send message to persistent session and wait for response."""
    proc = agent_info["process"]

    ndjson = json.dumps({
        "type": "user",
        "message": {"role": "user", "content": message},
    })

    try:
        proc.stdin.write((ndjson + "\n").encode())
        proc.stdin.flush()
    except (BrokenPipeError, OSError):
        return f"[{agent_info['name']} stdin broken]"

    result_queue = queue.Queue()

    def _reader():
        try:
            while True:
                line = proc.stdout.readline()
                if not line:
                    result_queue.put({"type": "error", "error": "stdout closed"})
                    return
                line = line.decode().strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    if msg.get("type") == "result":
                        result_queue.put({"type": "result", "msg": msg})
                        return
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            result_queue.put({"type": "error", "error": str(e)})

    threading.Thread(target=_reader, daemon=True).start()

    try:
        item = result_queue.get(timeout=timeout)
        if item["type"] == "result":
            return _extract_text(item["msg"])
        return f"[{agent_info['name']} error: {item['error']}]"
    except queue.Empty:
        return f"[{agent_info['name']} timed out after {timeout}s]"


def _extract_text(msg: dict) -> str:
    if isinstance(msg.get("result"), str):
        return msg["result"]
    if isinstance(msg.get("text"), str):
        return msg["text"]
    if isinstance(msg.get("content"), list):
        return "\n".join(c.get("text", "") for c in msg["content"] if c.get("text"))
    return json.dumps(msg)
