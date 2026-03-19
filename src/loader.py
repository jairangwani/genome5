"""Loader — imports Python node files and builds the Genome.

Walks plan/ recursively. AST validates before importing. Tracks load errors.
Prunes knowledge to last 8. Makes genome5 importable for node files.
"""

import os
import sys
import ast
import types
from pathlib import Path

from src.genome import Genome
from src.node import Node


# Allowed imports in node files
ALLOWED_IMPORTS = {"genome5", "genome5.seeds", "os", "re", "yaml", "json", "datetime"}


def load_genome(project_dir: str) -> Genome:
    """Load all Python nodes from plan/ and build the Genome."""
    genome = Genome(project_dir)
    plan_dir = os.path.join(project_dir, "plan")

    if not os.path.exists(plan_dir):
        raise FileNotFoundError(f"No plan/ directory at {project_dir}")

    _ensure_genome5_importable()

    for root, dirs, files in os.walk(plan_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]

        for filename in files:
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            filepath = os.path.join(root, filename)

            # AST validation before import
            if not _ast_validate(filepath):
                genome.load_errors.append((filepath, "AST validation failed"))
                continue

            node, error = _load_node_from_file(filepath)
            if node:
                node._source_file = filepath
                node._mtime = os.path.getmtime(filepath)

                if node.knowledge and len(node.knowledge) > 8:
                    node.knowledge = node.knowledge[-8:]

                genome.add(node)
            elif error:
                genome.load_errors.append((filepath, error))

    genome.build_index()
    return genome


def _ast_validate(filepath: str) -> bool:
    """Validate Python file before importing. Reject dangerous code."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filepath)

        for node in ast.walk(tree):
            # Check imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_module = alias.name.split(".")[0]
                    if root_module not in ALLOWED_IMPORTS:
                        print(f"  AST reject {filepath}: import {alias.name}")
                        return False
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_module = node.module.split(".")[0]
                    if root_module not in ALLOWED_IMPORTS:
                        print(f"  AST reject {filepath}: from {node.module}")
                        return False

        return True
    except SyntaxError as e:
        print(f"  Syntax error in {filepath}: {e}")
        return False
    except Exception as e:
        print(f"  AST error in {filepath}: {e}")
        return False


def _load_node_from_file(filepath: str) -> tuple[Node | None, str | None]:
    """Import a Python file and extract the Node subclass instance."""
    mtime = int(os.path.getmtime(filepath) * 1000)
    module_name = f"_genome5_node_{Path(filepath).stem}_{mtime}"

    if module_name in sys.modules:
        del sys.modules[module_name]

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()

        code = compile(source, filepath, "exec")
        module = types.ModuleType(module_name)
        module.__file__ = filepath
        module.__name__ = module_name
        sys.modules[module_name] = module
        exec(code, module.__dict__)

        node_class = _find_node_class(module)
        if node_class:
            instance = node_class()
            if instance.name:
                return instance, None

        return None, None
    except Exception as e:
        print(f"  Warning: Failed to load {filepath}: {e}")
        return None, str(e)


def _find_node_class(module) -> type | None:
    """Find the first Node subclass defined in a module."""
    for name in dir(module):
        obj = getattr(module, name)
        if (isinstance(obj, type)
                and issubclass(obj, Node)
                and obj is not Node
                and obj.__module__ == module.__name__):
            return obj
    return None


_genome5_installed = False

def _ensure_genome5_importable():
    """Make 'genome5' importable so nodes can do 'from genome5 import Node'."""
    global _genome5_installed
    if _genome5_installed:
        return

    from src import node as node_module

    genome5_mod = types.ModuleType("genome5")
    for attr_name in ["Node", "Task", "Issue"]:
        setattr(genome5_mod, attr_name, getattr(node_module, attr_name))
    sys.modules["genome5"] = genome5_mod

    # Seed classes: from genome5.seeds import ServiceNode
    seeds_mod = types.ModuleType("genome5.seeds")
    sys.modules["genome5.seeds"] = seeds_mod

    seeds_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seeds")
    seed_classes_file = os.path.join(seeds_dir, "base_classes.py")

    if os.path.exists(seed_classes_file):
        try:
            with open(seed_classes_file, "r", encoding="utf-8") as f:
                source = f.read()
            code = compile(source, seed_classes_file, "exec")
            exec(code, seeds_mod.__dict__)
        except Exception as e:
            print(f"  Warning: Failed to load seed classes: {e}")

    _genome5_installed = True
