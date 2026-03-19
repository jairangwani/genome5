"""Debate Team — 1 Solver + 2 Breakers for exhaustive coverage.

Used for open-ended tasks where "are we sure we covered everything?" matters:
- Discovering ALL personas from a spec
- Discovering ALL use cases per persona
- Reviewing architecture decisions

NOT used for: writing code, creating specific journeys, fixing bugs.

The debate runs as a special engine mode. The solver proposes, breakers
challenge, solver integrates. Repeats until all say CONVERGED.
The solver's final output IS the result.
"""

import os
import json
import subprocess
import time


MAX_ROUNDS = 12


def run_debate(project_dir: str, topic: str, context_files: list[str],
               solver_instructions: str, breaker1_focus: str = "logical flaws",
               breaker2_focus: str = "practical gaps", model: str = "claude-sonnet-4-6",
               timeout: int = 300) -> str:
    """Run a 1+2 debate and return the solver's final output.

    Args:
        project_dir: working directory for agents
        topic: what they're debating (e.g., "List ALL personas for Pando")
        context_files: files to read (spec, existing nodes)
        solver_instructions: specific task for the solver
        breaker1_focus: angle for breaker 1
        breaker2_focus: angle for breaker 2
        model: Claude model to use
        timeout: seconds per agent turn

    Returns:
        The solver's final consolidated response.
    """

    debate_history = []

    def call_agent(role: str, role_instructions: str, round_num: int) -> str:
        """One-shot agent call with debate history."""
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

        prompt = (
            f"You are the {role}. {role_instructions}\n\n"
            f"TOPIC: {topic}\n\n"
        )

        if round_num <= 2:
            prompt += f"CONTEXT:\n{context_text}\n\n"
        else:
            prompt += f"CONTEXT: Read the files on disk if needed. Key files: {[os.path.basename(f) for f in context_files]}\n\n"

        if history_text:
            prompt += f"DEBATE HISTORY:\n{history_text}\n\n"

        prompt += (
            f"YOUR TURN (Round {round_num}). "
            f"Be specific. Build on previous rounds. "
            f"If you genuinely cannot find more issues or improvements, "
            f"end your response with the word CONVERGED.\n"
            f"Keep response under 2000 words."
        )

        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        try:
            result = subprocess.run(
                ["claude", "--output-format", "text", "--model", model],
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

    # Run debate rounds
    for round_num in range(1, MAX_ROUNDS + 1):
        if round_num % 3 == 1:
            # Solver's turn
            role = "SOLVER"
            if round_num == 1:
                instructions = f"You propose the answer. {solver_instructions}"
            else:
                instructions = (
                    f"Integrate the breakers' feedback. Update your answer. "
                    f"Address every point they raised — accept valid ones, "
                    f"defend wrong ones with reasoning. {solver_instructions}"
                )
        elif round_num % 3 == 2:
            # Breaker 1's turn
            role = "BREAKER 1"
            instructions = (
                f"Find flaws in the solver's answer. Focus on: {breaker1_focus}. "
                f"For each flaw, hint at a solution. Don't repeat previous points."
            )
        else:
            # Breaker 2's turn
            role = "BREAKER 2"
            instructions = (
                f"Find gaps the solver AND breaker 1 missed. Focus on: {breaker2_focus}. "
                f"For each gap, hint at what's missing. Don't repeat previous points."
            )

        print(f"  Debate round {round_num}: {role}...")
        response = call_agent(role, instructions, round_num)

        debate_history.append({
            "role": role,
            "round": round_num,
            "content": response,
        })

        # Check convergence
        if "CONVERGED" in response:
            # Check if ALL roles have converged in their latest rounds
            latest = {}
            for entry in debate_history:
                latest[entry["role"]] = entry["content"]

            all_converged = all(
                "CONVERGED" in latest.get(r, "")
                for r in ["SOLVER", "BREAKER 1", "BREAKER 2"]
                if r in latest
            )

            if all_converged and round_num >= 4:
                print(f"  Debate converged after {round_num} rounds.")
                break

    # Return the solver's LAST response as the final answer
    solver_responses = [e["content"] for e in debate_history if e["role"] == "SOLVER"]
    if solver_responses:
        return solver_responses[-1]
    return "Debate produced no solver output."
