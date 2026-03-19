"""Planning Workflow — USE-CASE-FIRST, OPEN SYSTEM, DEBATE CONVERGENCE.

The debate team fires for discovery AND wakes up when new nodes appear.
No rigid gates. The system stays open. But debate must converge before
marking any phase done.

Wake-up logic: if a new persona appears that wasn't part of the converged
debate, the persona debate re-opens. Same for use cases.
"""
import os
import yaml
from genome5 import Node, Task


class PlanningWorkflow(Node):
    name = "Planning Workflow"
    type = "workflow"
    level = 0
    description = "Use-case-first. Debate for discovery. Open for evolution. Wake-up on new nodes."
    edges = {}

    # Convergence tracking
    persona_debate_converged: bool = False
    persona_count_at_convergence: int = 0  # how many personas when debate converged
    use_case_debates_converged: dict = {}  # persona_name → True/False

    def __init__(self):
        super().__init__()
        self.use_case_debates_converged = dict(
            getattr(type(self), 'use_case_debates_converged', {}))

    def validate(self, genome) -> list[Task]:
        tasks = []

        context = self._read_context(genome)
        if not context:
            return tasks

        reference = context.get("planning", {}).get("reference", "")
        personas = genome.nodes_by_type("persona")
        use_cases = genome.nodes_by_type("use_case")
        journeys = [n for n in genome.all_nodes() if n.type == "journey"]

        # ============================================
        # PERSONA DISCOVERY + WAKE-UP
        # Initial: debate team discovers all personas.
        # Wake-up: if new personas appear after convergence,
        #   re-open the debate to verify completeness.
        # ============================================

        # Wake-up check: did new personas appear since convergence?
        if self.persona_debate_converged and len(personas) > self.persona_count_at_convergence:
            print(f"  WAKE-UP: {len(personas)} personas now vs {self.persona_count_at_convergence} at convergence. Re-opening debate.")
            self.persona_debate_converged = False

        if not self.persona_debate_converged:
            persona_names = [p.name for p in personas]
            if not personas:
                tasks.append(Task(
                    f"PERSONA DISCOVERY: Read {reference}. "
                    f"WHO uses this system? List EVERY type of user, operator, "
                    f"threat actor, and automated agent. Create persona nodes.",
                    self.name, phase="planning", priority=1,
                    check="initial-personas",
                    suggestion=(
                        f"Create persona nodes in plan/. Each: name, type='persona', "
                        f"level=1, description, goals, edges={{parent: 'Users Domain', "
                        f"owned_by: 'Planning Agent'}}. Think exhaustively."
                    ),
                    debate=True,
                ))
            else:
                tasks.append(Task(
                    f"PERSONA VERIFICATION: {len(personas)} personas exist: "
                    f"{', '.join(persona_names[:15])}{'...' if len(personas) > 15 else ''}. "
                    f"Re-read {reference}. WHO is NOT in this list? "
                    f"Add missing personas. All 3 debaters must agree nothing "
                    f"is missing for this to converge.",
                    self.name, phase="planning", priority=1,
                    check="verify-personas",
                    suggestion=(
                        f"Existing: {', '.join(persona_names)}. "
                        f"Read the full spec. Create .py files for missing personas."
                    ),
                    debate=True,
                ))

        # ============================================
        # USE CASE DISCOVERY PER PERSONA + WAKE-UP
        # Debate for each persona with < 3 use cases.
        # Wake-up: new use cases added externally reset convergence.
        # ============================================

        for persona in personas:
            persona_ucs = [uc for uc in use_cases
                          if persona.name in str(uc.edges)]

            # Wake-up: if persona had converged but now has new UCs
            # (added by another agent/journey discovery), re-verify
            prev_converged = self.use_case_debates_converged.get(persona.name, False)
            if prev_converged:
                continue  # This persona's UCs are debate-verified

            if len(persona_ucs) < 3:
                tasks.append(Task(
                    f"USE CASE DISCOVERY for '{persona.name}': "
                    f"has {len(persona_ucs)} use cases. "
                    f"WHAT can {persona.name} do? List EVERY action: "
                    f"happy path, error recovery, edge cases, abuse. "
                    f"Aim for 10-30 use cases.",
                    persona.name, phase="planning", priority=2,
                    check=f"discover-usecases-{persona.name[:20]}",
                    suggestion=(
                        f"Create use case nodes: name, type='use_case', level=2, "
                        f"description, edges={{parent: '{persona.name}', "
                        f"owned_by: 'Planning Agent'}}."
                    ),
                    debate=True,
                ))

        # ============================================
        # JOURNEY CREATION (no debate, specific tasks)
        # Runs alongside everything else. No gate.
        # ============================================

        for uc in use_cases:
            uc_journeys = [j for j in journeys
                          if j.edges.get("parent") == uc.name]
            if not uc_journeys:
                tasks.append(Task(
                    f"JOURNEY for '{uc.name}': Write step-by-step HOW. "
                    f"Reference services in [brackets]. Include error paths. "
                    f"10-25 steps.",
                    uc.name, phase="planning", priority=3,
                    check=f"journey-{uc.name[:20]}",
                ))

        # ============================================
        # SERVICES EMERGE from dangling edges.
        # Engine handles this automatically via validator.
        # ============================================

        return tasks

    def _read_context(self, genome) -> dict:
        ctx_path = os.path.join(genome.project_dir, "plan", "context.yaml")
        if not os.path.exists(ctx_path):
            return {}
        try:
            with open(ctx_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}
