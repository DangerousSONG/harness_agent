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
    SKILL_MEMORY,
    BG,
    TASK_MGR,
    TEAM,
    BUS,
    handle_shutdown_request,
    handle_plan_review,
    EVOLUTION_GATE=None,
    classify_learning_signal_for_tool=None,
):
    def load_skill(**kw):
        name = kw["name"]
        result = SKILLS.load(name)
        if not result.startswith("Error:"):
            SKILL_MEMORY.set_active_skill(name)
        return result

    def record_learning(**kw):
        return SKILL_MEMORY.record_learning(
            kw.get("skill_name", ""),
            kw["title"],
            kw["content"],
            evidence=kw.get("evidence", ""),
            source=kw.get("source", "manual"),
            domain=kw.get("domain", "learning"),
            priority=kw.get("priority", "medium"),
            source_skill=kw.get("source_skill", "self_improvement"),
            attribution_reason=kw.get("attribution_reason", ""),
            attribution_confidence=kw.get("attribution_confidence", ""),
            needs_attribution_review=kw.get("needs_attribution_review"),
        )

    def record_error(**kw):
        return SKILL_MEMORY.record_error(
            kw.get("skill_name", ""),
            kw["title"],
            kw["content"],
            command=kw.get("command", ""),
            traceback=kw.get("traceback", ""),
            source=kw.get("source", "manual"),
            domain=kw.get("domain", "error"),
            priority=kw.get("priority", "high"),
            source_skill=kw.get("source_skill", "self_improvement"),
            attribution_reason=kw.get("attribution_reason", ""),
            attribution_confidence=kw.get("attribution_confidence", ""),
            needs_attribution_review=kw.get("needs_attribution_review"),
        )

    def record_feature_request(**kw):
        return SKILL_MEMORY.record_feature_request(
            kw.get("skill_name", ""),
            kw["title"],
            kw["content"],
            source=kw.get("source", "manual"),
            domain=kw.get("domain", "feature_request"),
            priority=kw.get("priority", "medium"),
            source_skill=kw.get("source_skill", "self_improvement"),
            attribution_reason=kw.get("attribution_reason", ""),
            attribution_confidence=kw.get("attribution_confidence", ""),
            needs_attribution_review=kw.get("needs_attribution_review"),
        )

    def record_policy_candidate(**kw):
        return SKILL_MEMORY.record_policy_candidate(
            kw.get("skill_name", ""),
            kw["title"],
            kw["content"],
            risk_type=kw.get("risk_type", ""),
            severity=kw.get("severity", ""),
            source=kw.get("source", "manual"),
            priority=kw.get("priority", "medium"),
            source_skill=kw.get("source_skill", "self_improvement"),
            attribution_reason=kw.get("attribution_reason", ""),
            attribution_confidence=kw.get("attribution_confidence", ""),
            needs_attribution_review=kw.get("needs_attribution_review"),
        )

    def record_regression_test(**kw):
        return SKILL_MEMORY.record_regression_test(
            kw.get("skill_name", ""),
            kw["title"],
            kw["content"],
            domain=kw.get("domain", "regression_test"),
            priority=kw.get("priority", "medium"),
            source_skill=kw.get("source_skill", "self_improvement"),
            attribution_reason=kw.get("attribution_reason", ""),
            attribution_confidence=kw.get("attribution_confidence", ""),
            needs_attribution_review=kw.get("needs_attribution_review"),
        )

    return {
        "bash":             lambda **kw: run_bash(kw["command"]),
        "read_file":        lambda **kw: run_read(kw["path"], kw.get("limit")),
        "write_file":       lambda **kw: run_write(kw["path"], kw["content"]),
        "edit_file":        lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),

        "TodoWrite":        lambda **kw: TODO.update(kw["items"]),
        "task":             lambda **kw: run_subagent(kw["prompt"], kw.get("agent_type", "Explore")),
        "load_skill":       load_skill,
        "record_learning":  record_learning,
        "record_error":     record_error,
        "record_feature_request": lambda **kw: record_feature_request(**kw),
        "record_policy_candidate": lambda **kw: record_policy_candidate(**kw),
        "record_regression_test": lambda **kw: record_regression_test(**kw),
        "propose_memory_promotion": lambda **kw: SKILL_MEMORY.propose_memory_promotion(
            kw["skill_name"],
            kw["record_id"],
        ),
        "evaluate_evolution_candidate": lambda **kw: json.dumps(
            EVOLUTION_GATE.evaluate_candidate_id(kw["candidate_id"]).to_dict()
            if EVOLUTION_GATE
            else {
                "decision": "reject",
                "reason": "EvolutionGate is not configured.",
            },
            indent=2,
            ensure_ascii=False,
        ),
        "classify_learning_signal": lambda **kw: (
            classify_learning_signal_for_tool(**kw)
            if classify_learning_signal_for_tool
            else SKILL_MEMORY.classify_learning_signal(
                kw.get("raw_content", ""),
                signal_type=kw.get("signal_type", ""),
                source=kw.get("source", "manual"),
                candidate_skill=kw.get("candidate_skill", ""),
                confidence=kw.get("confidence", "medium"),
            )
        ),
        "summarize_skill_memory": lambda **kw: SKILL_MEMORY.summarize_memory(kw["skill_name"]),
        "list_skill_memory": lambda **kw: SKILL_MEMORY.list_memory(kw["skill_name"]),
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
