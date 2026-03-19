"""Debate Team — 1 Solver + 2 Breakers for exhaustive coverage.

ALL THREE must say CONVERGED for the debate to end successfully.
Max 50 rounds. Every round logged to plan/debate_log.md.
Returns (result_text, converged_bool).
"""

import os
import subprocess
import time
import datetime

MAX_ROUNDS = 50


def run_debate(project_dir: str, topic: str, context_files: list[str],
               solver_instructions: str, breaker1_focus: str = "logical flaws",
               breaker2_focus: str = "practical gaps", model: str = "claude-opus-4-6",
               timeout: int = 300) -> tuple[str, bool]:
    """Run a 1+2 debate. Returns (solver_final_output, all_3_converged)."""

    debate_history = []
    log_path = os.path.join(project_dir, "plan", "debate_log.md")
    topic_short = topic[:60].replace('\n', ' ')
    debate_id = datetime.datetime.now().strftime("%H:%M:%S")

    def _log(msg: str):
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")

    _log(f"\n{'='*60}")
    _log(f"## DEBATE [{debate_id}]: {topic_short}")
    _log(f"Model: {model} | Max rounds: {MAX_ROUNDS}")
    _log(f"{'='*60}\n")

    def call_agent(role: str, role_instructions: str, round_num: int) -> str:
        context_text = ""
        for cf in context_files:
            if os.path.exists(cf):
                try:
                    with open(cf, "r", encoding="utf-8") as f:
                        content = f.read()
                    context_text += f"\n=== {os.path.basename(cf)} ===\n{content[:8000]}\n"
                except Exception:
                    pass

        history_text = ""
        for entry in debate_history:
            history_text += f"\n--- {entry['role']} (Round {entry['round']}) ---\n{entry['content']}\n"

        prompt = f"{role}. {role_instructions}\n\nTOPIC: {topic}\n\n"

        if round_num <= 2:
            prompt += f"CONTEXT:\n{context_text}\n\n"
        else:
            prompt += f"CONTEXT: Read files on disk if needed. Key: {[os.path.basename(f) for f in context_files]}\n\n"

        if history_text:
            prompt += f"DEBATE HISTORY:\n{history_text}\n\n"

        prompt += (
            f"YOUR TURN (Round {round_num}/{MAX_ROUNDS}). "
            f"Be specific. Build on previous rounds. "
            f"If you genuinely cannot find ANY more issues or improvements, "
            f"end your response with the EXACT word CONVERGED on its own line.\n"
            f"Keep response under 2000 words."
        )

        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)
        try:
            result = subprocess.run(
                ["claude", "--output-format", "text", "--model", model,
                 "--dangerously-skip-permissions"],
                input=prompt, capture_output=True, text=True,
                timeout=timeout, cwd=project_dir, env=env,
                encoding="utf-8", errors="replace",
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            return f"[{role} error: {result.stderr[:200] if result.stderr else 'no output'}]"
        except subprocess.TimeoutExpired:
            return f"[{role} timed out after {timeout}s]"
        except Exception as e:
            return f"[{role} exception: {str(e)[:200]}]"

    # Track per-role convergence
    role_converged = {"SOLVER": False, "BREAKER 1": False, "BREAKER 2": False}
    final_converged = False

    for round_num in range(1, MAX_ROUNDS + 1):
        if round_num % 3 == 1:
            role = "SOLVER"
            if round_num == 1:
                instructions = f"You propose the answer. {solver_instructions}"
            else:
                instructions = (
                    f"Integrate the breakers' feedback. Update your answer. "
                    f"Address every point raised. {solver_instructions}"
                )
        elif round_num % 3 == 2:
            role = "BREAKER 1"
            instructions = (
                f"Find flaws in the solver's answer. Focus on: {breaker1_focus}. "
                f"Hint at solutions. Don't repeat previous points."
            )
        else:
            role = "BREAKER 2"
            instructions = (
                f"Find gaps the solver AND breaker 1 missed. Focus on: {breaker2_focus}. "
                f"Hint at what's missing. Don't repeat previous points."
            )

        print(f"  Debate [{debate_id}] round {round_num}/{MAX_ROUNDS}: {role}...")
        response = call_agent(role, instructions, round_num)

        # Check for CONVERGED as the LAST word or on its own line
        # Not just anywhere in the text (could appear in quotes/context)
        has_converged = response.rstrip().endswith("CONVERGED")
        if has_converged:
            role_converged[role] = True

        # Log every round with full detail
        conv_marker = " [CONVERGED]" if has_converged else ""
        _log(f"### Round {round_num}: {role}{conv_marker}")
        _log(f"{response[:800]}{'...' if len(response) > 800 else ''}\n")

        debate_history.append({
            "role": role,
            "round": round_num,
            "content": response,
        })

        # Check if ALL THREE have converged
        all_converged = all(role_converged.values())
        if all_converged and round_num >= 4:
            final_converged = True
            print(f"  Debate [{debate_id}] ALL 3 CONVERGED after {round_num} rounds!")
            _log(f"\n**RESULT: ALL 3 CONVERGED after {round_num}/{MAX_ROUNDS} rounds.**")
            _log(f"  SOLVER: converged={role_converged['SOLVER']}")
            _log(f"  BREAKER 1: converged={role_converged['BREAKER 1']}")
            _log(f"  BREAKER 2: converged={role_converged['BREAKER 2']}\n")
            break

        # If one role converged but another didn't, the converged role's
        # status resets — they need to re-confirm after seeing new feedback
        if has_converged and not all_converged:
            _log(f"  ({role} converged but waiting for others...)\n")

    if not final_converged:
        print(f"  Debate [{debate_id}] hit MAX_ROUNDS ({MAX_ROUNDS}) — did NOT converge.")
        _log(f"\n**RESULT: MAX ROUNDS ({MAX_ROUNDS}) reached. Did NOT converge.**")
        _log(f"  SOLVER: converged={role_converged['SOLVER']}")
        _log(f"  BREAKER 1: converged={role_converged['BREAKER 1']}")
        _log(f"  BREAKER 2: converged={role_converged['BREAKER 2']}\n")

    _log(f"Total rounds: {len(debate_history)} | Final converged: {final_converged}\n")

    solver_responses = [e["content"] for e in debate_history if e["role"] == "SOLVER"]
    result = solver_responses[-1] if solver_responses else "No solver output."
    return result, final_converged
