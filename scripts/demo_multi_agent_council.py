"""
Test script for the Hierarchical Multi-Agent Council.
Tests all 5 specialized sub-agents, A2A communication, and live Workspace + Jira Cloud generation.
"""

from agent.multi_agent import MultiAgentCouncilOrchestrator

def test_council():
    print("🚀 Initializing Hierarchical Multi-Agent Council...\n")
    orchestrator = MultiAgentCouncilOrchestrator()

    transcript_sample = (
        "Meeting Transcript: Multi-Agent Cloud Architecture & Security Review\n"
        "Attendees: Anima (Lead), Alex Chen (Frontend), Priya Patel (Backend), Marcus Vance (Security), David Kim (Product)\n"
        "Date: August 30, 2026\n\n"
        "David: Team, let's lock in our sprint deliverables.\n"
        "First, Alex, build the WebSocket streaming UI for our multi-agent council chat. High priority, 5 story points.\n"
        "Second, Priya, optimize Firestore database indexes for inter-agent message querying. Critical priority, 8 story points.\n"
        "Third, Marcus, enforce TLS 1.3 encryption on all webhook endpoints for SOC2 audit compliance. Medium priority, 3 story points."
    )

    goal = "Execute Sprint Planning & Security Review with Multi-Agent Council: extract tasks, provision Jira Cloud tickets, author Google Doc Minutes, populate Google Sheets Backlog, and audit deliverables."

    result = orchestrator.execute_council(
        goal=goal,
        context={"transcript": transcript_sample, "meeting_title": "Sprint 43 Cloud Architecture Review"}
    )

    print(f"\n==========================================")
    print(f"Council Execution Status: {result.status}")
    print(f"Total Execution Time: {result.total_execution_time_ms} ms")
    print(f"Total Sub-Agent Responses: {len(result.subagent_responses)}")
    print(f"Total Council Dialogue Events: {len(result.council_dialogue)}")
    print(f"==========================================\n")

    print("--- 🏛️ Live Council Inter-Agent Dialogue Stream ---")
    for event in result.council_dialogue:
        print(f"[{event.timestamp[11:19]}] 👤 {event.sender} ({event.sender_role}) ➔ {event.recipient}:")
        print(f"    💬 \"{event.message}\"")
        if event.artifacts_attached:
            print(f"    📦 Attached: {[a.get('type') for a in event.artifacts_attached]}")
        print()

    print("\n--- 👥 Specialized Sub-Agent Execution Summaries ---")
    for resp in result.subagent_responses:
        print(f"\n[{resp.role.value}] {resp.agent_name} -> {resp.status} ({resp.execution_time_ms}ms)")
        print(f"  Reasoning: {resp.reasoning}")
        print(f"  Tool calls: {len(resp.tool_calls_executed)}")

    print("\n--- 📄 Executive Summary ---")
    print(result.executive_summary)

if __name__ == "__main__":
    test_council()
