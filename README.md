# Harness Agent

一个基于 OpenAI Chat Completions API 的 Agent Harness 示例项目。它把常见的 Agent 运行机制集中在一个轻量 Python 工程里：工具调用、文件读写、子代理、后台任务、持久任务板、队友消息总线、上下文压缩和 REPL 交互。

项目当前默认使用 `LocalBackend`，可以在单机环境继续运行；同时已经抽象出 Runtime Backend 层，方便后续替换为 Redis、PostgreSQL、Celery 或 Kubernetes Worker 等生产级基础设施。

## 核心能力

- **主 Agent 循环**：读取用户输入，调用模型，根据工具调用结果继续推理，直到输出最终回答。
- **工具系统**：内置命令执行、文件读取、文件写入、精确文本替换、Todo 更新等基础工具。
- **子代理**：可启动一次性的 focused subagent，用于独立探索或执行局部任务。
- **持久任务板**：任务以 JSON 文件保存在 `.tasks/`，支持创建、查看、更新、认领和依赖解除。
- **后台任务**：长耗时命令可放到后台线程运行，并在后续循环中回收结果。
- **多队友协作**：可启动持续运行的 teammate，通过 `.team/inbox/` 下的 JSONL 消息进行通信。
- **上下文压缩**：支持手动压缩和超过阈值后的自动压缩，完整转录会保存到 `.transcripts/`。
- **Skill 加载**：从 `skills/**/SKILL.md` 读取技能说明，并在需要时注入上下文。
- **Runtime Backend 抽象**：Manager 不再直接依赖本地文件系统、线程或进程内字典，而是通过后端接口访问运行时能力。

## Runtime Backend 架构

运行时能力被拆成五类接口，定义在 `runtime/backends/base.py`：

- `TaskStore`：持久任务板，负责创建、查询、更新、认领和查找未认领任务。
- `MessageStore`：消息总线，负责发送消息、读取收件箱和广播。
- `JobQueue`：后台任务队列，负责提交任务、查询状态和回收通知。
- `AgentRunner`：队友运行器，负责 teammate 生命周期和执行载体。
- `ReviewStore`：审批状态，负责 shutdown request、plan approval 等人工确认状态。

默认实现是 `runtime/backends/local.py` 中的 `LocalBackend`。它保留原来的单机行为：

- `LocalTaskStore` 使用 `.tasks/*.json`
- `LocalMessageStore` 使用 `.team/inbox/*.jsonl`
- `LocalJobQueue` 使用本地 daemon thread
- `LocalAgentRunner` 使用本地 daemon thread 和 `.team/config.json`
- `LocalReviewStore` 使用进程内 dict

`harness/file_tasks.py`、`harness/messaging.py`、`harness/background.py` 和 `harness/team.py` 现在只依赖这些抽象接口。OpenAI tool schema 和工具名称保持不变。

### 生产环境替换建议

本地线程、本地 JSON/JSONL 文件和进程内 dict 不适合生产环境，主要原因是：

- **不可横向扩展**：本地线程只存在于单个 Python 进程里，无法自然扩展到多机器或多副本。
- **状态不可靠**：进程退出会丢失后台任务、审批状态和未持久化的运行中状态。
- **并发一致性弱**：多个进程同时读写本地 JSON 文件容易产生竞争、覆盖或损坏。
- **缺少投递语义**：JSONL inbox 没有确认、重试、死信队列、消费组和可观测性。
- **任务调度能力有限**：本地线程缺少优先级、限流、隔离、重试、超时治理和资源配额。

推荐的生产替换方案：

- `TaskStore`：使用 PostgreSQL，任务表加事务、唯一约束、行级锁和状态索引。
- `MessageStore`：使用 Redis Streams、Kafka、NATS 或 PostgreSQL outbox，根据规模选择消息确认和重放能力。
- `JobQueue`：使用 Celery、RQ、Dramatiq、Temporal 或云厂商队列，配合独立 worker 和结果后端。
- `AgentRunner`：使用 Kubernetes Job、Deployment worker、容器沙箱或远程执行服务承载 teammate。
- `ReviewStore`：使用 PostgreSQL 或 Redis，并为审批请求增加过期时间、审计日志和幂等更新。

代码中已经预留 `RedisMessageStore`、`PostgresTaskStore`、`CeleryJobQueue`、`KubernetesAgentRunner` 的 TODO 类作为扩展入口。

## SafeHarness 安全运行时

SafeHarness 在普通 Agent Harness 之上增加了统一安全事件、策略决策、权限控制和审计追踪。它不是只检查用户输入，而是在 Agent 运行过程中的关键中间状态都生成 `RuntimeEvent`，再交给 `PolicyEngine` 判断。

当前最小可用版本已接入：

- `RuntimeEvent`：统一描述运行时事件。
- `PolicyDecision`：统一返回 `allow`、`block`、`sanitize`、`require_approval` 或 `warn`。
- `PolicyEngine`：串联规则 guard，任一 guard 阻断就停止执行。
- `InputGuard`：检测直接提示注入，例如要求忽略系统规则、泄露系统提示词、绕过安全策略。
- `ToolCallGuard`：检测高风险工具调用、敏感文件写入、外发秘密、危险 teammate prompt。
- `ToolResultGuard`：把工具结果视为不可信内容，并包装成 `<untrusted_tool_result>` 后再交还给模型。
- `PermissionGuard`：引入 capability 权限模型，检查工具调用是否超出当前 run 权限。
- `AuditLogger`：把事件和策略决策写入 `.audit/events.jsonl`。

### 已覆盖的风险类型

- **直接提示注入**：用户输入中要求忽略规则、泄露系统提示词、关闭安全检查。
- **间接提示注入**：工具结果中包含 “ignore previous instructions”“you are now”“call this tool”等指令诱导。
- **工具滥用**：危险 shell、后台命令、敏感文件写入、危险 teammate delegation。
- **工具篡改**：已预留 `tool.registry.load` 和 policy 文件位置，后续可加入 schema hash 和 handler 匹配检查。
- **记忆污染**：已预留 `memory.write.before`；当前 `load_skill` 会进入工具调用链路，后续可扩展 Skill 内容扫描。
- **权限升级**：工具绑定 capability，run 只允许调用已授权能力。

### 当前拦截点

`harness/loop.py` 已接入以下运行时事件：

- `user_input.received`
- `llm.request.before`
- `llm.response.after`
- `tool.call.before`
- `tool.execution.before`
- `tool.execution.after`
- `tool.result.before_model`

设计上还预留了以下事件类型，便于后续继续接入：

- `prompt.build.before`
- `task.create.before`
- `task.update.before`
- `message.send.before`
- `teammate.spawn.before`
- `memory.write.before`
- `skill.load.before`
- `tool.registry.load`

### 决策含义

- `allow`：允许继续执行。
- `warn`：记录风险但继续。
- `sanitize`：清洗或包装 payload 后继续，例如工具结果会被标记为不可信数据。
- `require_approval`：需要人工确认；当前最小实现会停止该工具调用并返回明确提示。
- `block`：阻断执行并把原因写入审计日志。

### 审计日志

本地模式下，所有安全事件和决策会写入：

```text
.audit/events.jsonl
```

审计日志会记录事件、决策、时间、actor、tool、风险类型、严重级别和原因。payload 只写摘要，并会尽量脱敏 `api_key`、`token`、`secret`、`password` 等内容。

### 后续扩展方向

- 接入 LLM Judge，对复杂提示注入、上下文越权和数据外发进行二次判断。
- 将 `safety/policies/*.yaml` 接入 `PolicyEngine`，支持不同安全等级。
- 增加企业安全策略中心，例如集中下发 allowlist、denylist、数据分级和审批规则。
- 对 `tool.registry.load` 增加工具 schema hash、handler 匹配、异常字段检查和注册审计。
- 对 `memory.write.before` 增加长期记忆写入审批，防止伪造授权、保存凭证或污染 skill。

## SafeHarness 策略模式

SafeHarness 的策略文件位于 `safety/policies/`。

- `default_policy.yaml`：本地开发默认策略
- `high_security_policy.yaml`：更严格的高安全策略，权限集合更小，阻断规则更多

可以通过 `SAFETY_POLICY` 选择策略。

PowerShell 示例：

```powershell
$env:SAFETY_POLICY="high_security"
python .\harness\agent_harness.py
```

如果未设置 `SAFETY_POLICY`，运行时会默认加载 `safety/policies/default_policy.yaml`。

当前主要差异：

- `default` 保留较完整的 lead 能力，但仍会拦截或审计 `bash`、`background_run`、`spawn_teammate` 等高风险工具。
- `high_security` 默认阻断未知工具；shell 命令只有命中策略 allowlist 才允许；修改 `AGENTS.md`、`docs/**`、`harness/**`、`safety/**`、`tools/**` 时会触发更严格的审查。
- 当前已经实现最小人工审批队列。`require_approval` 会创建 `.reviews/` 下的 pending review item，返回 `review_id`，并停止当前工具调用；不会自动修改目标文件。

## 目录结构

```text
self-evolving/
├── harness/
│   ├── agent_harness.py   # 程序入口：初始化 client、manager、tools，并启动 REPL
│   ├── loop.py            # 主 Agent 循环
│   ├── prompt.py          # 系统提示词构造
│   ├── subagent.py        # 一次性子代理
│   ├── team.py            # 持续运行的 teammate 管理
│   ├── messaging.py       # 基于 JSONL 文件的消息总线
│   ├── file_tasks.py      # 持久任务管理
│   ├── background.py      # 后台命令管理
│   ├── compression.py     # 上下文估算、微压缩、自动压缩
│   ├── todos.py           # 短期 Todo 管理
│   └── review_state.py    # 计划审批和关闭请求状态
├── tools/
│   ├── schemas.py         # 暴露给模型的工具 schema
│   ├── handlers.py        # 工具名到处理函数的分发
│   └── base_tools.py      # 命令执行与文件操作基础实现
├── runtime/
│   ├── skill_loader.py    # Skill 扫描与加载
│   └── backends/
│       ├── base.py        # Runtime Backend 抽象接口
│       ├── local.py       # LocalBackend 单机实现
│       └── __init__.py
├── .env.example           # 环境变量示例
└── README.md
```

LocalBackend 运行过程中会自动生成以下本地状态目录：

- `.tasks/`：本地任务文件
- `.team/`：本地队友配置和收件箱
- `.transcripts/`：上下文压缩前的完整对话转录

这些目录已在 `.gitignore` 中忽略。

## 快速开始

### 1. 准备环境

建议使用 Python 3.10+。

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt` 目前只保留最小运行依赖：

- `openai`
- `python-dotenv`

SafeHarness 策略加载目前仍使用内置轻量解析器，因此暂时不需要 `PyYAML`。

### 2. 配置环境变量

复制 `.env.example` 为 `.env`：

```bash
copy .env.example .env
```

然后填写你的模型服务配置：

```env
OPENAI_BASE_URL=http://your-openai-compatible-endpoint/v1
OPENAI_API_KEY=your-api-key
MODEL_ID=your-model-id
```

如果使用官方 OpenAI API，可以删除 `OPENAI_BASE_URL` 或将其留空，并填写可用的 `MODEL_ID`。

### 3. 启动 Agent

```bash
python harness/agent_harness.py
```

启动后会进入交互式 REPL：

```text
s_full >>
```

直接输入任务即可，例如：

```text
阅读这个项目并总结架构
```

输入 `q`、`exit` 或空输入可退出。

## REPL 内置命令

- `/compact`：手动压缩当前对话上下文
- `/tasks`：查看持久任务板
- `/team`：查看 teammate 状态
- `/inbox`：读取 lead 的消息收件箱
- `/reviews`：列出 pending 审批项
- `/review <id>`：查看审批详情
- `/approve <id>`：批准审批项，只把状态改为 `approved`
- `/reject <id>`：拒绝审批项

## 工具概览

主 Agent 可使用的工具包括：

- `bash`：在项目根目录执行 shell 命令
- `read_file`：读取工作区内文件
- `write_file`：写入工作区内文件
- `edit_file`：对文件中的精确文本做一次替换
- `TodoWrite`：维护短期 Todo 列表
- `task`：启动一次性子代理
- `load_skill`：加载 `skills` 目录中的技能
- `compress`：触发上下文压缩
- `background_run` / `check_background`：运行和检查后台任务
- `task_create` / `task_get` / `task_update` / `task_list` / `claim_task`：管理持久任务
- `spawn_teammate` / `list_teammates` / `send_message` / `read_inbox` / `broadcast`：管理队友和消息
- `shutdown_request` / `plan_approval`：队友关闭与计划审批流程

文件工具会通过 `safe_path` 限制访问范围，防止路径逃逸到项目目录之外。

## Skill 格式

项目会扫描 `skills/**/SKILL.md`。每个 Skill 可以带有简单的 front matter：

```markdown
---
name: example
description: Example skill description
---

这里是技能正文。
```

模型调用 `load_skill` 后，技能正文会以 `<skill>` 片段的形式进入上下文。

## 内置 Skill

### self_improvement

`skills/self_improvement/SKILL.md` 是跨 Skill 的学习管理器，用于将明确的学习信号结构化记录到相应 Skill 的 memory 中。

该 Skill 只处理具备长期价值的学习信号，包括命令失败、用户纠正、能力缺口、外部 API 失败、知识过时、更优方法、SafeHarness 事件以及重复出现的问题。写入 memory 前，信号必须先被归类为 `noise`、`local_tip`、`transferable_learning`、`missing_capability`、`safety_policy_candidate` 或 `regression_case`。

学习信号可以由模型根据 `self_improvement` 规则判断归属。代码侧负责 secret 脱敏、重复记录合并、归属元数据写入和 markdown 落盘；`EvolutionGate` 负责判断候选改进是进化、退化还是需要人工确认。真正修改 `SKILL.md`、`AGENTS.md`、安全策略、工具代码或 prompt 前，仍必须经过人工确认。

Agent 循环会在每轮模型回复以及工具调用结束后自动调用 `classify_and_record_learning_signal`。该 helper 接收最近对话上下文、最新工具事件和最新模型消息，先脱敏，再调用 LLM 分类，再在 `should_record=true` 时写入对应 memory。当前自动学习闭环已经使用这个统一 helper，不再是旧的“先 classify，再由外层手动 record”路径。每条自动 memory 都会写入 Attribution Reason 和 Attribution Confidence。

当前自动闭环统一走 `classify_and_record_learning_signal`。归属优先级与 `runtime/learning_signal.py` 保持一致：低置信度先写入 `self_improvement` 并标记 Needs Attribution Review；否则依次使用 classifier 返回的 `target_skill`、显式 `skill_name`、最近成功加载的 `last_loaded_skill`，最后回退到 `self_improvement`。提示注入、绕过审批、关闭安全等内容不会被写成长期学习。

当同一条 memory 通过去重逻辑累计到 `Occurrence Count >= 3` 时，系统会将其标记为 `recurring`，并生成或复用一个 `PromotionCandidate`，写入 `.skills_memory/PROMOTION_CANDIDATES.md`。候选记录包含来源 `record_id`、目标 Skill、建议变更摘要、目标文件、预期改进、风险类型、严重程度、状态、evaluation plan 和 rollback plan。也可以通过 `propose_memory_promotion(skill_name, record_id)` 手动生成同类候选。

`evaluate_evolution_candidate(candidate_id)` 可以对 promotion candidate 做首版 Evolution Gate 评估。它会估算 correctness gain、safety gain、regression risk、overblocking risk 和 cost increase，按规则给出 `reject`、`needs_human_review` 或 `approve`，并写入 `.audit/evolution.jsonl`。该工具只评估候选，不会自动应用 patch。

当评估结果是 `needs_human_review` 时，系统会自动创建 review item。涉及 `SKILL.md`、`AGENTS.md`、`safety/**`、`tools/**` 或 `harness/prompt.py` 的候选变更必须进入审批队列；`approve` 只代表建议通过或人工批准状态，不会自动修改这些文件。

`self_improvement` 不直接修改长期规则或关键运行文件。它不得记录 secret 原文，不得自动修改 `SKILL.md`、`AGENTS.md`、安全策略、工具 schema、工具 handler 或 harness prompt。涉及长期规则变更的内容只能先记录为 memory 或候选建议，后续修改必须经过用户明确确认。

## 注意事项

- 当前项目没有固定依赖文件，最小运行依赖是 `openai` 和 `python-dotenv`。
- `bash` 工具使用 `shell=True` 执行命令，只做了少量危险命令拦截；如果用于真实生产环境，应继续强化权限控制和沙箱隔离。
- teammate、后台任务和任务板都基于本地文件或线程实现，更适合作为教学和原型框架。
