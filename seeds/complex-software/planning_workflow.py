"""Planning Workflow — enforces USE-CASE-FIRST ordering.

Phase 1: Personas (WHO?) — debate team ensures exhaustive coverage
Phase 2: Use cases per persona (WHAT?) — debate team per persona
Phase 3: Journeys (HOW?) — step by step with [service] references
Phase 4: Services EMERGE from journey references (dangling edges)
Phase 5: Hierarchy grows as services group

This node's validate() fires tasks in the CORRECT ORDER.
It does NOT let agents skip to services before personas exist.
"""
import os
import yaml
from genome5 import Node, Task


class PlanningWorkflow(Node):
    name = "Planning Workflow"
    type = "workflow"
    level = 0
    description = "Enforces use-case-first ordering: personas → use cases → journeys → services emerge."
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
        services = genome.nodes_by_type("service")

        # ============================================
        # PHASE 1: PERSONAS
        # Must exist before anything else.
        # Uses debate team for exhaustive coverage.
        # ============================================

        personas_complete = any(
            (getattr(a, 'doc', '') or '').lower().startswith("personas complete")
            for a in genome.nodes_by_type("agent")
        )

        if not personas_complete:
            if not personas:
                # No personas at all — first task. USE DEBATE TEAM.
                tasks.append(Task(
                    f"PHASE 1: Discover ALL personas. Read {reference}. "
                    f"WHO uses this system? List every type of user, operator, "
                    f"threat actor, and automated agent. Create a persona node "
                    f"for each. When you've exhausted all personas, set your "
                    f"doc field to 'Personas complete. [count] personas created.'",
                    self.name, phase="planning", priority=1,
                    check="phase1-personas",
                    suggestion=(
                        f"Create persona nodes in plan/. Each persona is a .py file "
                        f"with name, type='persona', level=1, description, goals, "
                        f"edges={{parent: 'Users Domain', owned_by: 'Planning Agent'}}. "
                        f"Think exhaustively: primary users, secondary users, operators, "
                        f"administrators, threat actors, automated agents, API consumers, "
                        f"visitors, moderators, governance participants."
                    ),
                    debate=True,  # 1 solver + 2 breakers for exhaustive coverage
                ))
            else:
                # Personas exist but not marked complete — exhaustion check
                persona_names = [p.name for p in personas]
                tasks.append(Task(
                    f"PHASE 1 EXHAUSTION: {len(personas)} personas exist: "
                    f"{', '.join(persona_names[:10])}{'...' if len(personas) > 10 else ''}. "
                    f"Re-read {reference}. WHO is NOT in this list? "
                    f"Think about: visitors, admins, moderators, API integrators, "
                    f"automated agents, threat actors, operators, developers, "
                    f"contributors, governance participants. "
                    f"Add any missing personas. If truly complete, set doc to "
                    f"'Personas complete. {len(personas)} personas created.'",
                    self.name, phase="planning", priority=1,
                    check="phase1-exhaustion",
                    suggestion=(
                        f"Existing personas: {', '.join(persona_names)}. "
                        f"Read the full spec. WHO is missing from this list? "
                        f"Create .py files for any missing personas."
                    ),
                    debate=True,  # ALL debates must converge — all 3 agree
                ))
            return tasks  # GATE: nothing else until personas complete

        # ============================================
        # PHASE 2: USE CASES PER PERSONA
        # For each persona, exhaustively list what they can do.
        # ============================================

        use_cases_complete = any(
            (getattr(a, 'doc', '') or '').lower().startswith("use cases complete")
            for a in genome.nodes_by_type("agent")
        )

        if not use_cases_complete:
            # Find personas with few/no use cases
            for persona in personas:
                persona_ucs = [uc for uc in use_cases
                              if persona.name in str(uc.edges)]
                if len(persona_ucs) < 3:
                    tasks.append(Task(
                        f"PHASE 2: '{persona.name}' has {len(persona_ucs)} use cases. "
                        f"WHAT can {persona.name} do? List EVERY action: "
                        f"happy path, error recovery, edge cases, abuse scenarios. "
                        f"Think: what do they create? browse? configure? monitor? "
                        f"What goes wrong? What do they do about it? "
                        f"Create use case nodes with parent='{persona.name}'. "
                        f"Aim for 10-20 use cases per persona.",
                        persona.name, phase="planning", priority=2,
                        check=f"phase2-usecases-{persona.name[:20]}",
                        suggestion=(
                            f"Create use case nodes in plan/. Each is a .py file with "
                            f"name, type='use_case', level=2, description, "
                            f"edges={{parent: '{persona.name}', owned_by: 'Planning Agent'}}."
                        ),
                        debate=True,  # exhaustive use-case discovery
                    ))

            if not tasks:
                # All personas have 3+ use cases — check for completion
                total_ucs = len(use_cases)
                tasks.append(Task(
                    f"PHASE 2 EXHAUSTION: {total_ucs} use cases across "
                    f"{len(personas)} personas. Re-read {reference}. "
                    f"For each persona, are ALL scenarios covered? "
                    f"Happy path + errors + edge cases + abuse? "
                    f"If complete, set doc to 'Use cases complete. "
                    f"{total_ucs} use cases across {len(personas)} personas.'",
                    self.name, phase="planning", priority=2,
                    check="phase2-exhaustion",
                ))

            if tasks:
                return tasks  # GATE: no journeys until use cases complete

        # ============================================
        # PHASE 3: JOURNEYS PER USE CASE
        # Step-by-step flows. Reference services in [brackets].
        # ============================================

        journeys_complete = any(
            (getattr(a, 'doc', '') or '').lower().startswith("journeys complete")
            for a in genome.nodes_by_type("agent")
        )

        if not journeys_complete:
            for uc in use_cases:
                # Check if this use case has a journey child
                uc_journeys = [j for j in journeys
                              if j.edges.get("parent") == uc.name]
                if not uc_journeys:
                    tasks.append(Task(
                        f"PHASE 3: Use case '{uc.name}' has no journey. "
                        f"Write step-by-step: HOW does this work? "
                        f"Reference services in [brackets]: [Gateway], [Auth], etc. "
                        f"Include error paths. 10-25 steps. "
                        f"Create journey node with parent='{uc.name}'.",
                        uc.name, phase="planning", priority=3,
                        check=f"phase3-journey-{uc.name[:20]}",
                    ))

            if not tasks:
                tasks.append(Task(
                    f"PHASE 3 COMPLETE CHECK: {len(journeys)} journeys for "
                    f"{len(use_cases)} use cases. Review: does every journey "
                    f"have error paths? Do steps reference specific services? "
                    f"If complete, set doc to 'Journeys complete.'",
                    self.name, phase="planning", priority=3,
                    check="phase3-exhaustion",
                ))

            if tasks:
                return tasks  # GATE: services emerge from journeys, not before

        # ============================================
        # PHASE 4: SERVICES EMERGE
        # Dangling edges from journey [brackets] create service tasks.
        # The engine's dangling edge detection handles this automatically.
        # This phase just monitors.
        # ============================================

        # Check if there are unresolved dangling edges
        # (services referenced in journeys that don't exist)
        # The validator already creates tasks for these.
        # We just add a review task after services stabilize.

        services_reviewed = any(
            (getattr(a, 'doc', '') or '').lower().startswith("services reviewed")
            for a in genome.nodes_by_type("agent")
        )

        if services and not services_reviewed:
            tasks.append(Task(
                f"PHASE 4: {len(services)} services emerged from journeys. "
                f"Review: are they well-organized? Should any be merged? "
                f"Do they have descriptions and failure_modes? "
                f"If satisfied, set doc to 'Services reviewed.'",
                self.name, phase="review", priority=4, severity="warning",
                check="phase4-service-review",
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
