# Harness Agent

Harness Agent 是一个本地优先的 Agent Harness 实验项目，当前核心能力是 **SafeHarness + Self-Evolving Skills**。

它不是让 Agent 无约束地自动修改自己，而是验证一条受控自进化链路：

```text
运行信号
→ Skill Memory
→ Promotion Candidate
→ ReviewQueue
→ Regression Coverage
→ Skill Patch
→ Approve / Apply
→ Skill Version
```

核心原则：

- memory 可以自动记录。
- PROMO 可以自动生成。
- patch 可以自动提议。
- 但 `SKILL.md` 的真实修改必须经过回归测试、人工审批、显式 apply 和版本登记。

## 当前能力

- **SafeHarness 安全运行时**：通过 `RuntimeEvent`、`PolicyDecision`、`PolicyEngine` 和 `AuditLogger` 在用户输入、模型请求、模型响应、工具调用、工具执行和工具结果返回前后做策略检查与审计。
- **ReviewQueue 人工审批队列**：`require_approval` 会创建 `.reviews/REV-*.json`，原始工具调用不会执行；队列已支持 `/approve` 和 `/apply`。
- **Skill Memory**：`self_improvement` 能从用户纠正、工具失败、能力缺口、安全事件和重复问题中识别可复用信号，写入 skill-scoped memory。
- **重复记忆合并和 PROMO**：相似 memory 会合并 `occurrence_count`，达到阈值后生成 `PROMO-xxxx`。
- **Promotion 浏览**：支持 `/promotions` 和 `/promotion <promo_id>` 查看候选。
- **Skill 进化流程向导**：`/evolve-skill <promo_id>` 根据当前状态创建或复用下一步 review，只提示下一步，不绕过审批。
- **Regression Gate**：没有 regression coverage 时，不允许 apply `SKILL.md` patch。
- **Skill Promotion**：`skill.promotion` review 的 patch preview 会把规则加入 `Memory-derived rules`，`/apply` 后才真正修改 `SKILL.md`。
- **Skill Evolution Registry**：`skill.promotion` apply 成功后会生成 `.skills_versions/<skill>/` 版本记录。
- **Runtime Backend 抽象**：默认使用 `LocalBackend`，并保留 `TaskStore`、`MessageStore`、`JobQueue`、`AgentRunner`、`ReviewStore` 等接口。

## 快速开始

建议使用 Python 3.10+。

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

编辑 `.env`：

```env
OPENAI_API_KEY=your-api-key
MODEL_ID=your-model-id
OPENAI_BASE_URL=
```

启动：

```powershell
python .\harness\agent_harness.py
```

进入 REPL 后直接输入任务即可。输入 `q`、`exit` 或空行退出。

## REPL 命令表

| 命令 | 说明 |
| --- | --- |
| `/compact` | 手动压缩当前上下文 |
| `/tasks` | 查看本地任务板 |
| `/team` | 查看 teammate 状态 |
| `/inbox` | 读取 lead inbox |
| `/reviews` | 列出 pending review |
| `/review <id>` | 查看 review 详情 |
| `/approve <id>` | 批准 review，生成 patch preview，不修改目标文件 |
| `/apply <id>` | 对 approved review 执行真实变更 |
| `/reject <id>` | 拒绝 review |
| `/promotions` | 列出 PROMO 候选 |
| `/promotion <promo_id>` | 查看 PROMO 详情 |
| `/evolve-skill <promo_id>` | Skill 进化流程向导；不绕过审批，不直接修改 `SKILL.md` |
| `/skill-versions <skill>` | 查看 skill 版本列表 |
| `/skill-version <skill> <version>` | 查看版本详情 |
| `/rollback-skill <skill> <version>` | 创建 rollback review，不直接修改文件 |

## SafeHarness 安全运行时

SafeHarness 在 Agent 执行链路中生成 `RuntimeEvent`，交给 `PolicyEngine` 评估，并通过 `AuditLogger` 写入审计日志。

核心对象：

- `RuntimeEvent`：统一描述用户输入、模型请求、模型响应、工具调用、工具执行和工具结果。
- `PolicyDecision`：策略评估结果。
- `PolicyEngine`：串联 input、tool call、permission、tool result 等 guard。
- `AuditLogger`：记录事件、决策、风险类型、原因和脱敏后的 payload 摘要。

决策类型：

| 决策 | 行为 |
| --- | --- |
| `allow` | 继续执行 |
| `warn` | 记录风险并继续执行 |
| `sanitize` | 清洗或包装 payload 后继续 |
| `require_approval` | 创建 review item，停止原始动作 |
| `block` | 阻断执行 |

在 `high_security` 下，敏感操作会进入 ReviewQueue。`require_approval` 不执行原始工具调用，而是生成 `REV-xxxx`，等待人工审批。

切换策略：

```powershell
$env:SAFETY_POLICY="high_security"
python .\harness\agent_harness.py
```

## ReviewQueue 人工审批队列

ReviewQueue 是本地人工审批队列。review item 保存在：

```text
.reviews/REV-*.json
```

patch preview 保存在：

```text
.reviews/patches/REV-*.diff
```

状态流转：

```text
pending  → approved: /approve
approved → applied:  /apply
pending  → rejected: /reject
```

审批语义：

- `/approve` 只把 review 标记为 `approved`，并生成 patch preview；不会修改目标文件。
- `/apply` 才会对 approved review 执行真实变更。
- `edit_file` / `write_file` 的 `/approve` 只生成 diff。
- `old_text=""` 的 `edit_file` 不生成伪装成可应用的 diff，而是提示 `Invalid edit_file preview`。
- `load_skill` 这类非文件工具不需要 patch preview；当前实现中 `/approve` 只批准，`/apply` 才真正执行 load，并设置 `last_loaded_skill`。再次加载同一 skill 会提示 already loaded，不重复创建 review。

## Skill Memory

`self_improvement` 会从用户纠正、工具失败、能力缺口、安全事件、重复问题中识别可复用信号。自动学习入口是：

```text
classify_and_record_learning_signal
```

写入位置：

```text
skills/<skill>/memory/LEARNINGS.md
skills/<skill>/memory/ERRORS.md
skills/<skill>/memory/FEATURE_REQUESTS.md
skills/<skill>/memory/POLICY_CANDIDATES.md
skills/<skill>/memory/REGRESSION_TESTS.md
```

自动学习会做归属、脱敏、去重和污染拦截。不应沉淀以下内容：

- secret、token、API key、密码。
- prompt injection。
- bypass approval。
- disable safety。
- ignore system。
- 一次性偏好或临时指令。

## Promotion Candidate

相似 memory 会合并并累计 `occurrence_count`。当 `occurrence_count >= 3` 时，会生成 `PROMO-xxxx`。

PROMO 保存在：

```text
.skills_memory/PROMOTION_CANDIDATES.md
```

PROMO 只是候选，不会自动修改 `SKILL.md`。`policy_candidate` 不应直接写入 `SKILL.md`，应走 policy review 或人工审查。

查看命令：

| 命令 | 说明 |
| --- | --- |
| `/promotions` | 列出 promotion candidates |
| `/promotion <promo_id>` | 查看单个 PROMO 详情 |

## Skill Evolution Flow

`/evolve-skill <promo_id>` 是 Skill 进化流程向导。

它根据当前状态推进：

1. 如果缺 regression coverage，创建 `skill.regression_case` review。
2. regression review 需要 `/approve` 和 `/apply`。
3. regression applied 后，再次 `/evolve-skill` 创建 `skill.promotion` review。
4. skill promotion review 需要 `/approve` 和 `/apply`。
5. skill promotion apply 成功后，记录 skill version。

明确边界：

- `/evolve-skill` 不会自动 apply。
- `/evolve-skill` 不会绕过 ReviewQueue。
- `/evolve-skill` 只是告诉用户下一步该执行什么。

## Regression Gate

每次 `SKILL.md` 进化前必须有 regression coverage。没有 coverage 时，`/apply` 一个 `skill.promotion` review 会拒绝执行。

Regression review：

- 类型：`skill.regression_case`
- 目标文件：`skills/<skill>/eval/cases.yaml`
- 每个 PROMO 至少应有 positive case 和 negative case。

Positive case 验证新规则生效。Negative case 验证新规则不污染其他任务。

示例：

```yaml
skill: markdown_writer
cases:
  - id: book_note_positive
    input: "请写《被讨厌的勇气》读书笔记"
    must_include:
      - "书名"
      - "核心观点"
      - "三条启发"
      - "行动清单"
    must_not_include: []
    target_rule: "When writing book-note style Markdown, prefer the structure: 书名 / 核心观点 / 三条启发 / 行动清单."
    source_promo_id: "PROMO-xxxx"

  - id: book_note_not_polluted
    input: "请写一个项目简介"
    must_include: []
    must_not_include:
      - "书名"
      - "核心观点"
      - "三条启发"
      - "行动清单"
    target_rule: "When writing book-note style Markdown, prefer the structure: 书名 / 核心观点 / 三条启发 / 行动清单."
    source_promo_id: "PROMO-xxxx"
```

## Skill Promotion

`skill.promotion` review 用于把经过回归覆盖和人工审批的规则写入 skill。

- 目标文件：`skills/<skill>/SKILL.md`
- patch preview 会加入 `Memory-derived rules`。
- `/approve` 只生成 preview，不修改文件。
- `/apply` 才真正修改 `SKILL.md`。
- 修改 `SKILL.md` 前必须通过 Regression Gate。

`policy_candidate` 不能直接进入 `SKILL.md`。

## Skill Evolution Registry

每次 `skill.promotion` review 成功 apply 后，系统会记录一个版本。

路径：

```text
.skills_versions/<skill>/versions.jsonl
.skills_versions/<skill>/<version>/SKILL.md
.skills_versions/<skill>/<version>/patch.diff
.skills_versions/<skill>/<version>/eval_result.json
```

命令：

| 命令 | 说明 |
| --- | --- |
| `/skill-versions <skill>` | 查看 skill 版本列表 |
| `/skill-version <skill> <version>` | 查看版本详情 |
| `/rollback-skill <skill> <version>` | 创建 rollback review，不直接修改文件 |

版本记录用于追溯：

```text
memory → PROMO → regression REV → skill patch REV → approve → apply → version
```

## 完整示例：markdown_writer

1. 用户多次纠正读书笔记格式：

```text
以后 markdown_writer 写读书笔记时，建议使用 书名 / 核心观点 / 三条启发 / 行动清单 的结构。
```

2. 系统生成：

```text
PROMO-F2C535BB
```

3. 用户执行：

```text
/evolve-skill PROMO-F2C535BB
```

4. 系统创建：

```text
REV-31D19BD3 type=skill.regression_case
```

5. 用户执行：

```text
/approve REV-31D19BD3
/apply REV-31D19BD3
```

6. 用户再次执行：

```text
/evolve-skill PROMO-F2C535BB
```

7. 系统创建：

```text
REV-530A7BEA type=skill.promotion
```

8. 用户执行：

```text
/approve REV-530A7BEA
/apply REV-530A7BEA
```

9. 系统输出：

```text
recorded skill version v0.1.1
```

10. 用户查看：

```text
/skill-versions markdown_writer
```

## 安全边界

- 不会自动静默修改 `SKILL.md`。
- 不会绕过 ReviewQueue。
- 不会在缺少 regression coverage 时 apply skill patch。
- 不会把 `policy_candidate` 直接写入 `SKILL.md`。
- 不会把 secret、prompt injection、bypass approval、disable safety 沉淀为长期规则。
- 所有 `SKILL.md` 进化必须可追溯到：

```text
memory → PROMO → regression REV → skill patch REV → approve → apply → version
```

## Runtime Backend

项目默认使用 `LocalBackend`，所有运行状态都落在本地目录中，适合原型、教学和安全机制实验。

后端接口已经抽象：

- `TaskStore`
- `MessageStore`
- `JobQueue`
- `AgentRunner`
- `ReviewStore`

这些接口把运行逻辑和本地文件、线程细节隔离开。后续可替换为 PostgreSQL、Redis、Celery、Kubernetes 等生产基础设施。

## 项目结构

```text
self-evolving/
├─ harness/      # REPL、主循环、prompt、任务、消息、后台任务和 teammate 管理
├─ runtime/      # backend 抽象、Skill 加载、Skill memory、ReviewQueue、进化流程
├─ safety/       # SafeHarness 事件、决策、策略、guard 和审计
├─ tools/        # OpenAI tool schema 和 handler 分发
├─ skills/       # Skill 定义、memory 和 eval cases
├─ docs/         # 设计文档、变更记录和历史 notes
└─ tests/        # self_improvement 等单元测试
```

## 本地目录与 .gitignore

这些目录是运行产物，不建议提交：

| 路径 | 内容 |
| --- | --- |
| `.tasks/` | 本地任务板 |
| `.team/` | teammate 配置与 inbox |
| `.transcripts/` | 压缩前对话记录 |
| `.audit/` | SafeHarness 审计日志 |
| `.reviews/` | ReviewQueue item 和 patch preview |
| `.skills_memory/` | 全局 memory 和 PROMO |
| `.skills_versions/` | Skill evolution version records and snapshots |
| `skills/*/memory/` | 单个 skill 的 memory |

建议 `.gitignore` 包含：

```gitignore
.env
.venv/
venv/
env/
evolve/
__pycache__/
*.py[cod]
.tasks/
.team/
.transcripts/
.audit/
.reviews/
.skills_memory/
.skills_versions/
skills/*/memory/
```

## 常用验证

```powershell
python -m unittest
python -m compileall harness runtime tools safety
"q" | python .\harness\agent_harness.py
```

修改 SafeHarness、ReviewQueue、Skill Memory、promotion、Regression Gate 或 Skill Evolution 相关逻辑后，优先运行上面的验证。更多架构说明见 `docs/README.md`、`docs/HARNESS_DESIGN.md`、`docs/SAFEHARNESS_DESIGN.md` 和 `docs/RUNTIME_BACKEND_DESIGN.md`。
