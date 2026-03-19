"""Planning Workflow — USE-CASE-FIRST, NO RIGID GATES.

The debate team fires for INITIAL discovery of personas and use cases.
After that, the system stays OPEN — new personas, use cases, journeys
can be created at ANY time by any agent.

The workflow TRACKS what's been done, but does NOT BLOCK new work.
Debate convergence is recorded so we know if all 3 agreed.
"""
import os
import yaml
from genome5 import Node, Task


class PlanningWorkflow(Node):
    name = "Planning Workflow"
    type = "workflow"
    level = 0
    description = "Use-case-first planning. Debate for initial discovery. Open for ongoing evolution."
    edges = {}

    # Track debate convergence — did all 3 agree?
    persona_debate_converged: bool = False
    use_case_debates_converged: dict = {}  # persona_name → True/False

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
        # INITIAL PERSONA DISCOVERY (debate team)
        # Fires once. After convergence, system stays open.
        # New personas can be added anytime via dangling edges.
        # ============================================

        if not self.persona_debate_converged:
            persona_names = [p.name for p in personas]
            if not personas:
                tasks.append(Task(
                    f"INITIAL PERSONA DISCOVERY: Read {reference}. "
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
                    f"Add missing personas. When ALL 3 debaters agree nothing "
                    f"is missing, the debate converges and we move on.",
                    self.name, phase="planning", priority=1,
                    check="verify-personas",
                    suggestion=(
                        f"Existing: {', '.join(persona_names)}. "
                        f"Read the full spec. Create .py files for missing personas."
                    ),
                    debate=True,
                ))
            # NOTE: NOT returning early. Other tasks can coexist.
            # The debate runs, but doesn't block everything else.

        # ============================================
        # USE CASE DISCOVERY PER PERSONA (debate team)
        # Fires for each persona that has < 3 use cases.
        # After debate converges for a persona, it's done.
        # New use cases can still be added anytime.
        # ============================================

        for persona in personas:
            persona_ucs = [uc for uc in use_cases
                          if persona.name in str(uc.edges)]

            # Skip if this persona's debate already converged
            if self.use_case_debates_converged.get(persona.name):
                continue

            if len(persona_ucs) < 3:
                tasks.append(Task(
                    f"USE CASE DISCOVERY for '{persona.name}': "
                    f"has {len(persona_ucs)} use cases. "
                    f"WHAT can {persona.name} do? List EVERY action: "
                    f"happy path, error recovery, edge cases, abuse scenarios. "
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
        # For each use case without a journey.
        # No gate — runs alongside other work.
        # ============================================

        for uc in use_cases:
            uc_journeys = [j for j in journeys
                          if j.edges.get("parent") == uc.name]
            if not uc_journeys:
                tasks.append(Task(
                    f"JOURNEY for '{uc.name}': Write step-by-step HOW this works. "
                    f"Reference services in [brackets]. Include error paths. "
                    f"10-25 steps.",
                    uc.name, phase="planning", priority=3,
                    check=f"journey-{uc.name[:20]}",
                ))

        # ============================================
        # SERVICES EMERGE (engine handles via dangling edges)
        # Journey steps reference [ServiceName].
        # If service doesn't exist → dangling edge → engine creates it.
        # No explicit task needed here — the validator handles it.
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
