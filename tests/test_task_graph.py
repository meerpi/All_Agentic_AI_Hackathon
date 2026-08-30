import pytest
from agent.models import PlanStep, StepStatus
from agent.task_graph import (
    CyclicDependencyError,
    MissingDependencyError,
    TaskDAG,
)


def test_topological_sort_linear():
    steps = [
        PlanStep(step_number=1, description="Step 1", tool_name="tool_a", reasoning="r"),
        PlanStep(step_number=2, description="Step 2", tool_name="tool_b", reasoning="r", depends_on=[1]),
        PlanStep(step_number=3, description="Step 3", tool_name="tool_c", reasoning="r", depends_on=[2]),
    ]
    dag = TaskDAG(steps)
    order = dag.topological_sort()
    assert order == [1, 2, 3]


def test_topological_sort_branching():
    # 1 -> 2, 1 -> 3, 2 -> 4, 3 -> 4
    steps = [
        PlanStep(step_number=1, description="Root", tool_name="t", reasoning="r"),
        PlanStep(step_number=2, description="Branch A", tool_name="t", reasoning="r", depends_on=[1]),
        PlanStep(step_number=3, description="Branch B", tool_name="t", reasoning="r", depends_on=[1]),
        PlanStep(step_number=4, description="Join", tool_name="t", reasoning="r", depends_on=[2, 3]),
    ]
    dag = TaskDAG(steps)
    order = dag.topological_sort()
    assert order[0] == 1
    assert order[-1] == 4
    assert set(order[1:3]) == {2, 3}


def test_cycle_detection():
    # 1 -> 2, 2 -> 3, 3 -> 1
    steps = [
        PlanStep(step_number=1, description="A", tool_name="t", reasoning="r", depends_on=[3]),
        PlanStep(step_number=2, description="B", tool_name="t", reasoning="r", depends_on=[1]),
        PlanStep(step_number=3, description="C", tool_name="t", reasoning="r", depends_on=[2]),
    ]
    dag = TaskDAG(steps)
    cycle = dag.detect_cycles()
    assert cycle is not None
    assert set(cycle) == {1, 2, 3}
    with pytest.raises(CyclicDependencyError):
        dag.topological_sort()


def test_missing_dependency():
    steps = [
        PlanStep(step_number=1, description="A", tool_name="t", reasoning="r", depends_on=[99]),
    ]
    with pytest.raises(MissingDependencyError):
        TaskDAG(steps)


def test_parallel_groups():
    steps = [
        PlanStep(step_number=1, description="A", tool_name="t", reasoning="r"),
        PlanStep(step_number=2, description="B", tool_name="t", reasoning="r"),
        PlanStep(step_number=3, description="C", tool_name="t", reasoning="r", depends_on=[1, 2]),
    ]
    dag = TaskDAG(steps)
    groups = dag.get_parallel_groups()
    assert groups[0] == [1, 2]
    assert groups[1] == [3]


def test_critical_path():
    steps = [
        PlanStep(step_number=1, description="A", tool_name="t", reasoning="r"),
        PlanStep(step_number=2, description="B", tool_name="t", reasoning="r", depends_on=[1]),
        PlanStep(step_number=3, description="C", tool_name="t", reasoning="r", depends_on=[2]),
        PlanStep(step_number=4, description="D", tool_name="t", reasoning="r", depends_on=[1]),
    ]
    dag = TaskDAG(steps)
    cp = dag.get_critical_path()
    assert cp == [1, 2, 3]  # Length 3 path is longer than 1 -> 4 (length 2)
