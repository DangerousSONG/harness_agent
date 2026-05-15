#!/usr/bin/env python3
# Harness: all mechanisms combined -- the complete cockpit for the model.
"""
s_full.py - Full Reference Agent

Capstone implementation combining every mechanism from s01-s11.
Session s12 (task-aware worktree isolation) is taught separately.
NOT a teaching session -- this is the "put it all together" reference.

    +------------------------------------------------------------------+
    |                        FULL AGENT                                 |
    |                                                                   |
    |  System prompt (s05 skills, task-first + optional todo nag)      |
    |                                                                   |
    |  Before each LLM call:                                            |
    |  +--------------------+  +------------------+  +--------------+  |
    |  | Microcompact (s06) |  | Drain bg (s08)   |  | Check inbox  |  |
    |  | Auto-compact (s06) |  | notifications    |  | (s09)        |  |
    |  +--------------------+  +------------------+  +--------------+  |
    |                                                                   |
    |  Tool dispatch (s02 pattern):                                     |
    |  +--------+----------+----------+---------+-----------+          |
    |  | bash   | read     | write    | edit    | TodoWrite |          |
    |  | task   | load_sk  | compress | bg_run  | bg_check  |          |
    |  | t_crt  | t_get    | t_upd    | t_list  | spawn_tm  |          |
    |  | list_tm| send_msg | rd_inbox | bcast   | shutdown  |          |
    |  | plan   | idle     | claim    |         |           |          |
    |  +--------+----------+----------+---------+-----------+          |
    |                                                                   |
    |  Subagent (s04):  spawn -> work -> return summary                 |
    |  Teammate (s09):  spawn -> work -> idle -> auto-claim (s11)      |
    |  Shutdown (s10):  request_id handshake                            |
    |  Plan gate (s10): submit -> approve/reject                        |
    +------------------------------------------------------------------+

    REPL commands: /compact /tasks /team /inbox
"""

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from openai import OpenAI
from dotenv import load_dotenv
from tools import (
    build_tools,
    build_tool_handlers,
    run_bash,
    run_read,
    run_write,
    run_edit,
)
from runtime import (
    EvolutionGate,
    LocalBackend,
    PromotionBrowser,
    SkillEvolutionRegistry,
    SkillLoader,
    SkillMemoryManager,
    classify_and_record_learning_signal,
    classify_learning_signal,
    evolve_skill_from_promotion,
    format_promotion_detail,
    format_promotion_list,
    format_skill_version_detail,
    format_skill_versions,
    propose_regression_case_from_promotion,
    propose_skill_patch_from_promotion,
)
from safety import AuditLogger, PolicyEngine, capabilities_for_actor, load_policy
from harness.todos import TodoManager
from harness.subagent import run_subagent
from harness.compression import estimate_tokens, microcompact, auto_compact
from harness.file_tasks import TaskManager
from harness.background import BackgroundManager
from harness.messaging import MessageBus
from harness.team import TeammateManager
from harness.prompt import build_system_prompt
from harness.loop import agent_loop


load_dotenv(PROJECT_ROOT / ".env", override=True)

client = OpenAI(
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.getenv("OPENAI_BASE_URL"),
)

MODEL = os.environ["MODEL_ID"]

'''
PROJECT_ROOT = 项目根目录
WORKDIR = Agent 执行工作目录，也指向项目根目录
TEAM_DIR = 队友状态目录
INBOX_DIR = 队友消息目录
TASKS_DIR = 持久任务目录
SKILLS_DIR = 技能目录
TRANSCRIPT_DIR = 压缩转录目录
'''
WORKDIR = PROJECT_ROOT

SKILLS_DIR = PROJECT_ROOT / "skills"
GLOBAL_SKILL_MEMORY_DIR = PROJECT_ROOT / ".skills_memory"
TRANSCRIPT_DIR = PROJECT_ROOT / ".transcripts"
TOKEN_THRESHOLD = 100000
POLL_INTERVAL = 5
IDLE_TIMEOUT = 60

VALID_MSG_TYPES = {"message", "broadcast", "shutdown_request",
                   "shutdown_response", "plan_approval_response"}


# === SECTION: global_instances ===
TODO = TodoManager()
SKILLS = SkillLoader(SKILLS_DIR)
SKILL_MEMORY = SkillMemoryManager(SKILLS_DIR, GLOBAL_SKILL_MEMORY_DIR)
SKILL_EVOLUTION = SkillEvolutionRegistry(PROJECT_ROOT)
BACKEND = LocalBackend(
    PROJECT_ROOT,
    WORKDIR,
    skill_loader=SKILLS,
    skill_memory=SKILL_MEMORY,
)
POLICY_CONFIG = load_policy()
POLICY = PolicyEngine(policy=POLICY_CONFIG)
print(f"[SafeHarness] policy={POLICY.policy.get('policy_name', 'unknown')}")
AUDIT_CONFIG = POLICY.policy.get("audit", {})
AUDIT_PATH = PROJECT_ROOT / AUDIT_CONFIG.get("path", ".audit/events.jsonl")
AUDIT = AuditLogger(
    AUDIT_PATH,
    enabled=bool(AUDIT_CONFIG.get("enabled", True)),
    redact_secrets=bool(AUDIT_CONFIG.get("redact_secrets", True)),
    max_payload_chars=int(AUDIT_CONFIG.get("max_payload_chars", 1000)),
)
EVOLUTION_GATE = EvolutionGate(
    audit_path=PROJECT_ROOT / ".audit" / "evolution.jsonl",
    promotion_candidates_path=GLOBAL_SKILL_MEMORY_DIR / "PROMOTION_CANDIDATES.md",
)
PROMOTIONS = PromotionBrowser(
    skills_dir=SKILLS_DIR,
    global_memory_dir=GLOBAL_SKILL_MEMORY_DIR,
    project_root=PROJECT_ROOT,
)
TASK_MGR = TaskManager(BACKEND.task_store)
BG = BackgroundManager(BACKEND.job_queue)
BUS = MessageBus(BACKEND.message_store)
TEAM = TeammateManager(
    bus=BUS,
    task_mgr=TASK_MGR,
    runner=BACKEND.agent_runner,
    workdir=WORKDIR,
    client=client,
    model=MODEL,
    run_bash=lambda command: run_bash(WORKDIR, command),
    run_read=lambda path: run_read(WORKDIR, path),
    run_write=lambda path, content: run_write(WORKDIR, path, content),
    run_edit=lambda path, old_text, new_text: run_edit(
        WORKDIR,
        path,
        old_text,
        new_text,
    ),
    idle_timeout=IDLE_TIMEOUT,
    poll_interval=POLL_INTERVAL,
)

# === SECTION: system_prompt ===
SYSTEM = build_system_prompt(WORKDIR, SKILLS)


# === SECTION: shutdown_protocol (s10) ===
def handle_shutdown_request(teammate: str) -> str:
    req_id = BACKEND.review_store.create_shutdown_request(teammate)
    BUS.send("lead", teammate, "Please shut down.", "shutdown_request", {"request_id": req_id})
    return f"Shutdown request {req_id} sent to '{teammate}'"

# === SECTION: plan_approval (s10) ===
def handle_plan_review(request_id: str, approve: bool, feedback: str = "") -> str:
    req = BACKEND.review_store.get_plan_request(request_id)
    if not req: return f"Error: Unknown plan request_id '{request_id}'"
    BACKEND.review_store.set_plan_status(request_id, "approved" if approve else "rejected")
    BUS.send("lead", req["from"], feedback, "plan_approval_response",
             {"request_id": request_id, "approve": approve, "feedback": feedback})
    return f"Plan {'approved' if approve else 'rejected'} for '{req['from']}'"


# === SECTION: tool_dispatch (s02) ===
TOOLS = build_tools(list(VALID_MSG_TYPES))


def classify_learning_signal_for_tool(**kw) -> str:
    conversation_context = kw.get("conversation_context")
    latest_tool_events = kw.get("latest_tool_events")
    latest_llm_messages = kw.get("latest_llm_messages")
    if conversation_context is None:
        conversation_context = [{"role": "user", "content": kw.get("raw_content", "")}]
    if latest_tool_events is None:
        latest_tool_events = []
    if latest_llm_messages is None:
        latest_llm_messages = []
    result = classify_learning_signal(
        client=client,
        model=MODEL,
        conversation_context=conversation_context,
        latest_tool_events=latest_tool_events,
        latest_llm_messages=latest_llm_messages,
    )
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)


def classify_and_record_learning_signal_for_tool(**kw) -> str:
    result = classify_and_record_learning_signal(
        client=client,
        model=MODEL,
        skill_memory=SKILL_MEMORY,
        raw_content=kw.get("raw_content", ""),
        conversation_context=kw.get("conversation_context") or [],
        latest_tool_events=kw.get("latest_tool_events") or [],
        latest_llm_messages=kw.get("latest_llm_messages") or [],
        explicit_skill_name=kw.get("skill_name", ""),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


TOOL_HANDLERS = build_tool_handlers(
    run_bash=lambda command: run_bash(WORKDIR, command),
    run_read=lambda path, limit=None: run_read(WORKDIR, path, limit),
    run_write=lambda path, content: run_write(WORKDIR, path, content),
    run_edit=lambda path, old_text, new_text: run_edit(WORKDIR, path, old_text, new_text),

    TODO=TODO,

    run_subagent=lambda prompt, agent_type="Explore": run_subagent(
    prompt=prompt,
    agent_type=agent_type,
    client=client,
    model=MODEL,
    run_bash=lambda command: run_bash(WORKDIR, command),
    run_read=lambda path: run_read(WORKDIR, path),
    run_write=lambda path, content: run_write(WORKDIR, path, content),
    run_edit=lambda path, old_text, new_text: run_edit(
        WORKDIR,
        path,
        old_text,
        new_text,
    ),
),

    SKILLS=SKILLS,
    SKILL_MEMORY=SKILL_MEMORY,
    BG=BG,
    TASK_MGR=TASK_MGR,
    TEAM=TEAM,
    BUS=BUS,
    handle_shutdown_request=handle_shutdown_request,
    handle_plan_review=handle_plan_review,
    EVOLUTION_GATE=EVOLUTION_GATE,
    REVIEW_STORE=BACKEND.review_store,
    classify_learning_signal_for_tool=classify_learning_signal_for_tool,
    classify_and_record_learning_signal_for_tool=classify_and_record_learning_signal_for_tool,
)
LAST_APPLIED_TOOL_CONTEXT = None


def format_reviews() -> str:
    reviews = BACKEND.review_store.list_reviews("pending")
    if not reviews:
        return "No pending reviews."
    lines = []
    for item in reviews:
        files = ", ".join(item.get("target_files", [])) or "(no files)"
        lines.append(
            f"{item['review_id']} [{item['severity']}] {item['type']} "
            f"candidate={item.get('candidate_id') or '-'} files={files}"
        )
    return "\n".join(lines)


def show_review(review_id: str) -> str:
    item = BACKEND.review_store.get_review(review_id)
    if not item:
        return f"Unknown review_id: {review_id}"
    return json.dumps(item, indent=2, ensure_ascii=False)


def approve_review(review_id: str) -> str:
    try:
        item, patch_path = BACKEND.review_store.approve_review(review_id)
    except ValueError as e:
        return f"Error: {e}"
    if not patch_path:
        return (
            f"Review {item['review_id']} approved. "
            "No patch preview is needed. No target file was modified."
        )
    return (
        f"Review {item['review_id']} approved. "
        f"Patch preview written to {patch_path}. No target file was modified."
    )


def apply_review(review_id: str) -> str:
    global LAST_APPLIED_TOOL_CONTEXT
    LAST_APPLIED_TOOL_CONTEXT = None
    try:
        item, message = BACKEND.review_store.apply_review(review_id)
    except ValueError as e:
        return f"Error: {e}"
    if item.get("tool_name") == "load_skill":
        args = item.get("tool_arguments") or {}
        skill_name = args.get("name") or item.get("target_skill") or ""
        loaded = SKILLS.load(skill_name)
        if not loaded.startswith("Error:"):
            LAST_APPLIED_TOOL_CONTEXT = {
                "review_id": item["review_id"],
                "tool_name": "load_skill",
                "content": loaded,
            }
    return f"Review {item['review_id']} applied. {message}"


def reject_review(review_id: str) -> str:
    try:
        item = BACKEND.review_store.reject_review(review_id)
    except ValueError as e:
        return f"Error: {e}"
    return f"Review {item['review_id']} rejected."


def format_promotions() -> str:
    return format_promotion_list(PROMOTIONS.list_candidates())


def show_promotion(promo_id: str) -> str:
    return format_promotion_detail(PROMOTIONS.get_candidate(promo_id), promo_id)


def propose_skill_patch(promo_id: str) -> str:
    result = propose_skill_patch_from_promotion(
        browser=PROMOTIONS,
        review_store=BACKEND.review_store,
        promo_id=promo_id,
    )
    return result.message


def propose_regression_case(promo_id: str) -> str:
    result = propose_regression_case_from_promotion(
        browser=PROMOTIONS,
        review_store=BACKEND.review_store,
        promo_id=promo_id,
    )
    return result.message


def evolve_skill(promo_id: str) -> str:
    result = evolve_skill_from_promotion(
        browser=PROMOTIONS,
        review_store=BACKEND.review_store,
        promo_id=promo_id,
        project_root=PROJECT_ROOT,
    )
    return result.message


def list_skill_versions(skill: str) -> str:
    return format_skill_versions(skill, SKILL_EVOLUTION.list_versions(skill))


def show_skill_version(skill: str, version: str) -> str:
    return format_skill_version_detail(skill, version, SKILL_EVOLUTION.get_version(skill, version))


def rollback_skill(skill: str, version: str) -> str:
    item = SKILL_EVOLUTION.create_rollback_review(
        review_store=BACKEND.review_store,
        skill=skill,
        version=version,
    )
    return (
        f"Created rollback review {item['review_id']} for {skill} {version}. "
        "No skill file was modified."
    )


# === SECTION: repl ===
if __name__ == "__main__":
    history = []
    while True:
        try:
            query = input("\033[36ms_full >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        if query.strip() == "/compact":
            if history:
                print("[manual compact via /compact]")
                history[:] = auto_compact(
                    messages=history,
                    client=client,
                    model=MODEL,
                    transcript_dir=TRANSCRIPT_DIR,
                )
            continue
        if query.strip() == "/tasks":
            print(TASK_MGR.list_all())
            continue
        if query.strip() == "/team":
            print(TEAM.list_all())
            continue
        if query.strip() == "/inbox":
            print(json.dumps(BUS.read_inbox("lead"), indent=2))
            continue
        if query.strip() == "/reviews":
            print(format_reviews())
            continue
        if query.strip() == "/review":
            print("Usage: /review <review_id>")
            continue
        if query.strip().startswith("/review "):
            print(show_review(query.strip().split(maxsplit=1)[1]))
            continue
        if query.strip().startswith("/approve "):
            print(approve_review(query.strip().split(maxsplit=1)[1]))
            continue
        if query.strip().startswith("/apply "):
            print(apply_review(query.strip().split(maxsplit=1)[1]))
            if LAST_APPLIED_TOOL_CONTEXT:
                history.append({
                    "role": "user",
                    "content": (
                        "<approved-tool-result "
                        f"review_id=\"{LAST_APPLIED_TOOL_CONTEXT['review_id']}\" "
                        f"tool=\"{LAST_APPLIED_TOOL_CONTEXT['tool_name']}\">\n"
                        f"{LAST_APPLIED_TOOL_CONTEXT['content']}\n"
                        "</approved-tool-result>"
                    ),
                })
            continue
        if query.strip().startswith("/reject "):
            print(reject_review(query.strip().split(maxsplit=1)[1]))
            continue
        if query.strip() == "/promotions":
            print(format_promotions())
            continue
        if query.strip().startswith("/promotion "):
            print(show_promotion(query.strip().split(maxsplit=1)[1]))
            continue
        if query.strip().startswith("/propose-skill-patch "):
            print(propose_skill_patch(query.strip().split(maxsplit=1)[1]))
            continue
        if query.strip().startswith("/propose-regression-case "):
            print(propose_regression_case(query.strip().split(maxsplit=1)[1]))
            continue
        if query.strip() == "/evolve-skill":
            print("Usage: /evolve-skill <promo_id>")
            continue
        if query.strip().startswith("/evolve-skill "):
            print(evolve_skill(query.strip().split(maxsplit=1)[1]))
            continue
        if query.strip() == "/skill-versions":
            print("Usage: /skill-versions <skill>")
            continue
        if query.strip().startswith("/skill-versions "):
            print(list_skill_versions(query.strip().split(maxsplit=1)[1]))
            continue
        if query.strip() == "/skill-version":
            print("Usage: /skill-version <skill> <version>")
            continue
        if query.strip().startswith("/skill-version "):
            parts = query.strip().split(maxsplit=2)
            if len(parts) != 3:
                print("Usage: /skill-version <skill> <version>")
            else:
                print(show_skill_version(parts[1], parts[2]))
            continue
        if query.strip() == "/rollback-skill":
            print("Usage: /rollback-skill <skill> <version>")
            continue
        if query.strip().startswith("/rollback-skill "):
            parts = query.strip().split(maxsplit=2)
            if len(parts) != 3:
                print("Usage: /rollback-skill <skill> <version>")
            else:
                print(rollback_skill(parts[1], parts[2]))
            continue
        history.append({"role": "user", "content": query})
        agent_loop(
            messages=history,
            client=client,
            model=MODEL,
            system=SYSTEM,
            tools=TOOLS,
            tool_handlers=TOOL_HANDLERS,
            todo=TODO,
            bg=BG,
            bus=BUS,
            token_threshold=TOKEN_THRESHOLD,
            transcript_dir=TRANSCRIPT_DIR,
            estimate_tokens=estimate_tokens,
            microcompact=microcompact,
            auto_compact=auto_compact,
            policy_engine=POLICY,
            audit_logger=AUDIT,
            review_store=BACKEND.review_store,
            actor="lead",
            allowed_capabilities=capabilities_for_actor(POLICY.policy, "lead"),
        )
        response_content = history[-1]["content"]
        if isinstance(response_content, list):
            for block in response_content:
                if hasattr(block, "text"):
                    print(block.text)
        print()
