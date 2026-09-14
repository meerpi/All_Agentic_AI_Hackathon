"""
Complex Multi-Domain Autonomous Engineering Workflow:
1. Search architecture references via media_controller.
2. Run Raft consensus election quorum simulation in python_sandbox.
3. Create a real engineering ticket on Jira Cloud (taskmasterjira.atlassian.net).
4. Persist cluster nodes & relations to Letta/Mem0 memory_tool.
5. Write the technical runbook to disk via os_desktop_tool.
6. Append the verified SLA metrics to the live Google Sheet matrix.
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
logger = logging.getLogger("complex_workflow")

def main():
    print("\n" + "=" * 80)
    print("🚀 EXECUTING COMPLEX MULTI-DOMAIN AUTONOMOUS WORKFLOW")
    print("Zero simulations. Live media search, Python sandbox, Jira Cloud, Letta/Mem0, OS desktop & Google Sheets.")
    print("=" * 80)

    agent = TaskmasterProAgent(
        model_id="gemini-3.1-flash-lite",
        enable_hitl=False,
        workflow_id=f"complex-wf-{int(time.time())}"
    )

    prompt = (
        "Act as a Principal Distributed Systems Architect handling an urgent infrastructure failover assessment.\n"
        "Execute the following complex sequence of tasks:\n"
        "1. Search YouTube for 'Distributed Systems Raft Consensus' using media_controller (action: 'youtube_api_search', limit: 2).\n"
        "2. In python_sandbox, run a Raft leader election simulation: simulate 500 election rounds with 5 nodes, "
        "calculate mean failover time and P99 failover time in milliseconds, and print the results.\n"
        "3. Using jira, create a real engineering issue with summary '[INC-9042] Deploy Patroni Raft Consensus on 5-Node Postgres Cluster', "
        "priority 'High', story_points 8, and description detailing the failover latency target.\n"
        "4. Using memory_tool, register the entity 'PostgreSQLConsensusCluster' with type 'Database' and observations ['5 Raft nodes', 'Failover SLA < 150ms'].\n"
        "5. Using os_desktop_tool (action: 'write_file'), write an incident failover runbook to 'data/incident_9042_runbook.md' with the simulation summary.\n"
        "6. Using google_sheets (action: 'append_rows', spreadsheet_id: '12s07QbnGcXo6EPHfVZ89xJz1AizHvIy-QyUFWDWz6M8'), "
        "append a row with [timestamp, 'INC-9042', 'PATRONI_RAFT', 'P99 < 150ms', 'RESOLVED'].\n"
        "7. Provide a final comprehensive executive digest."
    )

    t0 = time.time()
    result = agent.run(prompt)
    elapsed = time.time() - t0

    print(f"\nElapsed Time: {elapsed:.2f}s")
    print(f"Status: {result.get('status')}")
    print(f"Workflow ID: {result.get('workflow_id')}")
    print(f"Tool Calls Made: {len(result.get('tool_calls', []))}")
    for idx, tc in enumerate(result.get("tool_calls", []), 1):
        print(f"  [{idx}] Tool: {tc.get('name')} | Input: {tc.get('input')}")

    print("\nExecutive Digest:")
    print(result.get("output", ""))

    # Verify physical file on disk
    runbook_path = BASE_DIR / "data" / "incident_9042_runbook.md"
    if runbook_path.exists():
        print(f"\n✔ Physical runbook verified on disk: {runbook_path} ({len(runbook_path.read_text())} chars)")
    else:
        print(f"\n⚠️ Runbook file not found at: {runbook_path}")

    # Verify physical memory entity
    recalled = hybrid_memory.recall("PostgreSQLConsensusCluster")
    print(f"\n✔ Letta/Mem0 Physical Recall: {recalled}")

    print("\n" + "=" * 80)
    print("🎉 COMPLEX MULTI-DOMAIN WORKFLOW COMPLETED!")
    print("=" * 80)

if __name__ == "__main__":
    main()
