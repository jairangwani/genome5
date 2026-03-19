"""genome5 CLI — check, converge, init, status."""

import sys
import os

os.environ["PYTHONUNBUFFERED"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine import check, converge
from src.node import Task


def main():
    args = sys.argv[1:]
    command = args[0] if args else None
    path = args[1] if len(args) > 1 else "."
    project_dir = os.path.abspath(path)

    if command == "check":
        print(f"Checking {project_dir}/plan/\n")
        genome, issues = check(project_dir)
        for t in issues:
            icon = "x" if t.severity == "error" else "!" if t.severity == "warning" else "-"
            node = f" [{t.node_name}]" if t.node_name else ""
            print(f"  {icon} [{t.phase}]{node} {t.message}")
        errors = [i for i in issues if i.severity == "error"]
        print(f"\n{len(genome.nodes)} nodes, {len(issues)} issues ({len(errors)} errors)")
        if errors:
            sys.exit(1)

    elif command == "converge":
        print(f"Converging {project_dir}/plan/\n")
        from src.agent_manager import create_agent_manager
        mgr = create_agent_manager(project_dir)
        try:
            converge(project_dir, mgr)
        except KeyboardInterrupt:
            print("\nStopping...")
            mgr.kill()
        except Exception as e:
            import traceback, datetime
            tb = traceback.format_exc()
            print(f"\nCRASH: {e}\n{tb}")
            crash_log = os.path.join(project_dir, "plan", "engine-crash.log")
            with open(crash_log, "a", encoding="utf-8") as f:
                f.write(f"\n--- {datetime.datetime.now()} ---\n{tb}\n")
            mgr.kill()
            sys.exit(1)

    elif command == "init":
        seed = "blank"
        for a in args[1:]:
            if a.startswith("--seed="):
                seed = a.split("=", 1)[1]
            elif not a.startswith("-"):
                project_dir = os.path.abspath(a)

        print(f"Initializing genome5 project at {project_dir}")
        plan_dir = os.path.join(project_dir, "plan")
        os.makedirs(plan_dir, exist_ok=True)

        ctx_path = os.path.join(plan_dir, "context.yaml")
        if not os.path.exists(ctx_path):
            import yaml
            yaml.dump({"seed": seed, "description": "New genome5 project"},
                      open(ctx_path, "w", encoding="utf-8"), default_flow_style=False)
        print(f"  Created. Run: genome5 converge {project_dir}")

    elif command == "status":
        status_path = os.path.join(project_dir, "plan", "status.yaml")
        if os.path.exists(status_path):
            with open(status_path, encoding="utf-8") as f:
                print(f.read())
        else:
            print("No status.yaml. Run genome5 check first.")

    else:
        print("""
genome5 — The Agent Protocol. Use-case-first.

  genome5 check [path]              Validate, print tasks
  genome5 converge [path]           Convergence loop with agents
  genome5 init [path] --seed=X      Initialize project
  genome5 status [path]             Show status
""")


if __name__ == "__main__":
    main()
