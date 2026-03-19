"""Core genome5 tests."""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.node import Node, Task
from src.genome import Genome
from src.validator import validate_genome, prioritize, _check_dangling_edges, _check_level_consistency
from src.regression import detect_regression


def test_node_requires_name():
    n = Node()
    tasks = n.validate(Genome("."))
    assert any("no name" in t.message for t in tasks)


def test_node_clean():
    n = Node()
    n.name = "Test"
    n.description = "A test"
    tasks = n.validate(Genome("."))
    assert len(tasks) == 0


def test_mutable_defaults():
    a = Node()
    b = Node()
    a.edges["test"] = "x"
    a.expected_children.append("y")
    assert "test" not in b.edges
    assert "y" not in b.expected_children


def test_node_get_owner():
    g = Genome(".")
    agent = Node(); agent.name = "Agent"; agent.type = "agent"; g.add(agent)
    svc = Node(); svc.name = "Service"; svc.edges = {"owned_by": "Agent"}; g.add(svc)
    assert svc.get_owner(g).name == "Agent"


def test_genome_nodes_by_type():
    g = Genome(".")
    a = Node(); a.name = "A"; a.type = "service"; g.add(a)
    b = Node(); b.name = "B"; b.type = "persona"; g.add(b)
    assert len(g.nodes_by_type("service")) == 1


def test_genome_parent_index():
    g = Genome(".")
    parent = Node(); parent.name = "Parent"; g.add(parent)
    child = Node(); child.name = "Child"; child.edges = {"parent": "Parent"}; g.add(child)
    g.build_index()
    assert len(g.children_of("Parent")) == 1
    assert g.children_of("Parent")[0].name == "Child"


def test_dangling_edge():
    g = Genome(".")
    n = Node(); n.name = "A"; n.edges = {"calls": "NonExistent"}; g.add(n)
    tasks = _check_dangling_edges(g)
    assert any("NonExistent" in t.message for t in tasks)


def test_no_dangling_when_exists():
    g = Genome(".")
    a = Node(); a.name = "A"; a.edges = {"calls": "B"}; g.add(a)
    b = Node(); b.name = "B"; g.add(b)
    tasks = _check_dangling_edges(g)
    assert len(tasks) == 0


def test_level_consistency():
    g = Genome(".")
    parent = Node(); parent.name = "P"; parent.level = 0; g.add(parent)
    child = Node(); child.name = "C"; child.level = 2; child.edges = {"parent": "P"}; g.add(child)
    tasks = _check_level_consistency(g)
    assert any("level" in t.message.lower() for t in tasks)


def test_level_consistency_valid():
    g = Genome(".")
    parent = Node(); parent.name = "P"; parent.level = 0; g.add(parent)
    child = Node(); child.name = "C"; child.level = 1; child.edges = {"parent": "P"}; g.add(child)
    tasks = _check_level_consistency(g)
    assert len(tasks) == 0


def test_prioritize_phase():
    tasks = [
        Task("dev", phase="dev", priority=1),
        Task("structural", phase="structural", priority=1),
    ]
    sorted_t = prioritize(tasks)
    assert sorted_t[0].phase == "structural"


def test_regression_fixed():
    assigned = Task("Fix X", "x")
    before = [Task("Fix X", "x")]
    after = []
    assert detect_regression(assigned, before, after) is None


def test_regression_not_fixed_no_new():
    assigned = Task("Fix X", "x")
    before = [Task("Fix X", "x")]
    after = [Task("Fix X", "x")]
    assert detect_regression(assigned, before, after) is None


def test_regression_new_criticals():
    assigned = Task("Fix X", "x")
    before = [Task("Fix X", "x")]
    after = [Task("Fix X", "x"), Task("Boom", "z", priority=1)]
    assert detect_regression(assigned, before, after) is not None


def test_loader_empty(tmp_path):
    (tmp_path / "plan").mkdir()
    from src.loader import load_genome
    g = load_genome(str(tmp_path))
    assert len(g.nodes) == 0


def test_loader_loads_node(tmp_path):
    plan = tmp_path / "plan"
    plan.mkdir()
    (plan / "test_node.py").write_text('''
from genome5 import Node
class TestNode(Node):
    name = "My Node"
    type = "test"
    description = "A test"
''', encoding="utf-8")
    from src.loader import load_genome
    g = load_genome(str(tmp_path))
    assert g.get("My Node") is not None


def test_loader_tracks_errors(tmp_path):
    plan = tmp_path / "plan"
    plan.mkdir()
    (plan / "bad.py").write_text("this is {{invalid}}", encoding="utf-8")
    from src.loader import load_genome
    g = load_genome(str(tmp_path))
    assert len(g.load_errors) >= 1


def test_exhaustion_state3_fires():
    """When all expected_children exist and children_verified=False, State 3 fires."""
    g = Genome(".")
    parent = Node(); parent.name = "Parent"; parent.level = 0
    parent.expected_children = ["Child A", "Child B"]
    parent.children_verified = False
    parent.description = "test"
    g.add(parent)

    child_a = Node(); child_a.name = "Child A"; child_a.level = 1
    child_a.edges = {"parent": "Parent"}; child_a.description = "a"; g.add(child_a)
    child_b = Node(); child_b.name = "Child B"; child_b.level = 1
    child_b.edges = {"parent": "Parent"}; child_b.description = "b"; g.add(child_b)

    g.build_index()
    from src.validator import _check_exhaustion
    tasks = _check_exhaustion(g)
    assert len(tasks) >= 1
    assert any("EXHAUSTION CHECK" in t.message for t in tasks)
    assert any(t.fresh_session for t in tasks)


def test_exhaustion_state4_fires():
    """When children_verified=True but not reviewed, State 4 fires."""
    g = Genome(".")
    parent = Node(); parent.name = "Parent"; parent.level = 0
    parent.expected_children = ["Child"]
    parent.children_verified = True
    parent.children_reviewed = False
    parent.description = "test"
    g.add(parent)

    child = Node(); child.name = "Child"; child.level = 1
    child.edges = {"parent": "Parent"}; child.description = "c"; g.add(child)

    g.build_index()
    from src.validator import _check_exhaustion
    tasks = _check_exhaustion(g)
    assert len(tasks) >= 1
    assert any("REVIEWER" in t.message for t in tasks)
    assert any(t.fresh_session for t in tasks)


def test_exhaustion_complete_no_tasks():
    """When verified AND reviewed, no exhaustion tasks fire."""
    g = Genome(".")
    parent = Node(); parent.name = "Parent"; parent.level = 0
    parent.expected_children = ["Child"]
    parent.children_verified = True
    parent.children_reviewed = True
    parent.description = "test"
    g.add(parent)

    child = Node(); child.name = "Child"; child.level = 1
    child.edges = {"parent": "Parent"}; child.description = "c"; g.add(child)

    g.build_index()
    from src.validator import _check_exhaustion
    tasks = _check_exhaustion(g)
    assert len(tasks) == 0


def test_task_debate_flag():
    t = Task("Discover personas", debate=True)
    assert t.debate is True
    t2 = Task("Fix bug")
    assert t2.debate is False


def test_task_fresh_session_flag():
    t = Task("Re-read spec", fresh_session=True)
    assert t.fresh_session is True
    t2 = Task("Normal task")
    assert t2.fresh_session is False


def test_loader_prunes_knowledge(tmp_path):
    plan = tmp_path / "plan"
    plan.mkdir()
    entries = ", ".join(f'"e{i}"' for i in range(20))
    (plan / "chatty.py").write_text(f'''
from genome5 import Node
class Chatty(Node):
    name = "Chatty"
    type = "test"
    description = "Lots of knowledge"
    knowledge = [{entries}]
''', encoding="utf-8")
    from src.loader import load_genome
    g = load_genome(str(tmp_path))
    assert len(g.get("Chatty").knowledge) == 8
