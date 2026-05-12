
### 工作目录及说明

self-evolving
├─ harness
│  ├─ agent_harness.py
│  ├─ __init__.py
│  ├─ todos.py       
│  └─ subagent.py     
├─ tools
│  ├─ schemas.py
│  ├─ handlers.py
│  └─ base_tools.py
├─ runtime
│  └─ skill_loader.py
└─ .env

harness/agent_harness.py
负责：
1. 加载 .env
2. 初始化 OpenAI client
3. 定义目录
4. 初始化各个 manager
5. 构造 TOOLS / TOOL_HANDLERS
6. 执行 agent_loop

harness/background.py    后台任务
harness/messaging.py     队友消息总线
harness/team.py          多智能体队友运行循环
harness/file_tasks.py    持久任务
harness/compression.py   上下文压缩
harness/todos.py         Todo 管理
harness/prompt.py：      系统提示词
harness/loop.py：        主 Agent 循环
tools/base_tools.py      基础命令/文件工具
tools/schemas.py         OpenAI 工具 schema
tools/handlers.py        工具分发
runtime/skill_loader.py  Skill 加载


PROJECT_ROOT = 项目根目录
WORKDIR = Agent 执行工作目录，也指向项目根目录
TEAM_DIR = 队友状态目录
INBOX_DIR = 队友消息目录
TASKS_DIR = 持久任务目录
SKILLS_DIR = 技能目录
TRANSCRIPT_DIR = 压缩转录目录