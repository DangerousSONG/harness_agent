# Harness Agent

本地优先的 **SafeHarness + Self-Evolving Skills** 实验系统。不让 Agent 无约束地修改自己，而是验证一条 **受控自进化** 链路。

## 系统架构图

<p align="center">
  <img src="docs/architecture.svg" alt="Harness Agent architecture" width="100%"/>
</p>

**六层视角**：前端工作台 · 编排与 SafeHarness · 两条自进化链路（主链路事件驱动 / 旁路批量发现）· 共享审批 ReviewQueue · AI 基础设施 · 本地存储。

**两条进化链路的分工**：

| 维度 | ♻️ 主链路 | 🛰️ 旁路 |
|---|---|---|
| 触发 | 事件驱动（用户纠正 / 工具失败 / 安全事件） | 离线批量扫描（`/evolution-scan`） |
| 准入 | `occurrence_count ≥ 3`（强纠正 ≥ 2） | 单次 safety 事件即可（safety_gain 通道） |
| 改 SKILL.md 范围 | 整篇可编辑 | 仅 `## Memory-derived rules` 节 · 仅 `add/replace/delete` · 单次 ≤ 5 op |
| 退化保护 | Regression Gate（positive + negative case） | ValidationGate（train / validation / regression） |
| 共享 | **同一 ReviewQueue · 同一 Skill Evolution Registry · 同一 Approve+Apply** |

核心原则：memory / PROMO / patch 都可以自动提议，但 **`SKILL.md` 的真实修改必须经过回归测试、人工审批、显式 apply 和版本登记**。

## 快速开始

Python 3.10+。

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

最少配置 `.env`：

```env
OPENAI_API_KEY=...
MODEL_ID=...                 # CLI / agent_harness
OPENAI_MODEL=                # web server / chat orchestrator（可与 MODEL_ID 同值）
OPENAI_BASE_URL=

# 实时查询 provider 优先级：Bailian / DashScope > DuckDuckGo no-key fallback
SEARCH_PROVIDER=bailian
DASHSCOPE_API_KEY=...
SEARCH_TOOL_NAME=auto        # MCP tool 自动发现

# 旁路 Scout / Optimizer 默认 deterministic；接 LLM：
# EVOLUTION_LLM_ENABLED=1
```

启动：

```bash
python harness/agent_harness.py                                   # CLI
uvicorn web.server:create_app --factory --reload --port 8000      # Web 后端
cd web/ui && npm install && npm run dev                           # Web 前端
```

## REPL 命令

| Command | Description |
| --- | --- |
| `/reviews` · `/review <id>` · `/approve <id>` · `/apply <id>` · `/reject <id>` | ReviewQueue |
| `/promotions` · `/promotion <id>` · `/evolve-skill <id>` | PROMO / 主链路推进 |
| `/skill-versions <skill>` · `/skill-version <skill> <ver>` · `/rollback-skill <skill> <ver>` | 版本与回滚 |
| `/evolution-scan` · `/evolution-opportunities` · `/evolution-opportunity <id>` | Scout 旁路 |
| `/promotion-batches` · `/promotion-batch <id>` · `/promotion-batch-create <opp_id...>` | Batch 合并 |
| `/skill-optimize <batch_id>` · `/skill-edits` · `/skill-edit <id>` · `/skill-edit-validate <id>` · `/rejected-edits` | Optimizer 旁路 |
| `/scout-decisions` · `/scout-stats [score_field=...] [threshold=...] [decision=...]` | 决策日志 / 命中率 |
| `/compact` · `/tasks` · `/team` · `/inbox` | 上下文 / 任务 / 队友 / 消息 |

## 主链路细节

**SafeHarness** — `RuntimeEvent → PolicyEngine → allow / warn / sanitize / require_approval / block`，决策经 `AuditLogger` 落到 `.audit/`。`require_approval` 不执行原始动作，转为创建 `REV-xxxx`。`SAFETY_POLICY=high_security` 切换严格策略。

**ReviewQueue** — `.reviews/REV-*.json` + `.reviews/patches/REV-*.diff`。`pending → approved → applied / rejected`。`/approve` 只生成 diff；`/apply` 才落盘。

**Skill Memory** — `classify_and_record_learning_signal` 自动归属 / 脱敏 / 去重 / 污染拦截。落盘 `skills/<skill>/memory/{LEARNINGS,ERRORS,FEATURE_REQUESTS,POLICY_CANDIDATES,REGRESSION_TESTS}.md`。**不沉淀**：secret · token · prompt injection · bypass approval · disable safety · 一次性偏好。

**PROMO 候选** — 相似 memory 合并并累计 `occurrence_count`，9 维 `promotion_score` 决定升级路径：

| 触发 | 输出 |
|---|---|
| `occurrence_count ≥ 3` + 可迁移 + 低风险 | `skill_rule` PROMO |
| 强纠正（"以后/固定/默认/不要再/可复用"）+ 可测试，`count ≥ 2` | `skill_rule` PROMO |
| high-severity safety / `policy_candidate` | `policy_review`（**不直接进 SKILL.md**） |
| 低归属置信度 / secret / 注入 / bypass approval / disable safety | 不生成 |

**`/evolve-skill <promo_id>`** — 按状态推进：缺 regression → `skill.regression_case` review；有 coverage → `skill.promotion` review；完成 → 显示版本。

**Regression Gate** —
1. *覆盖检查*：`skill.promotion` apply 前在 `skills/<skill>/eval/cases.yaml` 必须找到该 PROMO 的 positive + negative case，否则 apply 拒绝。
2. *Eval 运行*（`runtime/skill_eval_runner.py`）：apply **写盘前**对 *proposed* SKILL.md 跑一次 `cases.yaml`。失败 → 拒绝、文件不动；通过 → `RunReport` 写入 `eval_result.json`。
   > Deterministic 模式只校验 SKILL.md 文本层面（`target_rule` 是否落到 `## Memory-derived rules`）。`expected_behavior` / `negative_assertions` 描述的是 *agent 运行时输出*，文本检测无法保真，因此 *记录但不强制*；LLM evaluator 接口已留好。

**Skill Evolution Registry** — `skill.promotion` apply 成功后写 `.skills_versions/<skill>/`：`versions.jsonl` + `<version>/{SKILL.md, patch.diff, eval_result.json}`。**Runtime 加载源始终是 `skills/<skill>/SKILL.md`**；`.skills_versions/` 仅用于审计与回滚（rollback 也走 review）。

## 旁路 Scout + Optimizer

旁路是主链路的**离线批量补丁**通道。三层硬约束：

- **Scout 只读** — 扫 `.skills_memory/` + `skills/*/memory/` + `PROMOTION_CANDIDATES.md` + `.audit/runs/`；不写 `SKILL.md` / `eval/cases.yaml`；不创建 review。
- **Optimizer 受约束写** — 仅在 `.evolution/skill_edits/` 草拟；`edit_ops ∈ {add, replace, delete}`，`target_section == "## Memory-derived rules"`，单次 ≤ 5 op，每 op ≤ 500 字符；`decision ∈ {quarantine, safety_review}` 或 signal `quarantined=True` 一律拒绝提案。
- **ValidationGate 把守** — 失败 → `.evolution/rejected_edits/` 归档；通过 → `submit_review` 创建 `skill.bounded_edit` review，人审批后 apply。

### Scout 四段式判断

源码：`runtime/evolution_scout.py`。

```text
① 信号采集 + 硬过滤   → 攻击载荷脱敏归档，禁入 Optimizer
② 语义标签 (9 类)     → 给信号打可解释的语义标签
③ 跨 skill 聚类       → normalized_problem_signature 共享 cluster_key
④ 证据 × 价值 × 风险  → 三个独立分数，外加 testability
⑤ 决策矩阵            → promote / request_eval / defer / reject /
                          safety_review / quarantine
```

**信号源（3 个）**：

| 源 | 内容 | 备注 |
|---|---|---|
| 全局 + skill memory | `LEARNINGS / ERRORS / FEATURE_REQUESTS / POLICY_CANDIDATES / REGRESSION_TESTS` | 按 ID 解析 |
| PROMO 候选 | `PROMOTION_CANDIDATES.md` | 自动加权可靠度 |
| **RunTrace signals**（`runtime/run_trace_scanner.py`） | `.audit/runs/*.json` → `skill_gap / rule_not_applied / positive_preference` | 仅候选；`tool_failure / environment / policy_block / unknown` 在 scanner 上游已过滤 |

**Stage 1 安全过滤** — `ATTACK_PATTERNS` 分类：提示注入 · 绕过审批 · 关闭安全 · 密钥外泄。命中 → 信号 `quarantined=True`，content 中攻击短语替换为 `[REDACTED_ATTACK:<类型>]`，但 `source_path` / `source_ref` 完整保留可追溯。攻击载荷出现在 error 记录里并配 `blocked / rejected / 已拦截` 等防御标记 → 仅打 `security_incident` 标签走 safety_review，不全隔离。

**Stage 2 语义标签**（9 类，取代旧的单一 `safety`）：`security_incident / governance_related / memory_poisoning / policy_related / rollback_related / tool_failure / user_correction / format_preference / capability_gap`。强纠正（`以后 0.9 / 固定 0.9 / 默认 0.8 / 不要再 0.95 / from now on 0.95 / must not 0.85 / ...`）`≥ 0.7` 自动追加 `user_correction`。

> 关键修正：`approval / policy / review` 等普通治理词**只**打 `governance_related` / `policy_related`，**不**升级为 `security_incident`。

**Stage 3 聚类** — `cluster_key` 优先使用从 content 抽取的 **问题签名**：`action / tool / error_type / target_artifact / correction_pattern / safety_type`。签名形如 `sig:safe:approval_block|err:policy_block|tool:edit_file`，**不含 skill 名也不含具体文件路径**——同类问题在不同 skill 上能合并（→ 高可迁移度），同 tag 但不同根因（policy 拦截 vs JSON 解析）**不**合并。无可抽取特征时退化到 `tag:...` / `kw:...`。

聚类后 `target_skill` 选 `observed_skill` 分布出现次数最多者（平手时优先非 `self_improvement`）。可迁移度按 skill 数计：3+ 1.0 / 2 0.85 / 1+跨切标签 0.65 / 单 skill 0.40。

> **`self_improvement` 不自动晋升**：无真实 skill 归属的聚类，决策矩阵在 promote 之前拦截 —— 高价值降为 `request_eval`（"需人工标注 target_skill"），低价值 `defer`。RunTraceScanner 在 signal 上游已经把 `needs_human_label=true` 的候选强制 `observed_skill=self_improvement`，触发同一道闸。

**Stage 4 评分**（每项 [0,1]）—
- `evidence_quality` = 0.30·来源可靠度 + 0.25·独立出现次数 + 0.25·纠正强度 + 0.10·失败可复现度 + 0.10·调用链支撑
- `value_score`     = 0.25·证据 + 0.15·{频率, 可迁移度, 影响, 可测试度} + 0.10·skill_confidence + 0.05·safety_gain
- `risk_score`      = 0.25·回归 + 0.20·{过拟合, 策略} + 0.15·范围 + 0.10·{成本, 不确定性}
- `testability`     复合分（非元标签 0.20 + safety/governance 0.15 + 0.30·correction + format/capability 0.25 + 可复现 tool_failure 0.20 + PROMO 背书 0.10）

**Stage 5 决策矩阵**（自顶向下，先匹配先用）：

| 触发条件 | 决策 |
|---|---|
| `security_incident` 标签 | `safety_review` |
| **policy_gate**：tag ∈ {policy_related, policy_candidate, governance_related, tool_failure}，或 content 含 `policy_block / approval_block / Tool Call Blocked / Policy Enforcement Triggered / SafeHarness policy / protected file / policy_candidate / safety` | `safety_review`（reason 标 `requires_policy_review=true`） |
| `value ≥ 0.60 ∧ risk ≤ 0.35 ∧ testability ≥ 0.70` | `promote` |
| `value ≥ 0.55 ∧ (testability < 0.70 ∨ risk > 0.35)` | `request_eval` |
| `value ≥ 0.40 ∧ evidence < 0.50` | `defer` |
| `overfitting ≥ 0.5 ∧ Σf < 3` | `reject` |
| `target_skill = self_improvement` 非 security | `defer`（reason 提示 `request_human_label`） |
| `value ≥ 0.30` | `defer` |
| 其他 | `reject` |

quarantine 桶在 Stage 1 单独处理，固定 `decision=quarantine`、优先级 high，`must_not_regress` 写明"禁止把攻击载荷沉淀进 skill rule"。

**派生字段** — `should_improve` 按 tag 类型生成具体表述；`must_not_regress` 默认两条（不放宽安全策略、不绕 ReviewQueue），按 tag 追加。Batch 合并必须同 skill；跨 skill 抛 `ValueError`。

### Optimizer 受约束补丁

`propose()` 接受 `batch_id` 或 `opportunity_id`；`decision=reject` 让整次提案被拒。

**ValidationGate 默认评分** —
- `train_score`: 常量 0.6
- `validation_score`: 起 0.5；新 bullet 已在 SKILL.md 出现 −0.05，否则 +0.10，clamp [0,1]
- `regression_score`: 命中禁词（`disable safety / bypass approval / ignore previous`） ⇒ 0.0；`cases:` 非空 ⇒ 0.75；否则 0.6
- 判定：`validation_score ≥ 0.5 ∧ regression_score ≥ 0.5`

### LLM 接入（opt-in）

设 `EVOLUTION_LLM_ENABLED=1` + `OPENAI_API_KEY` + `OPENAI_MODEL` 即开。默认 deterministic。

| 接入点 | 做什么 | 仍然不能做 |
|---|---|---|
| `LLMOpportunityEnricher` | 丰富 `reason` / `should_improve` / `must_not_regress` | 改 `decision` / `score` / `signal_ids` / `target_skill` |
| `LLMBulletWriter` | 生成 1–3 条 bullet（≤ 240 字符/条） | 突破 `add/replace/delete`、扩 section、绕 `validate_edit_ops` |
| `LLMValidationGate` | 给 train / validation / regression 三分 | 直接 apply、跳 ReviewQueue、写 `SKILL.md` |

所有 LLM 输出经 `redact_secrets` + `looks_like_memory_poisoning` 清洗，命中污染字样 → 丢弃 → 回退 deterministic。网络/解析错误同样回退。

### 落盘 & 追溯

```text
.evolution/
├─ signals/  opportunities/  batches/  skill_edits/
├─ validation_results/  rejected_edits/
└─ scout_decisions/
```

追溯链：`LearningSignal.source_path:source_ref` → `Opportunity.signal_ids` → `Batch.opportunity_ids + promo_ids` → `SkillEditProposal.source_*_ids` → `review.metadata.source_edit_id`。

### 运行级归因（SkillRouter → RunTrace → CreditAssignment → Utility）

围绕 `ChatOrchestrator.handle` 的一条 observability 链。每个环节都只读 / 只补统计，不改 `SKILL.md`、不改 memory 文件、不绕 ReviewQueue。

```text
message ─► SkillRouter (deterministic, keyword-based)
        ├─ 记 RunTrace.router_decision
        └─ 若 top1 confidence ≥ medium → 预填 selected_skill
   │
   ▼
inner pipeline (safety / intent / capability / planner / executor)
   │
   ▼
populate_from_response → RunTrace
   │
   ▼
assign_credit → credit_assignment
   ├─ should_generate_learning_signal 闸：tool/env/policy 单独 → False
   ├─ SkillProfileStore.update_from_run（success / failure_skill / blocked）
   └─ MemoryUtilityStore.update_from_run（retrieved_memories 非空才更新）
   │
   ▼
RunTraceScanner（旁路按需）→ candidate signals → EvolutionScout
```

**RunTrace 字段（`.audit/runs/<run_id>.json`）**：

| 字段 | 含义 |
|---|---|
| `task / intent / selected_skill` | 输入 + 意图 + 最终 skill |
| `router_decision` | `ranked_skills / selected_skill / confidence / matched_reasons` |
| `retrieved_memories / applied_rules` | 命中的 memory / rule |
| `tool_calls[]` | `tool_name / status / error / error_class` |
| `policy_decisions[]` | SafeHarness 决策 + 工具注册检查 |
| `final_output_summary` / `outcome` | 输出前 240 字符；`success / failure / partial / blocked / unknown` |
| `credit_assignment` | 见下 |

**SkillRouter（`runtime/skill_router.py`，deterministic）** — `rank_skills(message, profiles)` 按 keyword/tag/name 匹配 + 历史成功率 + positive_credit 加成 − failure 惩罚 给出分数与 categorical confidence；置信度强依赖 keyword 命中，历史数据单独不能绑定无关请求。`self_improvement` 默认从候选中排除——低置信请求**回落到现有 executor 逻辑**，不强行绑定。

**SkillProfile（`runtime/skill_profile.py`）** — `skills/<skill>/profile.json` 持久化每个 skill 的 `success_count / failure_count / blocked_count / positive_credit_count / negative_credit_count / avg_eval_score / last_used_at` 加上路由用的 `tags / input_patterns / tool_dependencies`。缺失时从 SKILL.md 首段 + 名字 token 合成 fallback。`failure_source ∈ {skill_gap, rule_not_applied}` 才计 failure，其他失败源不动 counter。

**CreditAssignment（`runtime/credit_assignment.py`，deterministic）** — 8 类 `failure_source`：`environment / policy_block / tool_failure / rule_not_applied / bad_skill_selection / bad_retrieval / skill_gap / user_requirement_change`。成功运行同时记 4 类 `positive_credit`：`skill_selected_correctly / memory_helpful / rule_effective / tool_successful`。

> 关键护栏 `should_generate_learning_signal(credit)` —— skill-side blame ≥ medium 或任一 positive_credit 才返回 True；`tool_failure / environment / policy_block` 单独存在时一律 False。

**MemoryUtility（`runtime/memory_utility.py`）** — `.skills_memory/utility.jsonl` 累计每条 memory 的 `used / success / failure / positive_feedback / negative_feedback`。失败仅算 `bad_retrieval / rule_not_applied`；用户偏好短语 `以后这样 / 固定这样 / 记住` 计 positive，`不是这样 / 不要这样 / 错了` 计 negative。`utility_score = 0.40·success_rate + 0.30·positive_feedback_rate + 0.10·freshness − 0.20·failure_rate`，clamp 到 [0,1]。当前只产 stat，retrieval 路径未改。

**RunTraceScanner（`runtime/run_trace_scanner.py`，接入 Scout）** — 把符合上述护栏 + 主因 `∈ {skill_gap, rule_not_applied}`，或 positive_credit + 用户偏好短语的 run 转成候选 signal：`source_type=run_trace`、`source_ref=RUN-xxxxxxxx`。injection 类内容 → `quarantined=True`；`skill_gap` 且无 `selected_skill` → `target_skill=self_improvement` + `needs_human_label=true`，触发 `self_improvement_gate` 永远拒绝 promote。

REST：

| Method | Path | 作用 |
|---|---|---|
| GET | `/api/runs?limit=20&outcome=&intent=&should_emit=` | 倒序列出 run 摘要（含 `primary_failure_source` / `should_emit_learning_signal` / `credit recommended_action`）。支持按 outcome、intent 子串、should_emit 过滤 |
| GET | `/api/runs/{run_id}` | 完整 trace + credit_assignment + router_decision |

前端：`Self-Evolution → Runs` 选项卡（`web/ui/src/pages/RunsPage.jsx`）以表格呈现，点击一行展开完整 trace JSON。只读视图，不触发任何 PROMO 或 skill 改动。

### 决策可观测（Scout decision log）

每次 Scout 生成或更新 opportunity，`runtime/scout_decisions.py::ScoutDecisionStore` 追加一条 `DEC-xxxxxxxx`，含 `decision / alternative_decision / threshold_hit / binding_threshold / score_components / value_score / risk_score / evidence_quality / testability / outcome / outcome_history[]`。

**append-only-on-material-change** — re-scan 时，只有 decision 变化或任一 headline 分数移动超过 `MATERIAL_DELTA=0.02` 才追加新 `DEC-`；老记录标记 `superseded`，不污染统计。

**outcome 回写**：`pending → optimizer_proposed → review_created → approved / rejected → applied_eval_passed / applied_eval_failed / apply_failed`，新决策出现 → 老记录 `superseded`。通过 `review.metadata.source_opportunity_ids` 把 review 链路绑回 scout，无需改 ReviewQueue 核心 API。

### Side-Channel REST API

| Method | Path | 作用 |
|---|---|---|
| POST | `/api/evolution/scout/scan` | 扫描，返回新增数 |
| GET | `/api/evolution/scout/signals` | 列出 signal |
| GET | `/api/evolution/scout/opportunities[/{id}]` | 列出 / 单条 opportunity |
| GET / POST | `/api/evolution/scout/batches` | 列出 / 合批 |
| POST | `/api/evolution/optimizer/propose` | body `{batch_id \| opportunity_id}` |
| GET | `/api/evolution/optimizer/edits[/{id}]` | 列出 / 单条 edit |
| POST | `/api/evolution/optimizer/edits/{id}/validate` | 验证通过则创建 `skill.bounded_edit` review |
| GET | `/api/evolution/optimizer/rejected` | 被拒 edit |
| GET | `/api/evolution/scout/decisions[?opportunity_id=&decision=]` | 决策记录（默认排除 superseded） |
| GET | `/api/evolution/scout/decisions/stats?score_field=&threshold=[&decision=]` | 阈值命中率（命中 = `applied_eval_passed`） |

UI：**Self-Evolution → Side-Channel** tab，含 Opportunities / Batches / Edits / Rejected 四区。

## Chat / 实时查询

`runtime/chat_orchestrator.py` + `chat_intent.py` + `chat_executor.py` 把自然语言路由到 skill / tool / workspace 或实时查询。

实时查询路径（`web_research_query / financial_research_query / news_query`）：

```text
query → SEARCH_PROVIDER（Bailian / DashScope MCP → DuckDuckGo no-key fallback）
      → URL 列表 → crawl_urls_to_markdown（并行 + 早停：2 个 usable 后 cancel 其余）
      → OPENAI_MODEL summarize（≤ 9k chars，timeout 12s，max_tokens 600）
```

默认 `max_results=3`，并行抓取上限 3，每 URL 12s 超时。典型延时 3–6s。配置入口：UI **Settings**（写入 `.env` 并 in-process 应用）或直接编辑 `.env`。健康检查：`GET /api/settings/crawl4ai/health`。

### 知识库 Q&A（KB-aware chat）

聊天框 `📎 知识库 N/3` 选择器至多选 3 个 KB。请求带 `context.kb_ids=[...]` 时走 `_kb_qa` 分支：有 `index.json` 用 BM25 chunked，无则朴素拼接前 N KB；上下文按 30 KB 预算裁剪；"ONLY 用提供的 KB excerpts，不得编造"提示；OPENAI_MODEL 答题。trace 显示 `retrieval=bm25` + 每条 source 的 score / matched_terms。

KB 落盘 `.knowledge_bases/<kb_id>/{meta.json, index.json, files/...}`。本地上传或 GitHub `https://github.com/<owner>/<repo>` tarball 导入；路径越权防护、单文 ≤ 2 MB、单 KB ≤ 100 MB、二进制不入 Q&A 上下文。chunker 默认 800 字符目标 + 100 overlap，CJK 取 2-gram。

## Web Workbench

`web/server.py` 提供 FastAPI 后端，`web/ui/` 为 React + Vite 工作台。左侧导航 5 项：

- **Chat** — 自然语言入口，带"📎 知识库 N/3"选择器
- **Workspace** — 文件读写、命令运行
- **Assets** — Skills / Tools / Workflows / Memories / Knowledge bases / Eval cases
- **Self-Evolution** — 5 个 tab：候选 PROMO / 审批队列 / 版本与回滚 / 旁路进化 / **Runs**（RunTrace + credit 可视化）。顶部常驻 3 张 metric 卡（高风险待审 / 失败变更 / 审批保护变更）
- **Settings** — Provider 配置 + 模型连接（写入 `.env` 并 in-process 生效）

EN / 中文切换由 `LanguageProvider` 接管，本地存储记忆。所有列表统一走 `Paginator` 共享组件，每页 10 条。

## 项目结构

```text
harness_agent/
├─ harness/      # REPL、主循环、prompt、任务、消息、teammate
├─ runtime/      # ReviewQueue / Skill 加载 / memory / 主链路进化 / chat
│                # 旁路：evolution_scout · evolution_stores · skill_optimizer · evolution_llm · scout_decisions
│                # 工具：skill_eval_runner · knowledge_base · kb_index · web_search_provider · tool_registry
│                # 观测：run_trace · credit_assignment · run_trace_scanner
│                # 路由 & 统计：skill_router · skill_profile · memory_utility
├─ safety/       # SafeHarness 事件、决策、策略、guard、审计
├─ tools/        # OpenAI tool schema + handler 分发
├─ skills/       # Skill 定义、memory、eval cases
├─ web/          # FastAPI server + React/Vite 工作台
├─ docs/         # 设计文档 + architecture.svg
└─ tests/        # self_improvement · evolution pipeline · scout decisions · run_trace · kb · skill_eval_runner · web API
```

## 本地运行产物（建议加入 `.gitignore`）

`.tasks/` · `.team/` · `.transcripts/` · `.audit/`（含 `runs/RUN-*.json`） · `.reviews/` · `.skills_memory/`（全局 memory + `utility.jsonl` + scanner 状态）· `.skills_versions/` · `.evolution/` · `skills/*/memory/` · `skills/*/profile.json`。也别提交 `.env`。

## 安全边界

- `SKILL.md` 不会被自动静默修改、不会绕过 ReviewQueue、不会在缺 regression coverage 时 apply。
- `policy_candidate` 不直接写入 `SKILL.md`；secret / prompt injection / bypass approval / disable safety 不沉淀为长期规则。
- Scout 只读；Optimizer 仅 `add/replace/delete` 在 `## Memory-derived rules`；evaluator / scorer / regression gate 不能被 Scout 或 Optimizer 修改。
- LLM 输出经脱敏 + 注入检测，命中即回退 deterministic。
- 工具失败 / 环境问题 / 审批拦截**不会被错误沉淀为 skill 更新**：`should_generate_learning_signal` 在 RunTrace → LearningSignal 转换前拦截；`RunTraceScanner` / `SkillProfileStore.update_from_run` / `MemoryUtilityStore.update_from_run` 都再加一层（`tool_failure / environment / policy_block` 不进 Scout opportunity、不计 skill failure、不计 memory failure）。
- Scout `policy_gate`：cluster 命中 `policy_block / approval_block / Tool Call Blocked / Policy Enforcement Triggered / SafeHarness policy / protected file / policy_candidate / safety` 等 phrase/tag/source_type → 强制 `safety_review`，再高的 value/testability 也不能 promote。
- SkillRouter 默认从候选中排除 `self_improvement`：低置信请求回落到现有 executor 逻辑，不会被强行绑定。
- 所有 `SKILL.md` 进化必须可追溯：`memory → PROMO → regression REV → skill patch REV → approve → apply → version`。

## 常用验证

```bash
python -m unittest
python -m compileall harness runtime tools safety
echo q | python harness/agent_harness.py
cd web/ui && npm run build
```

修改 SafeHarness / ReviewQueue / Skill Memory / promotion / Regression Gate / Skill Evolution / 旁路 Scout / Optimizer 相关逻辑后，先跑上面这一组。更多架构细节见 `docs/HARNESS_DESIGN.md`、`docs/SAFEHARNESS_DESIGN.md`、`docs/RUNTIME_BACKEND_DESIGN.md`、`docs/UI_ACCEPTANCE.md`。
