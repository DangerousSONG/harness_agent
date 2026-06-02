from __future__ import annotations

from typing import Any, Callable

from runtime.chat_capability import AssetRouter, CapabilityChecker
from runtime.chat_executor import Executor
from runtime.chat_intent import IntentRouter, TaskModeClassifier
from runtime.chat_planner import ActionPlanner, ClarificationPlanner, RiskClassifier
from runtime.chat_response import ResponseComposer, normalize_legacy_response, trace
from runtime.chat_safety import InputSafetyGate
from runtime.credit_assignment import assign_credit
from runtime.run_trace import RunTraceStore, mark_exception, populate_from_response


LegacyHandler = Callable[[Any, str, dict[str, Any]], dict[str, Any]]


class ContextLoader:
    def load(self, ctx: Any, intent: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        # The new orchestrator keeps context loading narrow. Legacy workspace
        # routes still load their detailed context inside the compatibility
        # executor until those paths are migrated.
        primary = intent.get("primary", "general_chat")
        if primary in {"skill_use_request", "memory_preference"}:
            try:
                skills = ctx.skill_loader.list_skills()
            except Exception:
                skills = []
            return {"skills": skills}, [
                trace("tool_call", "Context loader", method="GET", path="/api/skills", status="completed", summary=f"Loaded {len(skills)} skill record(s).")
            ]
        return {}, []


class MemoryCaptureJudge:
    def judge(self, task_mode: dict[str, Any], intent: dict[str, Any]) -> dict[str, Any]:
        should_capture = task_mode.get("mode") == "preference_memory" or intent.get("primary") == "memory_preference"
        return {
            "should_capture": should_capture,
            "reason": "Explicit durable preference." if should_capture else "No durable memory capture requested.",
        }


class ChatOrchestrator:
    """Claw-style workspace Chat orchestrator.

    Pipeline:
    User Query -> InputSafetyGate -> TaskModeClassifier -> IntentRouter ->
    ClarificationPlanner -> ContextLoader -> CapabilityChecker -> AssetRouter ->
    RiskClassifier -> ActionPlanner -> Executor/ResponseComposer ->
    MemoryCaptureJudge.
    """

    def __init__(self, ctx: Any, legacy_handler: LegacyHandler | None = None):
        self.ctx = ctx
        self.safety_gate = InputSafetyGate()
        self.task_mode_classifier = TaskModeClassifier()
        self.intent_router = IntentRouter()
        self.clarification_planner = ClarificationPlanner()
        self.context_loader = ContextLoader()
        self.capability_checker = CapabilityChecker()
        self.asset_router = AssetRouter()
        self.risk_classifier = RiskClassifier()
        self.action_planner = ActionPlanner()
        self.executor = Executor(legacy_handler)
        self.memory_capture_judge = MemoryCaptureJudge()
        self.composer = ResponseComposer()
        # Run-level attribution. Falls back to a no-op when project_root
        # is unavailable so tests with stub contexts still work.
        project_root = getattr(ctx, "project_root", None)
        self.run_trace_store = RunTraceStore(project_root) if project_root else None

    def handle(self, message: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        run_trace = (
            self.run_trace_store.new_trace(task=message)
            if self.run_trace_store else None
        )
        try:
            response = self._handle_inner(message, context)
        except BaseException as exc:
            if run_trace is not None and self.run_trace_store is not None:
                mark_exception(run_trace, exc)
                credit = assign_credit(run_trace).to_dict()
                try:
                    self.run_trace_store.save(run_trace, credit_assignment=credit)
                except Exception:
                    pass
            raise
        if run_trace is not None and self.run_trace_store is not None:
            try:
                populate_from_response(
                    run_trace,
                    response=response,
                    safety=response.get("safety"),
                    intent=response.get("intent"),
                    loaded_context=(response.get("data") or {}).get("loaded_context"),
                )
                credit = assign_credit(run_trace).to_dict()
                self.run_trace_store.save(run_trace, credit_assignment=credit)
                if isinstance(response.get("data"), dict):
                    response["data"]["run_id"] = run_trace.run_id
            except Exception:
                # Observability must never break the chat response.
                pass
        return response

    def _handle_inner(self, message: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        safety = self.safety_gate.check(message)
        task_mode = self.task_mode_classifier.classify(message, safety)
        intent = self.intent_router.route(message, safety, task_mode)
        loaded_context, load_trace = self.context_loader.load(self.ctx, intent)
        capability = self.capability_checker.check(self.ctx, message, task_mode, intent)
        asset_route = self.asset_router.route(intent, capability)
        risk = self.risk_classifier.classify(safety, task_mode, intent, asset_route)
        plan = self.action_planner.plan(intent, capability)
        memory_judgement = self.memory_capture_judge.judge(task_mode, intent)
        prefix_trace = self._pipeline_trace(safety, task_mode, intent, capability, plan) + load_trace

        if context.get("force_mode") == "answer_without_realtime":
            return self.composer.compose(
                response_type="answer",
                message=self._offline_realtime_answer(message, intent),
                safety=safety,
                task_mode=task_mode,
                intent={**intent, "mode": "answer_without_realtime"},
                asset_route=asset_route,
                capability=capability,
                risk=risk,
                traces=prefix_trace + [
                    trace(
                        "decision",
                        "Decision",
                        status="completed",
                        decision="answer_without_realtime",
                        summary="Composed an offline analysis framework without current market data.",
                    )
                ],
                data={"force_mode": "answer_without_realtime"},
            )

        clarification = self.clarification_planner.plan(intent)
        if clarification and task_mode.get("mode") != "asset_update":
            return self.composer.compose(
                response_type="clarification",
                message=clarification["message"],
                safety=safety,
                task_mode=task_mode,
                intent=intent,
                asset_route=asset_route,
                capability=capability,
                risk=risk,
                traces=prefix_trace,
                data={"loaded_context": loaded_context, "memory_capture": memory_judgement},
            )

        result = self.executor.execute(
            ctx=self.ctx,
            message=message,
            context=context,
            safety=safety,
            task_mode=task_mode,
            intent=intent,
            asset_route=asset_route,
            capability=capability,
            risk=risk,
            prefix_trace=prefix_trace,
        )
        if "task_mode" not in result or "capability" not in result:
            return normalize_legacy_response(
                result,
                safety=safety,
                task_mode=task_mode,
                intent=intent,
                asset_route=asset_route,
                capability=capability,
                risk=risk,
                prefix_trace=prefix_trace,
            )
        result.setdefault("data", {})
        if isinstance(result["data"], dict):
            result["data"].setdefault("memory_capture", memory_judgement)
        return result

    def _offline_realtime_answer(self, message: str, intent: dict[str, Any]) -> str:
        if intent.get("primary") == "financial_research_query":
            return (
                "可以先给你一个离线财报分析框架，但我不会声称已经查询到今天的最新财报、股价或新闻。\n\n"
                "1. 看收入和同比/环比增速，特别区分数据中心、游戏、专业可视化等业务。\n"
                "2. 看毛利率、运营费用和指引，判断增长是否伴随盈利质量改善。\n"
                "3. 看管理层对下一季度需求、供应、库存和资本开支的描述。\n"
                "4. 对照市场预期，而不只看绝对数字；股价反应常取决于是否超预期。\n"
                "5. 单独列风险：估值、客户集中、供应链、出口限制、竞争和周期波动。\n\n"
                "说明：这不是财务建议；需要实时结论时应先配置搜索/金融 provider 或提供可靠来源。"
            )
        return (
            "我可以给出不依赖实时数据的通用分析框架，但不会编造最新事实、新闻、来源或引用。"
            "如果需要实时结论，请配置搜索 provider 或提供要总结的 URL。"
        )

    def _pipeline_trace(
        self,
        safety: dict[str, Any],
        task_mode: dict[str, Any],
        intent: dict[str, Any],
        capability: dict[str, Any],
        plan: dict[str, Any],
    ) -> list[dict[str, Any]]:
        traces = [
            trace(
                "safety_check",
                "Input safety check",
                status="completed" if safety.get("safe") else "failed",
                risk_labels=", ".join(safety.get("risk_labels", [])) or "none",
                severity=safety.get("severity", "low"),
                summary=safety.get("reason", ""),
            ),
            trace(
                "analyze",
                "Analyze request",
                primary_intent=intent.get("primary", ""),
                mode=intent.get("mode", ""),
                summary=intent.get("reason", ""),
            ),
            trace(
                "task_mode",
                "Task mode",
                mode=task_mode.get("mode", ""),
                confidence=task_mode.get("confidence", 0),
                summary=task_mode.get("reason", ""),
            ),
            trace(
                "intent_analysis",
                "Intent analysis",
                primary_intent=intent.get("primary", ""),
                confidence=intent.get("confidence", 0),
                mode=intent.get("mode", ""),
                requires_realtime_data=str(bool(intent.get("requires_realtime_data"))).lower(),
                summary=intent.get("reason", ""),
            ),
            trace(
                "capability_check",
                "Capability check",
                status="completed" if capability.get("can_execute") or not intent.get("requires_realtime_data") else "failed",
                web_research_executable=str(bool(capability.get("web_research_executable"))).lower(),
                web_search_provider_configured=str(bool(capability.get("web_search_provider_configured"))).lower(),
                crawl4ai_available=str(bool(capability.get("crawl4ai_available"))).lower(),
                finance_quote_executable=str(bool(capability.get("finance_quote_executable"))).lower(),
                model_connection_configured=str(bool(capability.get("model_connection_configured"))).lower(),
                summary=capability.get("reason", ""),
            ),
            trace(
                "decision",
                "Decision",
                status="blocked" if plan.get("decision") == "missing_realtime_capability" else "completed",
                decision=plan.get("decision", ""),
                summary=plan.get("summary", ""),
            ),
        ]
        for status in capability.get("tool_statuses", []):
            traces.append(
                trace(
                    "tool_registry_check",
                    "Tool availability check",
                    status="completed" if status.get("executable") else "failed",
                    tool_name=status.get("name", ""),
                    asset_exists=str(bool(status.get("asset_exists"))).lower(),
                    handler_available=str(bool(status.get("handler_available"))).lower(),
                    provider_configured=str(bool(status.get("provider_configured"))).lower(),
                    executable=str(bool(status.get("executable"))).lower(),
                    missing=", ".join(status.get("missing", [])),
                    summary=f"{status.get('name')} executable={bool(status.get('executable'))}; missing={status.get('missing', [])}.",
                )
            )
        return traces
