"""
Taskmaster Pro: State-of-the-Art Professional Agent built with Strands Agents SDK.

Target Track: Track 2 — Professional Agents.
Targets repetitive, judgment-heavy tasks for technical founders, engineering managers,
and solo product builders:
- PRD parsing into structured Jira epics & Fibonacci-estimated tasks
- Environment verification & smoke testing in Docker sandbox
- GitHub PR drafting and repository audit
- Stakeholder communication: executive briefs, Slack announcements, and client notification emails
- Governed execution via Human-in-the-Loop (HITL) approval gates
"""

import asyncio
import logging
import os
import re
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from strands import Agent
from strands.models.gemini import GeminiModel
from strands.multiagent.graph import Graph, GraphEdge, GraphNode

from agent.config import settings
from agent.memory.hybrid_graph_memory import hybrid_memory
from agent.strands_bridge.hitl_intervention import hitl_manager
from agent.strands_bridge.preflight_auditor import PreFlightAuditor
from agent.strands_bridge.tool_adapter import strands_tool_registry

logger = logging.getLogger("taskmaster.strands_bridge.agent")

PROFESSIONAL_SYSTEM_PROMPT = """You are Taskmaster Pro, an autonomous operational co-founder and engineering partner for technical professionals, makers, and teams.
Your purpose is to eliminate the repetitive, judgment-heavy operational choreography of software delivery:
1. Deconstruct complex product requirement documents (PRDs) or raw goals into structured, ordered engineering tasks with clear dependencies, priorities, and acceptance criteria.
2. Actively create, track, and manage real tasks on the system task board using the task_scheduler tool (action: create_task, list_tasks, update_task_status).
3. Set up automated background schedules, recurring intervals, and timers using task_scheduler (action: create_schedule, list_schedules).
4. Maintain persistent cross-session knowledge using memory_tool (Mem0/Letta architecture):
   - store entity nodes and directional relations in the entity graph (action: remember with source, relation, target)
   - traverse graph associations (action: query_graph)
   - recall past context ranked by temporal decay (action: recall)
   - update working memory blocks (action: update_block with block_label and block_content).
5. Navigate and extract web content using browser_controller with Stagehand natural language actions (observe, act, extract).
6. Verify code environments and execute calculations/tests safely using python_sandbox or docker_sandbox.
7. Synchronize project tracking with Jira and GitHub when external services are connected.
8. Maintain team transparency by drafting concise, actionable Slack updates and executive briefing reports.
9. Practice strict operational governance: whenever an action interacts with live external systems (creating public PRs, sending emails, or triggering webhooks), prepare the full payload and prompt for human review.
10. Cooperate with the Pre-Flight Auditor: When a pre-flight critique is issued on a proposed tool call, review the flagged policy and promptly revise your parameters or approach."""


class TaskmasterProAgent:
    """Production-grade Professional Agent powered by the Strands Agents SDK."""

    def __init__(
        self,
        model_id: Optional[str] = None,
        tools: Optional[List[Any]] = None,
        enable_hitl: bool = True,
        workflow_id: Optional[str] = None,
    ):
        self.workflow_id = workflow_id or str(uuid.uuid4())
        self.model_id = model_id or getattr(settings, "GEMINI_MODEL", "gemini-3.1-flash-lite")
        
        # Configure model provider
        api_key = getattr(settings, "GEMINI_API_KEY", None) or os.environ.get("GEMINI_API_KEY", "")
        client_args = {"api_key": api_key} if api_key else {}
        self.model = GeminiModel(model_id=self.model_id, client_args=client_args)

        # Configure tools
        self.tools = tools or strands_tool_registry.get_professional_tools()

        # Configure Multi-Agent Pre-Flight Auditor & Human-in-the-Loop Interventions
        self.interventions = []
        self.auditor = PreFlightAuditor()
        self.interventions.append(self.auditor)
        if enable_hitl:
            self.hitl_handler = hitl_manager.create_handler(self.workflow_id)
            self.interventions.append(self.hitl_handler)
        else:
            self.hitl_handler = None

        # Build dynamic system prompt with Letta/Mem0 working memory blocks
        try:
            working_mem = hybrid_memory.get_working_memory()
            mem_blocks = "\n".join([f"- [{k.upper()}]: {v}" for k, v in working_mem.items()]) if working_mem else ""
        except Exception:
            mem_blocks = ""

        sys_prompt = PROFESSIONAL_SYSTEM_PROMPT
        if mem_blocks:
            sys_prompt += f"\n\n## Persistent Core Working Memory (Letta/Mem0):\n{mem_blocks}"

        # Build Strands Agent
        self.agent = Agent(
            model=self.model,
            tools=self.tools,
            system_prompt=sys_prompt,
            interventions=self.interventions,
        )

    def run(self, prompt: str, max_retries: int = 3) -> Dict[str, Any]:
        """Execute a professional task synchronously and return structured results."""
        logger.info(f"Executing Taskmaster Pro workflow [{self.workflow_id}]: {prompt[:80]}...")
        for attempt in range(max_retries):
            try:
                result = self.agent(prompt)
                output_text = ""
                if hasattr(result, "message") and isinstance(result.message, dict):
                    content_blocks = result.message.get("content", [])
                    text_parts = [b.get("text", "") for b in content_blocks if isinstance(b, dict) and "text" in b]
                    output_text = "".join(text_parts).strip()
                if not output_text:
                    output_text = getattr(result, "output", str(result))

                stop_reason = getattr(result, "stop_reason", "completed")

                # Extract tool calls executed from agent message history
                tool_calls = []
                tool_results_by_id = {}
                for msg in getattr(self.agent, "messages", []):
                    content = msg.get("content", []) if isinstance(msg, dict) else getattr(msg, "content", [])
                    for block in content:
                        if isinstance(block, dict) and "toolResult" in block:
                            tr = block["toolResult"]
                            tool_results_by_id[tr.get("toolUseId")] = tr.get("content")

                for msg in getattr(self.agent, "messages", []):
                    content = msg.get("content", []) if isinstance(msg, dict) else getattr(msg, "content", [])
                    for block in content:
                        if isinstance(block, dict) and "toolUse" in block:
                            tu = block["toolUse"]
                            tool_calls.append({
                                "name": tu.get("name"),
                                "args": tu.get("input", {}),
                                "tool_use_id": tu.get("toolUseId"),
                                "result": tool_results_by_id.get(tu.get("toolUseId")),
                            })

                return {
                    "workflow_id": self.workflow_id,
                    "status": "COMPLETED" if stop_reason != "interrupt" else "INTERRUPTED",
                    "stop_reason": stop_reason,
                    "output": output_text,
                    "tool_calls": tool_calls,
                    "audit_summary": self.auditor.get_audit_summary(),
                    "pending_approvals": [
                        req.__dict__ for req in hitl_manager.get_pending(self.workflow_id)
                    ],
                }
            except Exception as e:
                err_str = str(e)
                is_rate_limit = any(term in err_str for term in ["429", "RESOURCE_EXHAUSTED", "Quota exceeded", "Too Many Requests"])
                if is_rate_limit and attempt < max_retries - 1:
                    wait_time = 30 * (attempt + 1)
                    match = re.search(r'retryDelay["\']?:\s*["\']?(\d+)', err_str)
                    if match:
                        wait_time = max(wait_time, int(match.group(1)) + 2)
                    logger.warning(f"Rate limit 429 encountered in workflow {self.workflow_id}. Backing off for {wait_time}s (attempt {attempt+1}/{max_retries})...")
                    time.sleep(wait_time)
                    continue

                logger.error(f"Error executing Strands agent workflow {self.workflow_id}: {e}", exc_info=True)
                return {
                    "workflow_id": self.workflow_id,
                    "status": "FAILED",
                    "error": str(e),
                    "output": "",
                }

    async def stream_events(self, prompt: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream agent execution events (tokens, tool call events, and interrupts)
        using Strands stream_async() for real-time SSE frontend delivery.
        """
        yield {
            "type": "workflow_started",
            "workflow_id": self.workflow_id,
            "goal": prompt,
        }

        try:
            async for event in self.agent.stream_async(prompt):
                # Format event payload for SSE consumption
                event_type = type(event).__name__
                payload = {
                    "type": "agent_stream_event",
                    "event_class": event_type,
                    "workflow_id": self.workflow_id,
                }
                
                # Check for token or content blocks
                if hasattr(event, "delta") and hasattr(event.delta, "text"):
                    payload["token"] = event.delta.text
                elif hasattr(event, "text"):
                    payload["token"] = event.text
                elif hasattr(event, "tool_use"):
                    payload["tool_call"] = {
                        "name": getattr(event.tool_use, "name", "tool"),
                        "input": getattr(event.tool_use, "input", {}),
                    }

                yield payload

            # Final check on pending approvals
            pending = hitl_manager.get_pending(self.workflow_id)
            if pending:
                yield {
                    "type": "hitl_interrupt",
                    "workflow_id": self.workflow_id,
                    "pending_approvals": [p.__dict__ for p in pending],
                }

            # Extract final message text from agent history
            output_text = ""
            for msg in reversed(getattr(self.agent, "messages", [])):
                content = msg.get("content", []) if isinstance(msg, dict) else getattr(msg, "content", [])
                text_parts = [b.get("text", "") for b in content if isinstance(b, dict) and "text" in b]
                if text_parts:
                    output_text = "".join(text_parts).strip()
                    break

            yield {
                "type": "workflow_completed",
                "workflow_id": self.workflow_id,
                "status": "COMPLETED",
                "summary": output_text,
                "output": output_text,
            }
        except Exception as e:
            logger.error(f"Error in Strands agent stream for {self.workflow_id}: {e}", exc_info=True)
            yield {
                "type": "workflow_failed",
                "workflow_id": self.workflow_id,
                "error": str(e),
            }


def build_professional_council_graph(workflow_id: Optional[str] = None) -> Graph:
    """
    Construct a Hierarchical Multi-Agent Council using strands.multiagent.graph.Graph.
    Coordinates 4 specialized agents in a deterministic topological pipeline:
    1. Spec & PRD Specialist -> 2. Engineering & QA -> 3. Operations & Jira -> 4. Communications
    """
    wid = workflow_id or str(uuid.uuid4())
    api_key = getattr(settings, "GEMINI_API_KEY", None) or os.environ.get("GEMINI_API_KEY", "")
    client_args = {"api_key": api_key} if api_key else {}
    model = GeminiModel(model_id=getattr(settings, "GEMINI_MODEL", "gemini-3.1-flash-lite"), client_args=client_args)

    # 1. Spec & PRD Specialist Agent
    spec_agent = Agent(
        model=model,
        tools=strands_tool_registry.get_tools(["data_extractor", "validator", "google_docs"]),
        system_prompt="You are the Spec & PRD Specialist. Analyze technical requirements, detect ambiguities, and structure clear acceptance criteria.",
    )
    spec_node = GraphNode(node_id="spec_specialist", executor=spec_agent)

    # 2. Engineering & QA Specialist Agent
    qa_agent = Agent(
        model=model,
        tools=strands_tool_registry.get_tools(["docker_sandbox", "validator", "browser_controller"]),
        system_prompt="You are the Engineering & QA Specialist. Inspect test coverage, execute smoke tests in Docker sandbox, and verify correctness.",
    )
    qa_node = GraphNode(node_id="engineering_qa", executor=qa_agent)

    # 3. Operations & Release Specialist Agent
    ops_agent = Agent(
        model=model,
        tools=strands_tool_registry.get_tools(["jira", "github", "db_manager"]),
        system_prompt="You are the Operations & Release Specialist. Synchronize sprint backlogs in Jira, draft GitHub PRs, and record audit records.",
    )
    ops_node = GraphNode(node_id="operations_release", executor=ops_agent)

    # 4. Communications Specialist Agent
    comms_agent = Agent(
        model=model,
        tools=strands_tool_registry.get_tools(["slack", "gmail", "report_generator"]),
        system_prompt="You are the Communications Specialist. Compose executive summaries, team Slack announcements, and client notification drafts.",
    )
    comms_node = GraphNode(node_id="comms_specialist", executor=comms_agent)

    # Connect nodes via GraphEdge dependencies
    edges = {
        GraphEdge(from_node=spec_node, to_node=qa_node),
        GraphEdge(from_node=qa_node, to_node=ops_node),
        GraphEdge(from_node=ops_node, to_node=comms_node),
    }

    nodes = {
        "spec_specialist": spec_node,
        "engineering_qa": qa_node,
        "operations_release": ops_node,
        "comms_specialist": comms_node,
    }

    graph = Graph(
        id=f"council_{wid}",
        nodes=nodes,
        edges=edges,
        entry_points={spec_node},
    )
    return graph
