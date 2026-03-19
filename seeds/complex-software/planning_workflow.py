"""Planning Workflow — USE-CASE-FIRST, OPEN SYSTEM.

Reads engine_state.yaml for convergence tracking.
Does NOT store state in its own class attributes.
Engine writes engine_state.yaml. This node reads it.
Clean separation: engine owns engine state, agents own node content.
"""
import os
import yaml
from genome5 import Node, Task


class PlanningWorkflow(Node):
    name = "Planning Workflow"
    type = "workflow"
    level = 0
    description = "Use-case-first planning. Debate for discovery. Open for evolution."
    edges = {}

    def validate(self, genome) -> list[Task]:
        tasks = []

        context = self._read_context(genome)
        if not context:
            return tasks

        reference = context.get("planning", {}).get("reference", "")
        personas = genome.nodes_by_type("persona")
        use_cases = genome.nodes_by_type("use_case")
        journeys = [n for n in genome.all_nodes() if n.type == "journey"]

        # Read engine state — convergence info lives here, NOT in this node
        engine_state = self._read_engine_state(genome)

        # ============================================
        # PERSONA DISCOVERY
        # Check engine_state for convergence. If not converged, fire debate.
        # Wake-up: if persona count grew since convergence, re-debate.
        # ============================================

        persona_state = engine_state.get("initial-personas", engine_state.get("verify-personas", {}))
        persona_converged = persona_state.get("converged", False)
        persona_count_at_conv = persona_state.get("personas", 0)

        # Wake-up: new personas appeared since convergence
        if persona_converged and len(personas) > persona_count_at_conv:
            persona_converged = False

        if not persona_converged:
            persona_names = [p.name for p in personas]
            if not personas:
                tasks.append(Task(
                    f"PERSONA DISCOVERY: Read {reference}. "
                    f"WHO uses this system? Create persona nodes in plan/.",
                    self.name, phase="planning", priority=1,
                    check="initial-personas",
                    suggestion=(
                        f"Create persona .py files. Each: name, type='persona', "
                        f"level=1, description, goals, edges={{parent: 'Users Domain', "
                        f"owned_by: 'Planning Agent'}}. Think exhaustively."
                    ),
                    debate=True,
                ))
            else:
                tasks.append(Task(
                    f"PERSONA VERIFICATION: {len(personas)} personas exist. "
                    f"Re-read {reference}. WHO is missing? All 3 debaters must agree.",
                    self.name, phase="planning", priority=1,
                    check="verify-personas",
                    suggestion=f"Existing: {', '.join(persona_names[:15])}. Add missing ones.",
                    debate=True,
                ))

        # ============================================
        # USE CASE DISCOVERY PER PERSONA
        # Check engine_state per persona. Fire debate if not converged.
        # ============================================

        for persona in personas:
            persona_ucs = [uc for uc in use_cases
                          if persona.name in str(uc.edges)]

            uc_key = f"discover-usecases-{persona.name[:20]}"
            uc_state = engine_state.get(uc_key, {})
            uc_converged = uc_state.get("converged", False)

            if uc_converged:
                continue

            if len(persona_ucs) < 3:
                tasks.append(Task(
                    f"USE CASES for '{persona.name}': has {len(persona_ucs)}. "
                    f"WHAT can {persona.name} do? Create use case nodes. "
                    f"Happy path, errors, edge cases, abuse. 10-30 per persona.",
                    persona.name, phase="planning", priority=2,
                    check=uc_key,
                    suggestion=(
                        f"Create .py files: name, type='use_case', level=2, "
                        f"description, edges={{parent: '{persona.name}', "
                        f"owned_by: 'Planning Agent'}}."
                    ),
                    debate=True,
                ))

        # ============================================
        # JOURNEY CREATION (no debate, specific tasks)
        # ============================================

        for uc in use_cases:
            uc_journeys = [j for j in journeys
                          if j.edges.get("parent") == uc.name]
            if not uc_journeys:
                tasks.append(Task(
                    f"JOURNEY for '{uc.name}': Write step-by-step HOW. "
                    f"Reference services in [brackets]. Include error paths. "
                    f"10-25 steps. Create the journey .py file.",
                    uc.name, phase="planning", priority=3,
                    check=f"journey-{uc.name[:20]}",
                ))

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

    def _read_engine_state(self, genome) -> dict:
        state_path = os.path.join(genome.project_dir, "plan", "engine_state.yaml")
        if not os.path.exists(state_path):
            return {}
        try:
            with open(state_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}
