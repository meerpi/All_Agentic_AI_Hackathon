from agent.memory import MemoryManager
from agent.prd_parser import PRDParser
from agent.task_expansion import TaskExpansionEngine
from agent.models import PlanStep
from agent.time_travel import time_travel
from agent.persistence import persistence
from agent.evals import TrajectoryEvaluator


def test_persistent_memory():
    mem = MemoryManager()
    mem.semantic.store("coding_language", "Python", category="preferences")
    val = mem.semantic.recall("coding_language", category="preferences")
    assert val == "Python"

    mem.episodic.record("TEST_EVENT", "wf-123", {"action": "sync"})
    results = mem.episodic.search("TEST_EVENT")
    assert len(results) >= 1


def test_prd_parser_heuristic():
    parser = PRDParser(None)
    prd_text = """
    # Patient Dashboard PRD
    - Set up PostgreSQL schema
    - Build FastAPI authentication endpoints
    - Deploy React frontend to Cloud Run
    """
    res = parser.parse(prd_text)
    assert len(res["tasks"]) >= 3
    assert res["tasks"][0].description == "Set up PostgreSQL schema"


def test_task_expansion():
    engine = TaskExpansionEngine(None)
    parent = PlanStep(
        step_number=1,
        description="Deploy patient analytics infrastructure",
        tool_name="docker_sandbox",
        reasoning="Core setup",
    )
    subtasks = engine.expand_step(parent, num_subtasks=3)
    assert len(subtasks) == 3
    assert subtasks[0].step_number == 101
    assert subtasks[1].step_number == 102
    assert subtasks[2].step_number == 103


def test_trajectory_evaluator_deterministic():
    from agent.models import WorkflowPlan, StepStatus
    wf = WorkflowPlan(
        goal="Test Goal",
        steps=[
            PlanStep(step_number=1, description="s1", tool_name="gmail", reasoning="r", status=StepStatus.COMPLETED),
            PlanStep(step_number=2, description="s2", tool_name="jira", reasoning="r", status=StepStatus.COMPLETED),
        ],
        final_artifact={"status": "done"},
    )
    evaluator = TrajectoryEvaluator(None)
    report = evaluator.evaluate_workflow(wf)
    assert report.passed is True
    assert report.overall_score >= 75.0
    assert report.plan_adherence.score == 100.0
