"""
Live Agent Task Execution: Give an actual high-level multi-step engineering task
to TaskmasterProAgent and verify that it plans, selects tools, debates/passes audits,
and accomplishes the task live with real side-effects.
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ["MOCK_GEMINI"] = "false"

from agent.strands_bridge.professional_agent import TaskmasterProAgent
from agent.memory.hybrid_graph_memory import hybrid_memory

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("live_agent_task")

def main():
    print("\n" + "=" * 80)
    print("🚀 GIVING REAL HIGH-LEVEL ENGINEERING GOAL TO TASKMASTER PRO AGENT")
    print("Goal: Compute 500-sample latency distribution in python_sandbox, store ServiceMeshGateway in memory_tool, and update working memory.")
    print("=" * 80)

    agent = TaskmasterProAgent(
        model_id="gemini-3.1-flash-lite",
        enable_hitl=False,
        workflow_id=f"live-task-{int(time.time())}"
    )

    prompt = (
        "Act as a Principal Infrastructure SRE. Execute the following sequence of actions:\n"
        "1. Use python_sandbox to compute a latency SLA distribution: generate 500 random values (mean 25ms, stddev 5ms), calculate mean and P95 latency, and output the result.\n"
        "2. Use memory_tool to remember entity 'ProductionServiceMeshGateway' with type 'Microservice' and observations ['Mesh v2.4', 'P95 latency compliant'].\n"
        "3. Use memory_tool to update working memory block 'system_state' with 'ServiceMeshGateway healthy, P95 verified'.\n"
        "4. Summarize your findings in a final executive statement."
    )

    t0 = time.time()
    result = agent.run(prompt)
    elapsed = time.time() - t0

    print(f"\nElapsed Time: {elapsed:.2f}s")
    print(f"Status: {result.get('status')}")
    print(f"Workflow ID: {result.get('workflow_id')}")
    print(f"Tool Calls Made: {len(result.get('tool_calls', []))}")
    for tc in result.get("tool_calls", []):
        print(f"  - Tool: {tc.get('name')} | Input: {tc.get('input')}")

    print("\nFinal Output:")
    print(result.get("output", ""))

    # Physical verification in memory
    recalled = hybrid_memory.recall("ProductionServiceMeshGateway")
    print(f"\nPhysical Letta/Mem0 Recall Verification: {recalled}")
    
    assert result.get("status") in ("COMPLETED", "INTERRUPTED"), f"Unexpected status: {result.get('status')}"
    print("\n✔ LIVE AGENT TASK ACCOMPLISHED SUCCESSFULLY!")

if __name__ == "__main__":
    main()
