"""Verify Chinese-by-default constraints across every user-visible LLM prompt.

The boundary: code / commands / variable names / file paths / logs /
error messages / internal enum values (decision, failure_source,
source_type, target_skill, ...) keep their English text. Only user-
visible model answers must default to Simplified Chinese unless the
user explicitly requests another language. The Chat orchestrator must
also greet new conversations with "您好，有什么可以帮您".

These tests intentionally probe the prompt strings themselves rather
than mocking an LLM round-trip, because the constraint is a static
property of what we send the model — easier to keep honest.
"""

from __future__ import annotations

import inspect
import unittest


CN_RULE = "简体中文"
CN_KEEP_ENGLISH_HINT = "代码、命令"
GREETING = "您好，有什么可以帮您"


class ChatOrchestratorPromptTests(unittest.TestCase):
    """The main ChatOrchestrator system prompt + KB Q&A prompt."""

    def test_general_chat_system_prompt_has_chinese_rule_and_greeting(self) -> None:
        from runtime import chat_executor

        source = inspect.getsource(chat_executor._llm_free_form_answer)
        self.assertIn(CN_RULE, source,
                      "general_chat system prompt must include the Chinese rule")
        self.assertIn(CN_KEEP_ENGLISH_HINT, source,
                      "system prompt must keep code/commands/logs in English")
        self.assertIn(GREETING, source,
                      "system prompt must seed the 您好，有什么可以帮您 greeting")

    def test_kb_qa_prompt_has_chinese_rule(self) -> None:
        from runtime.chat_executor import Executor

        source = inspect.getsource(Executor._kb_qa)
        self.assertIn(CN_RULE, source,
                      "KB Q&A prompt must include the Chinese rule")
        self.assertIn("摘录不足", source,
                      "KB Q&A prompt must instruct the model to say so when KB is insufficient")
        # Fallback string was translated to Chinese per spec.
        self.assertIn("当前配置的 OPENAI_MODEL 没有返回可用答案", source)
        self.assertIn("上方内容是本次已检索到、原本会用于回答的原始上下文", source)


class RealtimeSearchPromptTests(unittest.TestCase):
    """tool_registry summarization prompts (OpenAI + Bailian)."""

    def test_realtime_search_prompts_have_chinese_rule(self) -> None:
        from runtime import tool_registry

        source = inspect.getsource(tool_registry)
        # Both call_openai_summary and call_bailian_summary share the same
        # system instruction line; require Chinese-by-default to appear in
        # the module source so future authors don't drift apart.
        self.assertGreaterEqual(
            source.count(CN_RULE),
            1,
            "realtime search summary prompt must include the Chinese rule",
        )
        self.assertIn("简体中文", source)


class EvolutionLLMPromptTests(unittest.TestCase):
    """Scout enricher + bullet writer + validation gate prompts."""

    def test_opportunity_enricher_prompt_keeps_enums_english(self) -> None:
        from runtime.evolution_llm import LLMOpportunityEnricher
        prompt = LLMOpportunityEnricher.SYSTEM_PROMPT
        self.assertIn(CN_RULE, prompt)
        # Pin that enum names stay English so we don't accidentally
        # ask the model to translate decision / target_skill / etc.
        for term in ("decision", "target_skill", "source_type", "failure_source"):
            self.assertIn(term, prompt,
                          f"enricher prompt should mention '{term}' as a non-translated enum")

    def test_bullet_writer_prompt_defaults_to_chinese(self) -> None:
        from runtime.evolution_llm import LLMBulletWriter
        prompt = LLMBulletWriter.SYSTEM_PROMPT
        self.assertIn(CN_RULE, prompt)
        # Section heading must stay English so the bounded-edit gate
        # (which exact-matches "## Memory-derived rules") still works.
        self.assertIn("## Memory-derived rules", prompt)

    def test_validation_gate_prompt_defaults_to_chinese(self) -> None:
        from runtime.evolution_llm import LLMValidationGate
        prompt = LLMValidationGate.SYSTEM_PROMPT
        self.assertIn(CN_RULE, prompt)
        # reject_reason is user-visible; JSON keys and score fields stay
        # English so the deterministic gate parser still works.
        self.assertIn("reject_reason", prompt)
        self.assertIn("train_score", prompt)


class HarnessSidePromptTests(unittest.TestCase):
    """CLI agent / teammate / subagent prompts."""

    def test_cli_agent_system_prompt_has_chinese_rule_and_greeting(self) -> None:
        from harness.prompt import build_system_prompt

        class _StubSkills:
            def descriptions(self) -> str:
                return ""

        prompt = build_system_prompt("/tmp/proj", _StubSkills())
        self.assertIn(CN_RULE, prompt)
        self.assertIn(GREETING, prompt)
        # Tool names / sentinel tags must remain English.
        self.assertIn("<untrusted_tool_result>", prompt)
        self.assertIn("task_create", prompt)

    def test_team_and_subagent_prompts_have_chinese_rule(self) -> None:
        from harness import team, subagent
        self.assertIn(CN_RULE, inspect.getsource(team))
        self.assertIn(CN_RULE, inspect.getsource(subagent))


if __name__ == "__main__":
    unittest.main()
