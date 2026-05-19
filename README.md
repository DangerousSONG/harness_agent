# Harness Agent

Harness Agent 是一个本地优先的 **SafeHarness + Self-Evolving Skills** 实验系统。

它不是让 Agent 无约束地自动修改自己，而是验证一条“受控自进化 Skill”链路：

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

七个核心角色：

1. SafeHarness 负责拦截高风险动作。
2. ReviewQueue 负责人审。
3. Skill Memory 负责沉淀经验。
4. PROMO 负责提出进化候选。
5. `/evolve-skill` 负责推进流程。
6. Regression Gate 防止退化。
7. Skill Evolution Registry 负责版本追溯。

核心原则：

- memory 可以自动记录。
- PROMO 可以自动生成。
- patch 可以自动提议。
- 但 `SKILL.md` 的真实修改必须经过回归测试、人工审批、显式 apply 和版本登记。

## 当前能力

- **SafeHarness 安全拦截**：基于 `RuntimeEvent`、`PolicyDecision`、`PolicyEngine` 和 `AuditLogger` 做运行时策略判断与审计。
- **ReviewQueue 人工审批**：`require_approval` 会创建 `.reviews/REV-*.json`，原始工具调用不会执行；队列已支持 `/approve` 和 `/apply`。
- **Skill Memory 经验沉淀**：`self_improvement` 能从用户纠正、工具失败、能力缺口、安全事件和重复问题中识别可复用信号。
- **重复记忆合并和 PROMO**：相似 memory 会累计 `occurrence_count`，达到阈值后生成 `PROMO-xxxx`。
- **`/evolve-skill` 流程向导**：根据当前状态创建或复用下一步 review，只提示下一步，不绕过审批。
- **Regression Gate 防退化**：没有 regression coverage 时，不允许 apply `SKILL.md` patch。
- **Skill Evolution Registry 版本追溯**：`skill.promotion` apply 成功后会生成 `.skills_versions/<skill>/` 版本记录。
- **Runtime Backend 抽象**：默认使用 `LocalBackend`，并保留 `TaskStore`、`MessageStore`、`JobQueue`、`AgentRunner`、`ReviewStore` 等接口。

## 系统主流程

```mermaid
flowchart TD
    A[User / Agent Runtime Signals] --> B[SafeHarness Runtime Checks]
    B -->|allow| C[Tool / Skill Execution]
    B -->|require_approval| D[ReviewQueue<br/>REV-xxxx]

    D --> E[/review]
    E --> F[/approve<br/>Generate Patch Preview]
    F --> G[/apply<br/>Apply Approved Change]

    C --> H[Skill Memory<br/>LEARNINGS / ERRORS / FEATURE_REQUESTS / POLICY_CANDIDATES / REGRESSION_TESTS]
    H --> I{Repeated Pattern?<br/>Occurrence Count >= 3}
    I -->|yes| J[PROMO<br/>Promotion Candidate]
    I -->|no| H

    J --> K[/evolve-skill PROMO]
    K --> L{Regression Coverage Exists?}
    L -->|no| M[skill.regression_case Review]
    M --> F
    G --> N[eval/cases.yaml Applied]

    L -->|yes| O[skill.promotion Review]
    N --> K
    O --> F
    G --> P[Update Active SKILL.md]
    P --> Q[Skill Evolution Registry<br/>.skills_versions]
```

SafeHarness 负责在工具调用、文件修改、Skill 加载等关键点进行策略判断。如果策略要求审批，动作不会立即执行，而是进入 ReviewQueue。Skill Memory 会自动沉淀可复用经验，但不会直接修改 `SKILL.md`。当相似经验重复出现时，系统生成 PROMO。`/evolve-skill` 会把 PROMO 推进到回归测试和 Skill Patch 审批流程。Regression Gate 保证没有回归测试覆盖时不能修改 `SKILL.md`。只有 `/apply` approved `skill.promotion` review 后，`SKILL.md` 才会真正被修改。Skill Evolution Registry 会记录版本、快照、patch、`eval_result`，实现可追溯和可回滚。

## 七层职责表

| Layer | Responsibility | Output | Does Not Do |
| --- | --- | --- | --- |
| SafeHarness | 拦截高风险动作，执行策略判断 | `allow` / `warn` / `sanitize` / `require_approval` / `block` | 不决定长期 Skill 规则 |
| ReviewQueue | 承接人工审批 | `REV-xxxx`、patch preview、approved/applied status | `/approve` 不直接修改文件 |
| Skill Memory | 沉淀运行经验和用户纠正 | `LEARNINGS.md`、`ERRORS.md`、`FEATURE_REQUESTS.md` 等 | 不直接修改 `SKILL.md` |
| PROMO | 把重复经验提升为进化候选 | `PROMO-xxxx` | 不自动 apply |
| `/evolve-skill` | 推进进化流程 | regression review 或 `skill.promotion` review | 不绕过审批 |
| Regression Gate | 防止进化退化 | `eval/cases.yaml` coverage | 没有 coverage 不允许 apply `SKILL.md` |
| Skill Evolution Registry | 记录版本和审计链路 | `.skills_versions/<skill>/...` | 不是运行时默认加载源 |

## Active Skill Version

The active skill is always loaded from `skills/<skill>/SKILL.md`.
`.skills_versions/<skill>/` stores historical snapshots and audit records, but it is not the default runtime loading source.
A rollback must create and apply a review that writes the selected snapshot back to `skills/<skill>/SKILL.md`.

也就是说：

- Runtime 默认加载的 Skill 来源是 `skills/<skill>/SKILL.md`。
- `skills/<skill>/SKILL.md` 是当前生效版本。
- `load_skill("markdown_writer")` 默认读取 `skills/markdown_writer/SKILL.md`。
- 如果某次 `/apply` `skill.promotion` `REV-xxxx` 成功修改了 `skills/markdown_writer/SKILL.md`，后续加载的就是这个最新生效版本。
- `.skills_versions/markdown_writer/v0.1.1/SKILL.md` 是快照，不会被 runtime 自动作为默认加载源。
- 如果要回滚，必须通过 rollback review 把历史快照写回 `skills/<skill>/SKILL.md`。
- 当前系统不做多版本动态加载，不默认支持 `load_skill --version`。
- 版本库用于追溯，不用于替代 active `SKILL.md`。

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
| `/reviews` | 列出 pending review |
| `/review <id>` | 查看 review 详情 |
| `/approve <id>` | 批准 review 并生成 patch preview，不修改目标文件 |
| `/apply <id>` | 对 approved review 执行真实变更 |
| `/reject <id>` | 拒绝 review |
| `/promotions` | 列出 PROMO 候选 |
| `/promotion <promo_id>` | 查看 PROMO 详情 |
| `/evolve-skill <promo_id>` | Skill 进化流程向导；不绕过审批，不直接修改 `SKILL.md` |
| `/skill-versions <skill>` | 查看 skill 版本列表 |
| `/skill-version <skill> <version>` | 查看版本详情 |
| `/rollback-skill <skill> <version>` | 创建 rollback review，不直接修改文件 |
| `/compact` | 手动压缩当前上下文 |
| `/tasks` | 查看本地任务板 |
| `/team` | 查看 teammate 状态 |
| `/inbox` | 读取 lead inbox |

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

`/approve` 和 `/apply` 的区别：

```text
/approve = approve the review and generate patch preview. It does not modify target files.
/apply = apply an approved review. This is the step that may modify target files.
```

中文语义：

- `/approve` 是“同意进入预览态”，生成 diff。
- `/apply` 是“看过 diff 后确认落盘”。
- 对 `SKILL.md`、`eval/cases.yaml`、`tools/`、`safety/` 等文件，必须先 approve，再 apply。
- 不建议合并两步，因为 `SKILL.md` 会影响后续 Agent 行为。
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

```text
/promotions
/promotion <promo_id>
```

## Skill Evolution Flow

`/evolve-skill <promo_id>` 是流程向导，不是自动进化。

它会：

1. 检查 PROMO 是否适合 skill evolution。
2. 如果缺 regression coverage，创建 `skill.regression_case` review。
3. regression review apply 后，再次执行 `/evolve-skill`。
4. 如果已有 coverage，创建 `skill.promotion` review。
5. skill promotion review approve/apply 后，修改 active `SKILL.md`。
6. apply 成功后记录 skill version。

明确边界：

- 全程不会绕过 ReviewQueue。
- 全程不会自动静默修改 `SKILL.md`。
- `/evolve-skill` 只是告诉用户下一步该执行什么。

简洁示例：

```text
/promotions
/evolve-skill PROMO-F2C535BB

# system creates regression review
/approve REV-31D19BD3
/apply REV-31D19BD3

/evolve-skill PROMO-F2C535BB

# system creates skill promotion review
/approve REV-530A7BEA
/apply REV-530A7BEA

/skill-versions markdown_writer
```

## Regression Gate

每次 Skill 进化前，必须有 regression coverage。

如果没有，`/apply REV-skill` 会被拒绝，并提示：

```text
missing regression coverage for PROMO-xxxx
```

Regression review：

- 类型：`skill.regression_case`
- 目标文件：`skills/<skill>/eval/cases.yaml`
- 每个 PROMO 至少需要 positive case 和 negative case。

Positive case 验证新规则应该生效。Negative case 验证新规则不污染其他任务。

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

`skill.promotion` review 用于把经过回归覆盖和人工审批的规则写入 active skill。

- 目标文件：`skills/<skill>/SKILL.md`
- patch preview 会加入 `Memory-derived rules`。
- `/approve` 只生成 preview，不修改文件。
- `/apply` 才真正修改 `SKILL.md`。
- 修改 `SKILL.md` 前必须通过 Regression Gate。

`policy_candidate` 不能直接进入 `SKILL.md`。

## Skill Evolution Registry

当 `skill.promotion` review 成功 `/apply` 后，系统会记录一个版本。

路径：

```text
.skills_versions/<skill>/versions.jsonl
.skills_versions/<skill>/<version>/SKILL.md
.skills_versions/<skill>/<version>/patch.diff
.skills_versions/<skill>/<version>/eval_result.json
```

版本记录用于追溯：

```text
memory → PROMO → regression REV → skill patch REV → approve → apply → version
```

支持命令：

```text
/skill-versions <skill>
/skill-version <skill> <version>
/rollback-skill <skill> <version>
```

Skill Evolution Registry 是版本登记模块，不是一个 Skill。它不参与 runtime skill loading；active runtime skill 仍然是 `skills/<skill>/SKILL.md`。

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

这些目录是运行产物，通常不建议提交到 Git：

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

## 核心结论

Harness Agent implements controlled self-evolving skills.

It can automatically discover reusable experience, but it cannot silently rewrite its own skills. A skill change must pass through:

```text
Skill Memory
→ PROMO
→ Regression Review
→ Skill Promotion Review
→ /approve
→ /apply
→ Skill Version Record
```

The active skill is always `skills/<skill>/SKILL.md`; version snapshots under `.skills_versions/` are for audit and rollback.

## 常用验证

```powershell
python -m unittest
python -m compileall harness runtime tools safety
"q" | python .\harness\agent_harness.py
```

修改 SafeHarness、ReviewQueue、Skill Memory、promotion、Regression Gate 或 Skill Evolution 相关逻辑后，优先运行上面的验证。更多架构说明见 `docs/README.md`、`docs/HARNESS_DESIGN.md`、`docs/SAFEHARNESS_DESIGN.md` 和 `docs/RUNTIME_BACKEND_DESIGN.md`。
