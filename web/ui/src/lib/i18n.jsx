import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "safeharness.language";
const SUPPORTED = ["en", "zh"];

const STRINGS = {
  en: {
    "app.brand_line_1": "SafeHarness",
    "app.brand_line_2": "Console",
    "app.local_workspace": "Local Workspace",
    "app.language": "Language",

    "nav.chat": "Chat",
    "nav.workspace": "Workspace",
    "nav.assets": "Assets",
    "nav.assets.library": "Library",
    "nav.assets.changes": "Changes",
    "nav.assets.governance": "Governance",
    "nav.settings": "Settings",

    "panel.current_asset": "Current Asset",
    "panel.asset_type": "Asset type",
    "panel.asset_type.skill": "Skill",
    "panel.name": "Name",
    "panel.active_source": "Active source",
    "panel.latest_snapshot": "Latest snapshot",
    "panel.no_snapshot": "No snapshot",
    "panel.skill_evolution_progress": "Skill Evolution Progress",
    "panel.next_action": "Next Action",
    "panel.next_action.regenerate_hint":
      "Missing promotion_decision, promotion_score, or eligible_target. Requires regeneration.",
    "panel.next_action.working": "Working…",
    "panel.next_action.regenerate": "Regenerate with Promotion Eligibility",
    "panel.next_action.waiting": "Waiting",

    "step.memory": "Memory captured",
    "step.promo": "PROMO generated",
    "step.regression": "Regression review",
    "step.skill": "Skill patch review",
    "step.version": "Version recorded",

    "chat.title": "Chat",
    "chat.placeholder": "Message Agent…",
    "chat.final_result": "Final Result",
    "chat.show_all_steps": "Show all {total} steps ({hidden} hidden)",
    "chat.hide_internal_steps": "Hide internal steps",

    "settings.title": "Settings",
    "settings.subtitle":
      "Read-only summary of provider state. Edit values in .env or via the Model Connection form below.",
    "settings.workspace": "Workspace",
    "settings.workspace.root": "Root",
    "settings.workspace.asset_counts": "Asset counts",
    "settings.workspace.pending_changes": "Pending changes",
    "settings.safety_policy": "Safety Policy",
    "settings.safety_policy.policy": "Policy",
    "settings.safety_policy.policy_value": "default",
    "settings.safety_policy.create_route": "Create route",
    "settings.safety_policy.create_route_value": "preflight + confirmation",
    "settings.safety_policy.rollback": "Rollback",
    "settings.safety_policy.rollback_value": "review required",

    "settings.search.title": "Built-in web_search Status",
    "settings.search.description":
      "web_search / web_research is a built-in tool. Configure it by editing the project .env: set SEARCH_PROVIDER=bailian (recommended) plus your DASHSCOPE_API_KEY or SEARCH_API_KEY. Settings reload automatically on next server start.",
    "settings.search.load_failed": "Status load failed",
    "settings.search.loading": "Loading…",
    "settings.search.configured": "Configured",
    "settings.search.provider": "Provider",
    "settings.search.api_key": "API key",
    "settings.search.not_set": "not set",
    "settings.search.test_query": "Test query",
    "settings.search.test_button": "Test search now",
    "settings.search.testing": "Testing…",
    "settings.search.test_description":
      "Runs a real search through the configured provider and shows the actual response. Use this to verify your key works end-to-end.",
    "settings.search.status_ok": "ok",
    "settings.search.status_failed": "failed",
    "settings.search.status_label": "Status",
    "settings.search.search_mode": "Search mode",
    "settings.search.endpoint": "Endpoint",
    "settings.search.raw_response": "Raw MCP response (truncated)",
    "settings.search.results_for": "result(s) for",
    "settings.search.loaded_env": "os.environ keys (from .env autoload)",

    "settings.model.title": "Model Connection",
    "settings.model.description":
      "OpenAI-compatible endpoint used for Chat fallback answers and Markdown summarization. Picking a preset fills in the base URL and a default model name; you still need to provide your own API key.",
    "settings.model.preset": "Preset",
    "settings.model.preset_hint": "Optional: select to autofill base URL and model name.",
    "settings.model.model": "Model",
    "settings.model.model_hint": "e.g. gpt-4o-mini, qwen-plus, deepseek-chat.",
    "settings.model.base_url": "Base URL",
    "settings.model.base_url_hint":
      "OpenAI-compatible chat completions root. Leave empty to default to https://api.openai.com/v1.",
    "settings.model.api_key": "API Key",
    "settings.model.api_key_hint_stored":
      "Stored. Current masked value: {masked}. Leave empty to keep, type to replace.",
    "settings.model.api_key_hint_empty": "Stored in .env only. Never returned in plaintext.",
    "settings.model.save": "Save to .env",
    "settings.model.saving": "Saving…",
    "settings.model.clear": "Clear model connection",
    "settings.model.cleared": "Model connection cleared from .env.",
    "settings.model.configured": "Configured",
    "settings.model.model_label": "Model",
    "settings.model.api_key_label": "API key",
    "settings.model.no_model": "no model",
    "settings.model.not_configured": "not configured",
    "settings.model.placeholder_keep": "•••••• (keep existing)",
  },
  zh: {
    "app.brand_line_1": "SafeHarness",
    "app.brand_line_2": "控制台",
    "app.local_workspace": "本地工作区",
    "app.language": "语言",

    "nav.chat": "对话",
    "nav.workspace": "工作区",
    "nav.assets": "资产",
    "nav.assets.library": "资产库",
    "nav.assets.changes": "变更",
    "nav.assets.governance": "治理",
    "nav.settings": "设置",

    "panel.current_asset": "当前资产",
    "panel.asset_type": "资产类型",
    "panel.asset_type.skill": "Skill",
    "panel.name": "名称",
    "panel.active_source": "当前文件",
    "panel.latest_snapshot": "最近版本",
    "panel.no_snapshot": "暂无版本",
    "panel.skill_evolution_progress": "Skill 演进进度",
    "panel.next_action": "下一步操作",
    "panel.next_action.regenerate_hint":
      "缺少 promotion_decision / promotion_score / eligible_target，需要重新生成。",
    "panel.next_action.working": "处理中…",
    "panel.next_action.regenerate": "重新生成 Promotion",
    "panel.next_action.waiting": "等待中",

    "step.memory": "记忆已捕获",
    "step.promo": "PROMO 已生成",
    "step.regression": "回归审查",
    "step.skill": "Skill 补丁审查",
    "step.version": "版本已记录",

    "chat.title": "对话",
    "chat.placeholder": "和 Agent 对话…",
    "chat.final_result": "最终结果",
    "chat.show_all_steps": "显示全部 {total} 步（已隐藏 {hidden} 步）",
    "chat.hide_internal_steps": "收起内部步骤",

    "settings.title": "设置",
    "settings.subtitle":
      "Provider 状态只读展示。要修改请编辑 .env 或在下方 Model Connection 表单中操作。",
    "settings.workspace": "工作区",
    "settings.workspace.root": "根目录",
    "settings.workspace.asset_counts": "资产统计",
    "settings.workspace.pending_changes": "待处理变更",
    "settings.safety_policy": "安全策略",
    "settings.safety_policy.policy": "策略",
    "settings.safety_policy.policy_value": "默认",
    "settings.safety_policy.create_route": "创建路径",
    "settings.safety_policy.create_route_value": "preflight + 二次确认",
    "settings.safety_policy.rollback": "回滚",
    "settings.safety_policy.rollback_value": "需要 review",

    "settings.search.title": "内置 web_search 状态",
    "settings.search.description":
      "web_search / web_research 是内置工具。请编辑项目根目录的 .env：设置 SEARCH_PROVIDER=bailian（推荐）并填入 DASHSCOPE_API_KEY 或 SEARCH_API_KEY。下次启动服务时自动加载。",
    "settings.search.load_failed": "状态加载失败",
    "settings.search.loading": "加载中…",
    "settings.search.configured": "是否已配置",
    "settings.search.provider": "Provider",
    "settings.search.api_key": "API key",
    "settings.search.not_set": "未设置",
    "settings.search.test_query": "测试查询",
    "settings.search.test_button": "立即测试搜索",
    "settings.search.testing": "测试中…",
    "settings.search.test_description":
      "用当前 provider 跑一次真实搜索并展示完整响应。用来验证 key 是否能跑通。",
    "settings.search.status_ok": "成功",
    "settings.search.status_failed": "失败",
    "settings.search.status_label": "状态",
    "settings.search.search_mode": "搜索模式",
    "settings.search.endpoint": "Endpoint",
    "settings.search.raw_response": "原始 MCP 响应（已截断）",
    "settings.search.results_for": "条结果，查询：",
    "settings.search.loaded_env": "已加载到 os.environ 的相关 key",

    "settings.model.title": "大模型连接",
    "settings.model.description":
      "Chat 兜底回答和 Markdown 摘要使用的 OpenAI 兼容 endpoint。选预设可自动填入 base URL 和默认 model 名，API key 仍需自己填。",
    "settings.model.preset": "预设",
    "settings.model.preset_hint": "可选：点一下自动填 base URL 和 model 名。",
    "settings.model.model": "Model",
    "settings.model.model_hint": "例如 gpt-4o-mini、qwen-plus、deepseek-chat。",
    "settings.model.base_url": "Base URL",
    "settings.model.base_url_hint":
      "OpenAI 兼容 chat completions 根 URL。留空使用默认 https://api.openai.com/v1。",
    "settings.model.api_key": "API Key",
    "settings.model.api_key_hint_stored": "已存储，脱敏：{masked}。留空表示不变，输入即替换。",
    "settings.model.api_key_hint_empty": "仅存到 .env，不会以明文返回。",
    "settings.model.save": "保存到 .env",
    "settings.model.saving": "保存中…",
    "settings.model.clear": "清除大模型配置",
    "settings.model.cleared": "已从 .env 清除大模型配置。",
    "settings.model.configured": "是否已配置",
    "settings.model.model_label": "Model",
    "settings.model.api_key_label": "API key",
    "settings.model.no_model": "未设置 model",
    "settings.model.not_configured": "未配置",
    "settings.model.placeholder_keep": "•••••• (保留现值)",
  },
};

const LanguageContext = createContext({ language: "en", setLanguage: () => {}, t: (key) => key });

function detectInitialLanguage() {
  if (typeof window === "undefined") return "en";
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored && SUPPORTED.includes(stored)) return stored;
  } catch (error) {
    // ignore storage errors
  }
  const navLang = (typeof navigator !== "undefined" && navigator.language) || "";
  return navLang.toLowerCase().startsWith("zh") ? "zh" : "en";
}

function format(template, params) {
  if (!params || typeof template !== "string") return template;
  return template.replace(/\{(\w+)\}/g, (match, key) => (key in params ? String(params[key]) : match));
}

export function LanguageProvider({ children }) {
  const [language, setLanguageState] = useState(detectInitialLanguage);

  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
    }
    try {
      window.localStorage.setItem(STORAGE_KEY, language);
    } catch (error) {
      // ignore storage errors
    }
  }, [language]);

  const setLanguage = useCallback((next) => {
    if (SUPPORTED.includes(next)) setLanguageState(next);
  }, []);

  const t = useCallback(
    (key, params) => {
      const dict = STRINGS[language] || STRINGS.en;
      const value = dict[key] ?? STRINGS.en[key] ?? key;
      return format(value, params);
    },
    [language],
  );

  const value = useMemo(() => ({ language, setLanguage, t }), [language, setLanguage, t]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  return useContext(LanguageContext);
}

export function useTranslate() {
  return useContext(LanguageContext).t;
}

export const SUPPORTED_LANGUAGES = SUPPORTED;
