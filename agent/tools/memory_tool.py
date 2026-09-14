"""
Hybrid Graph & Working Memory Tool for Taskmaster and Strands Agents SDK.

Exposes Letta/Mem0 hybrid memory architecture to the agent:
- Entity Knowledge Graph (nodes and relational edges in SQLite)
- Core Working Memory Blocks (human, persona, system_state)
- Associative Recall with Exponential Temporal Decay Scoring
"""

import logging
from typing import Any, Dict, List, Optional
from agent.memory.hybrid_graph_memory import hybrid_memory
from agent.tools.base import BaseTool

logger = logging.getLogger("taskmaster.tools.memory")


class MemoryTool(BaseTool):
    name = "memory_tool"
    description = (
        "Hybrid Graph & Working Memory Manager (Mem0/Letta architecture). "
        "Allows the agent to maintain cross-session working memory blocks (human, persona, system_state), "
        "store entity knowledge nodes and relational edges in a persistent graph, traverse graph connections, "
        "and perform associative recall ranked by temporal decay and access frequency. "
        "Actions: 'remember', 'recall', 'query_graph', 'update_block', 'get_working_memory'."
    )

    def run(
        self,
        action: str = "recall",
        query: Optional[str] = None,
        entity_name: Optional[str] = None,
        entity_type: str = "concept",
        attributes: Optional[Dict[str, Any]] = None,
        source: Optional[str] = None,
        relation: Optional[str] = None,
        target: Optional[str] = None,
        relation_weight: float = 1.0,
        relation_metadata: Optional[Dict[str, Any]] = None,
        block_label: Optional[str] = None,
        block_content: Optional[str] = None,
        limit: int = 10,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        act = (action or "recall").lower().strip()
        if act in ("add_entity", "create_entity", "add_relation", "create_relation"):
            act = "remember"

        try:
            if act == "remember":
                # If source, relation, and target are provided, create directed relation
                res = {}
                src = source or kwargs.get("source_entity")
                rel = relation or kwargs.get("rel")
                tgt = target or kwargs.get("target_entity")
                if src and rel and tgt:
                    rel_res = hybrid_memory.add_relation(
                        source=src,
                        relation=rel,
                        target=tgt,
                        weight=relation_weight,
                        metadata=relation_metadata or kwargs.get("metadata"),
                    )
                    res["relation"] = rel_res

                # Also remember entity if entity_name provided
                target_entity = entity_name or kwargs.get("name") or src
                if target_entity:
                    ent_res = hybrid_memory.remember_entity(
                        name=target_entity,
                        entity_type=entity_type or kwargs.get("type", "concept"),
                        attributes=attributes or kwargs.get("observations"),
                    )
                    res["entity"] = ent_res

                if not res:
                    return {
                        "status": "FAILED",
                        "error": "Action 'remember' requires 'entity_name' or ('source', 'relation', 'target').",
                    }
                return {"status": "SUCCESS", "action": "remember", **res}

            elif act == "recall":
                q = query or entity_name or kwargs.get("text", "")
                results = hybrid_memory.recall(query=q, limit=limit)
                return {
                    "status": "SUCCESS",
                    "action": "recall",
                    "query": q,
                    "count": len(results),
                    "results": results,
                }

            elif act == "query_graph":
                target_ent = entity_name or source or query or kwargs.get("name")
                if not target_ent:
                    return {
                        "status": "FAILED",
                        "error": "Action 'query_graph' requires 'entity_name'.",
                    }
                graph_data = hybrid_memory.query_graph(entity_name=target_ent)
                return {
                    "status": "SUCCESS",
                    "action": "query_graph",
                    "data": graph_data,
                }

            elif act == "update_block":
                lbl = block_label or kwargs.get("block_name") or kwargs.get("label") or kwargs.get("name")
                cnt = block_content or kwargs.get("value") or kwargs.get("content") or kwargs.get("text")
                if not lbl or cnt is None:
                    return {
                        "status": "FAILED",
                        "error": "Action 'update_block' requires 'block_label' (or 'block_name') and 'block_content' (or 'value').",
                    }
                up_res = hybrid_memory.update_block(label=lbl, content=str(cnt))
                return {
                    "status": "SUCCESS",
                    "action": "update_block",
                    "block": up_res,
                }

            elif act in ("get_working_memory", "get_blocks"):
                blocks = hybrid_memory.get_working_memory()
                return {
                    "status": "SUCCESS",
                    "action": "get_working_memory",
                    "blocks": blocks,
                }

            else:
                return {
                    "status": "FAILED",
                    "error": f"Unknown memory action '{action}'. Valid actions: remember, recall, query_graph, update_block, get_working_memory.",
                }

        except Exception as e:
            logger.error(f"Error executing memory_tool action '{action}': {e}", exc_info=True)
            return {"status": "FAILED", "error": str(e)}
