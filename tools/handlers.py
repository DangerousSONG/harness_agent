# tools/handlers.py

import json


def build_tool_handlers(
    *,
    run_bash,
    run_read,
    run_write,
    run_edit,
    TODO,
    run_subagent,
    SKILLS,
    BG,
    TASK_MGR,
    TEAM,
    BUS,
    handle_shutdown_request,
    handle_plan_review,
):
    return {
        "bash":             lambda **kw: run_bash(kw["command"]),
        "read_file":        lambda **kw: run_read(kw["path"], kw.get("limit")),
        "write_file":       lambda **kw: run_write(kw["path"], kw["content"]),
        "edit_file":        lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),

        "TodoWrite":        lambda **kw: TODO.update(kw["items"]),
        "task":             lambda **kw: run_subagent(kw["prompt"], kw.get("agent_type", "Explore")),
        "load_skill":       lambda **kw: SKILLS.load(kw["name"]),
        "compress":         lambda **kw: "Compressing...",

        "background_run":   lambda **kw: BG.run(kw["command"], kw.get("timeout", 120)),
        "check_background": lambda **kw: BG.check(kw.get("task_id")),

        "task_create":      lambda **kw: TASK_MGR.create(
            kw["subject"],
            kw.get("description", "")
        ),
        "task_get":         lambda **kw: TASK_MGR.get(kw["task_id"]),
        "task_update":      lambda **kw: TASK_MGR.update(
            kw["task_id"],
            kw.get("status"),
            kw.get("add_blocked_by"),
            kw.get("remove_blocked_by")
        ),
        "task_list":        lambda **kw: TASK_MGR.list_all(),
        "claim_task":       lambda **kw: TASK_MGR.claim(kw["task_id"], "lead"),

        "spawn_teammate":   lambda **kw: TEAM.spawn(
            kw["name"],
            kw["role"],
            kw["prompt"]
        ),
        "list_teammates":   lambda **kw: TEAM.list_all(),

        "send_message":     lambda **kw: BUS.send(
            "lead",
            kw["to"],
            kw["content"],
            kw.get("msg_type", "message")
        ),
        "read_inbox":       lambda **kw: json.dumps(
            BUS.read_inbox("lead"),
            indent=2,
            ensure_ascii=False
        ),
        "broadcast":        lambda **kw: BUS.broadcast(
            "lead",
            kw["content"],
            TEAM.member_names()
        ),

        "shutdown_request": lambda **kw: handle_shutdown_request(kw["teammate"]),
        "plan_approval":    lambda **kw: handle_plan_review(
            kw["request_id"],
            kw["approve"],
            kw.get("feedback", "")
        ),

        "idle":             lambda **kw: "Lead does not idle.",
    }