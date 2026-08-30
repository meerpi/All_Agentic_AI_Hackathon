from agent.a2a import (
    A2AServer,
    A2ATaskState,
    a2a_task_store,
    get_agent_card,
)


def test_agent_card_schema():
    card = get_agent_card("http://localhost:8000")
    assert card["name"] == "Taskmaster Autonomous Agent Council"
    assert card["protocol_version"] == "1.0"
    assert len(card["skills"]) >= 4
    skill_ids = [s["id"] for s in card["skills"]]
    assert "workflow_planning" in skill_ids
    assert "jira_sprint_management" in skill_ids


def test_task_lifecycle_store():
    task = a2a_task_store.create_task(skill_id="workflow_planning", parameters={"goal": "Test goal"})
    assert task.state == A2ATaskState.SUBMITTED

    a2a_task_store.update_state(task.task_id, A2ATaskState.WORKING)
    assert a2a_task_store.get_task(task.task_id).state == A2ATaskState.WORKING

    a2a_task_store.add_artifact(task.task_id, "test_art", {"status": "ok"})
    assert len(a2a_task_store.get_task(task.task_id).artifacts) == 1

    a2a_task_store.update_state(task.task_id, A2ATaskState.COMPLETED)
    assert a2a_task_store.get_task(task.task_id).state == A2ATaskState.COMPLETED


def test_jsonrpc_skills_list():
    server = A2AServer()
    req = {
        "jsonrpc": "2.0",
        "method": "skills/list",
        "id": "req-1",
    }
    resp = server.handle_jsonrpc(req)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == "req-1"
    assert "result" in resp
    assert len(resp["result"]["skills"]) >= 4


def test_jsonrpc_task_send_and_get():
    server = A2AServer()
    send_req = {
        "jsonrpc": "2.0",
        "method": "tasks/send",
        "params": {
            "skill_id": "prd_decomposition",
            "parameters": {
                "prd_content": "- Build backend API\n- Create Jira issues",
            },
        },
        "id": "req-2",
    }
    send_resp = server.handle_jsonrpc(send_req)
    assert send_resp["jsonrpc"] == "2.0"
    task_data = send_resp["result"]
    assert task_data["state"] in ("completed", "working")

    # Fetch task via get
    get_req = {
        "jsonrpc": "2.0",
        "method": "tasks/get",
        "params": {"task_id": task_data["task_id"]},
        "id": "req-3",
    }
    get_resp = server.handle_jsonrpc(get_req)
    assert get_resp["result"]["task_id"] == task_data["task_id"]
