# Harness Agent

Harness Agent 是一个本地优先的 Agent Harness 实验项目。它已经从普通的 OpenAI Chat Completions 工具调用框架，扩展为 **SafeHarness + Self-Evolving Skills** 实验运行时。

当前主链路是：

```text
用户交互 / 工具事件
→ Skill Memory
→ Promotion Candidate
→ /evolve-skill 流程向导
→ regression review
→ /approve + /apply regression
→ skill promotion review
→ /approve + /apply skill patch
→ Skill Evolution Registry 记录版本
```

重要边界：

- memory 可以自动记录。
- PROMO 可以自动生成。
- patch 可以自动提议。
- 但 `SKILL.md` 不会被静默自动修改。
- 修改 `SKILL.md` 必须经过 regression coverage、ReviewQueue、`/approve`、`/apply`、版本登记。
- 不允许把 prompt injection、secret、bypass approval、disable safety、ignore system 等内容沉淀为长期规则。

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

## SafeHarness 安全运行时

SafeHarness 在 Agent 执行链路中生成 `RuntimeEvent`，交给 `PolicyEngine` 评估，并通过 `AuditLogger` 写入审计日志。

核心对象：

- `RuntimeEvent`：统一描述用户输入、模型请求、模型响应、工具调用、工具执行和工具结果。
- `PolicyDecision`：策略评估结果。
- `PolicyEngine`：串联 input、tool call、permission、tool result 等 guard。
- `AuditLogger`：记录事件、决策、风险类型、原因和脱敏后的 payload 摘要。

当前决策类型：

| 决策 | 行为 |
| --- | --- |
| `allow` | 继续执行 |
| `warn` | 记录风险并继续执行 |
| `sanitize` | 清洗或包装 payload 后继续 |
| `require_approval` | 创建 review item，停止原始动作 |
| `block` | 阻断执行 |

在 `high_security` 下，敏感操作会进入 ReviewQueue。`require_approval` 不会执行原始工具调用，而是生成 `REV-xxxx`，等待人工审批。

切换策略：

```powershell
$env:SAFETY_POLICY="high_security"
python .\harness\agent_harness.py
```

## ReviewQueue 人工审批队列

本地 review item 保存在：

```text
.reviews/REV-xxxx.json
```

常用命令：

| 命令 | 说明 |
| --- | --- |
| `/reviews` | 列出 pending review |
| `/review <id>` | 查看 review 详情 |
| `/approve <id>` | 批准 review，生成 patch preview，不修改目标文件 |
| `/apply <id>` | review 已 approved 后，真正执行受支持的变更 |
| `/reject <id>` | 拒绝 review |

审批语义：

- `/approve` 只把状态改为 `approved`，并在需要时生成 preview。
- `/apply` 才会在 approved 后真正执行变更。
- `edit_file` / `write_file` 的 approve 会生成 `.reviews/patches/REV-xxxx.diff`。
- `old_text=""` 的 `edit_file` 会生成 `Invalid edit_file preview`，不会伪装成可应用 patch。
- `load_skill` review 不需要 patch preview；`/apply` 后才真正加载 skill 并设置 `last_loaded_skill`。

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

相似 memory 会合并，并累计 `Occurrence Count`。当 `occurrence_count >= 3` 时，会生成 `PROMO-xxxx`。

PROMO 写入：

```text
.skills_memory/PROMOTION_CANDIDATES.md
```

PROMO 只是候选，不会自动修改 `SKILL.md`。

浏览命令：

| 命令 | 说明 |
| --- | --- |
| `/promotions` | 列出 promotion candidates |
| `/promotion <promo_id>` | 查看单个 PROMO 详情 |

## /evolve-skill 流程向导

`/evolve-skill <promo_id>` 是 Skill 进化流程向导。它不会直接修改文件，也不会绕过人工审批。

它会根据当前状态推进：

```text
PROMO
→ regression review
→ approve/apply regression
→ skill promotion review
→ approve/apply skill patch
→ skill version recorded
```

状态行为：

- 缺 regression coverage 时，创建 `skill.regression_case` review。
- regression review 已 approved 时，提示运行 `/apply <review_id>`。
- regression review 已 applied 后，创建 `skill.promotion` review。
- skill promotion review 已 approved 时，提示运行 `/apply <review_id>`。
- skill patch 已 applied 后，提示进化完成。

## Regression Gate

每次 `SKILL.md` 进化前必须有 regression coverage。没有 coverage 时，`/apply` 一个 `skill.promotion` review 会拒绝执行。

Regression review：

- 类型：`skill.regression_case`
- 目标文件：`skills/<skill>/eval/cases.yaml`
- 每个 promotion 至少应有一个 positive case 和一个 negative case。

Positive case 用来验证新规则生效。Negative case 用来验证新规则不会污染其他任务。

示例：

```yaml
skill: markdown_writer
cases:
  - id: book_note_positive_PROMO_xxxx
    input: "请按读书笔记格式总结这本书"
    must_include:
      - "书名"
      - "核心观点"
      - "三条启发"
      - "行动清单"
    target_rule: "读书笔记应使用固定结构。"
    source_promo_id: "PROMO-xxxx"

  - id: book_note_negative_PROMO_xxxx
    input: "请写一个普通项目状态更新"
    must_not_include:
      - "书名"
      - "核心观点"
      - "三条启发"
      - "行动清单"
    target_rule: "读书笔记结构不应污染非读书笔记任务。"
    source_promo_id: "PROMO-xxxx"
```

## Skill Promotion

Skill promotion review：

- 类型：`skill.promotion`
- 目标文件：`skills/<skill>/SKILL.md`
- patch preview 会把规则加入 `Memory-derived rules` 段落。
- 只有 `/apply` approved review 后才真正修改 `SKILL.md`。

`policy_candidate` 不能直接进入 `SKILL.md`，应走 policy review 或人工审查。

## Skill Evolution Registry

每次 `skill.promotion` 成功 apply 后，会记录 skill version。

版本文件：

```text
.skills_versions/<skill>/versions.jsonl
.skills_versions/<skill>/<version>/SKILL.md
.skills_versions/<skill>/<version>/patch.diff
.skills_versions/<skill>/<version>/eval_result.json
```

版本记录用于追溯完整链路：

```text
memory
→ PROMO
→ regression REV
→ skill patch REV
→ approve
→ apply
→ version
```

命令：

| 命令 | 说明 |
| --- | --- |
| `/skill-versions <skill>` | 查看 skill 版本列表 |
| `/skill-version <skill> <version>` | 查看版本详情 |
| `/rollback-skill <skill> <version>` | 创建 rollback review，不直接修改文件 |

## 完整示例：markdown_writer 读书笔记格式

场景：用户多次纠正 `markdown_writer`，要求读书笔记固定使用 `书名 / 核心观点 / 三条启发 / 行动清单`。

1. 用户多次纠正输出格式。
2. Skill Memory 合并相似记录，`occurrence_count >= 3`。
3. 系统生成 promotion candidate：

```text
PROMO-F2C535BB
```

4. 查看候选：

```text
/promotion PROMO-F2C535BB
```

5. 启动流程向导，创建 regression review：

```text
/evolve-skill PROMO-F2C535BB
```

输出会提示新建的 `REV-xxxx`，例如：

```text
/review REV-AAAA1111
/approve REV-AAAA1111
/apply REV-AAAA1111
```

6. 批准并应用 regression review：

```text
/approve REV-AAAA1111
/apply REV-AAAA1111
```

7. 再次运行流程向导，创建 skill promotion review：

```text
/evolve-skill PROMO-F2C535BB
```

8. 批准并应用 skill review：

```text
/approve REV-BBBB2222
/apply REV-BBBB2222
```

9. 系统修改 `skills/markdown_writer/SKILL.md`，并记录版本 `v0.1.1`。

10. 查看版本：

```text
/skill-versions markdown_writer
/skill-version markdown_writer v0.1.1
```

## 常用命令表

| 命令 | 说明 |
| --- | --- |
| `/reviews` | 列出 pending review |
| `/review <id>` | 查看 review 详情 |
| `/approve <id>` | 批准 review，生成 preview，不修改目标文件 |
| `/apply <id>` | 对 approved review 执行受支持的变更 |
| `/reject <id>` | 拒绝 review |
| `/promotions` | 列出 PROMO 候选 |
| `/promotion <promo_id>` | 查看 PROMO 详情 |
| `/evolve-skill <promo_id>` | 推进 skill 进化流程 |
| `/skill-versions <skill>` | 查看 skill 版本列表 |
| `/skill-version <skill> <version>` | 查看版本详情 |
| `/rollback-skill <skill> <version>` | 创建 rollback review |
| `/compact` | 手动压缩当前上下文 |
| `/tasks` | 查看本地任务板 |
| `/team` | 查看 teammate 状态 |
| `/inbox` | 读取 lead inbox |

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

## 本地运行产物与 .gitignore

这些目录是运行产物，不建议提交：

```text
.tasks/
.team/
.transcripts/
.audit/
.reviews/
.skills_memory/
.skills_versions/
skills/*/memory/
```

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

修改 SafeHarness、ReviewQueue、Skill Memory、promotion、regression gate 或 skill evolution 相关逻辑后，优先运行上面的验证。更多架构说明见 `docs/README.md`、`docs/HARNESS_DESIGN.md`、`docs/SAFEHARNESS_DESIGN.md` 和 `docs/RUNTIME_BACKEND_DESIGN.md`。
