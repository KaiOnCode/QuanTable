# Agent Terminal — Claude Code 式功能实现计划

> 基于 `docs/research/06-claude-code-architecture-python-guide.md` 的架构分析
> 参考源码: `/tmp/claude-code/src/` (3560 文件)
> 最后更新: 2026-06-30 (重构: agent/ + quick_ask/ 分离)
> 总条目: 55 条

---

## 开发原则

1. **每完成一条, 立即测试, 测试通过再继续**
2. **经常回看 Claude Code 源码** (`docs/research/06-claude-code-architecture-python-guide.md` 和 `/tmp/claude-code/src/`)
3. **测试命令必须具体可执行** (curl / Python script / Bash)
4. 之前的结构可能过于简单，你随时可以修改整体的架构，做出大改动，让使用变得更好，让内容变得更完整，但是你需要注意改完必须做全量测试。
5. 注意出了具体的代码的测试，对于agent的能力也要实际的进行测试，比如用几个问题去尝试
---

## Phase 1: Agent Loop 核心重构 (P0, 12 条)

### 1.1 — 不可变 State 对象
- **文件**: `agent/state.py` (修改)
- **参考**: Claude Code `query.ts` State + transition 字段, `docs/research/06-...` 第一节 1.2
- **内容**:
  - 新建 `AgentLoopState` dataclass (frozen=True)
  - 字段: `messages: tuple`, `iteration: int`, `transition: str | None`, `cost_usd: float`, `started_at: float`
  - 添加 `next_iteration(**kwargs)` 方法 (使用 `dataclasses.replace`)
  - 添加 `TransitionType` 枚举: `TOOL_CALLS, TEXT_RESPONSE, COMPACT_TRIGGERED, ERROR_RECOVERY`
- **测试**: `PYTHONPATH=. uv run python3 -c "from agent.state import AgentLoopState, TransitionType; s = AgentLoopState(messages=()); s2 = s.next_iteration(transition=TransitionType.TOOL_CALLS); assert s2.iteration == 1; print('OK')"`

### 1.2 — TerminalReason 枚举
- **文件**: `agent/loop.py` (修改)
- **参考**: Claude Code `query.ts` 10 种 terminal reasons
- **内容**: 添加 `TerminalReason` 枚举, 包含: `COMPLETED, MAX_TURNS, MAX_BUDGET_USD, ABORTED_STREAMING, ABORTED_TOOLS, PROMPT_TOO_LONG, STOP_HOOK_PREVENTED, MODEL_ERROR, BLOCKING_LIMIT`
- **测试**: `PYTHONPATH=. uv run python3 -c "from agent.loop import TerminalReason; assert TerminalReason.COMPLETED.value == 'completed'; print('OK')"`

### 1.3 — 重构 query_loop 为 async generator
- **文件**: `agent/loop.py` (修改 `AgentLoop.run()`)
- **参考**: Claude Code `queryLoop()` async generator pattern
- **内容**:
  - 将当前 `run()` 中的 while loop 拆分为独立的 `_query_loop()` async generator
  - 每次迭代 yield `StreamEvent` (包含 text_delta, tool_call, tool_result, thinking_start, thinking_end, done)
  - 保持现有 SSE emit 兼容 (包装 async generator → SSE events)
- **测试**: 启动后端, `curl -N POST /api/agent/chat -d '{"message":"hello"}'`, 验证 SSE events 仍正常

### 1.4 — 5-phase 迭代结构
- **文件**: `agent/loop.py` (修改 `_query_loop()`)
- **参考**: Claude Code queryLoop 5 phases: pre-processing → streaming API → tool execution → attachment injection → termination check
- **内容**:
  - Phase 1: 调用 `_preprocess_messages()` (预留压缩 pipeline 入口)
  - Phase 2: 调用 `_call_model_streaming()` (已实现的 streaming LLM)
  - Phase 3: 调用 `_execute_tools()` (已实现的 `_execute_batch()`)
  - Phase 4: 调用 `_inject_attachments()` (初期空实现, 预留记忆/技能注入)
  - Phase 5: 调用 `_check_termination()` (抽取现有终止逻辑)
- **测试**: 发送 "分析 AAPL 价格" 请求, 验证完整 5-phase 流程

### 1.5 — Pre-processing pipeline 入口
- **文件**: `agent/loop.py` (新增 `_preprocess_messages()`)
- **参考**: Claude Code 5-layer 压缩 pipeline 入口
- **内容**:
  - 统一调用: `apply_tool_result_budget()` → `micro_compact()` → `check_autocompact()`
  - 每个函数接收 messages 返回 messages (纯函数风格)
  - 第一阶段: tool_result_budget 和 micro_compact 已有, 只需串联
- **测试**: `PYTHONPATH=. uv run python3 -c "from agent.loop import AgentLoop; loop = AgentLoop(AgentConfig()); msgs = [{'role':'tool','content':'x'*200000}]; result = loop._preprocess_messages(msgs); print(len(str(result)))"`

### 1.6 — 增强 tool_result_budget 截断
- **文件**: `agent/compression.py` (修改)
- **参考**: Claude Code `applyToolResultBudget`, maxResultSizeChars (~100K)
- **内容**:
  - 添加 `TOOL_RESULT_MAX_CHARS = 100_000` 常量
  - 添加 `apply_tool_result_budget(messages, max_chars)` 函数
  - 对每个 tool role message, 截断 content 到 max_chars
  - 保留前 max_chars//2 + 后 max_chars//2 字符 (头尾保留)
- **测试**: 创建 200K chars 的 tool result, 验证截断到 100K 且保留头尾

### 1.7 — 增强 micro_compact 白名单
- **文件**: `agent/compression.py` (修改)
- **参考**: Claude Code `microcompact`, `MICROCOMPACT_WHITELIST`
- **内容**:
  - 添加 `MICROCOMPACT_WHITELIST = {"read_file", "glob", "web_search", "web_fetch", "get_price", "get_indicators", "get_news", "get_fundamentals", "search_news", "search_symbol", "get_sentiment"}`
  - 修改 `micro_compact()`: 只清理白名单工具的结果, 非白名单工具保留
  - 保留最近 3 条 tool_result (已有逻辑)
- **测试**: 构造 10 条 tool messages (mix of whitelist/non-whitelist), 验证只清理白名单的

### 1.8 — 终止条件重构
- **文件**: `agent/loop.py` (新增 `_check_termination()`)
- **参考**: Claude Code 10 种 terminal reasons
- **内容**:
  - 抽取现有终止检查逻辑为独立方法
  - 检查: max_iterations, timeout, no_tool_calls, empty_content
  - 返回 `(is_terminal: bool, reason: TerminalReason)`
  - 在 _query_loop Phase 5 调用
- **测试**: 验证各终止条件正常触发

### 1.9 — transition 追踪
- **文件**: `agent/loop.py` (修改)
- **参考**: Claude Code State.transition field
- **内容**:
  - 每次迭代结束时设置 state.transition (TOOL_CALLS / TEXT_RESPONSE / ...)
  - 在日志/trace 中记录 transition
  - 添加防无限循环: 连续 3 次相同 transition → force stop
- **测试**: 运行一个会 loop 的请求, 验证 3 次相同 transition 后终止

### 1.10 — 错误恢复 withholding 模式
- **文件**: `agent/loop.py` (修改)
- **参考**: Claude Code error withholding pattern
- **内容**:
  - 可恢复错误 (413, max_output_tokens) 不立即抛给用户
  - 先尝试恢复 (compact → retry), 所有路径失败后再报错
  - 添加 `_attempt_recovery(error_type, messages)` 方法
- **测试**: 模拟 413 错误, 验证自动触发 compact 而不是直接报错

### 1.11 — Immutable messages 风格
- **文件**: `agent/loop.py` (修改)
- **参考**: Claude Code 不可变 state 更新
- **内容**:
  - 每次对 messages 的修改都返回新 list (不原地修改)
  - 使用 `messages = [*messages, new_msg]` 而非 `messages.append()`
  - 添加 copy-on-write 工具函数 `_append_message(messages, msg) -> list`
- **测试**: 验证原始 messages 不被修改

### 1.12 — Transcript 先写后调
- **文件**: `agent/loop.py` + `server/routes/agent.py` (修改)
- **参考**: Claude Code "transcript before API call" pattern
- **内容**:
  - 在调用 LLM 之前, 先把 user message 写入 session.json
  - 确保进程被 kill 后 `--resume` (即多轮对话) 可以恢复
  - 在 `run()` 中: user message 入队 → flush session.json → 进入 loop
- **测试**: 发送请求后立即 kill 进程, 验证 session.json 已包含 user message

---

## Phase 2: 工具系统升级 (P0, 10 条)

### 2.1 — build_tool 工厂函数
- **文件**: `agent/tools/base.py` (修改)
- **参考**: Claude Code `buildTool(name, description, execute, schema, options)`
- **内容**:
  - 添加 `build_tool(name, description, execute_fn, input_schema, *, is_readonly=True, is_destructive=False, timeout=30, repeatable=True)` 工厂函数
  - 返回 `BaseTool` 子类实例
  - 工厂内部处理 schema 生成 (从 input_schema dict 生成 OpenAI function schema)
- **测试**: 用 build_tool 创建一个简单工具, 验证 schema 正确生成

### 2.2 — 工具分类系统
- **文件**: `agent/tools/registry.py` (修改)
- **参考**: Claude Code 13 类工具分类
- **内容**:
  - 定义 `ToolCategory` 枚举: `FILE_SYSTEM, SEARCH, SHELL, WEB, FINANCIAL, ANALYSIS, WORKSPACE, MEMORY, SKILL, MCP, INTERACTION, SCHEDULING, WORKFLOW`
  - 每个工具通过 `ToolMeta.category` 归类
  - `list_by_category()` 按分类返回
  - `get_tools_by_category(category)` 方法
- **测试**: 验证所有现有工具都有分类

### 2.3 — StreamingToolExecutor
- **文件**: `agent/tools/streaming_executor.py` (新建)
- **参考**: Claude Code `StreamingToolExecutor` — LLM streaming 期间并行执行
- **内容**:
  - `StreamingToolExecutor` 类
  - `add_tool(tool_block)` — 注册工具执行 (立即启动)
  - `get_completed_results()` — 获取 streaming 期间完成的结果
  - `get_remaining_results()` — await 所有未完成的
  - `abort()` — 中断时为进行中的工具生成 synthetic error result
  - `max_concurrency=10` (只读) + serial (写) 执行策略
- **测试**: 创建 5 个 sleep tool, 验证并发执行; 创建 2 个 write tool, 验证串行

### 2.4 — 读写工具分离执行
- **文件**: `agent/loop.py` (修改 `_execute_batch()`)
- **参考**: Claude Code 并行读/串行写
- **内容**:
  - 在 `_execute_batch()` 中: 分离 read_only vs write 工具
  - Read: `asyncio.gather()` 并行 (用 StreamingToolExecutor)
  - Write: 严格串行 `for tc in write_calls: await execute(tc)`
- **测试**: 混合 3 个只读 + 2 个写工具, 验证执行顺序

### 2.5 — 权限决策框架
- **文件**: `agent/tools/permissions.py` (新建)
- **参考**: Claude Code 16-step permission pipeline
- **内容**:
  - `PermissionDecision` 枚举: `ALLOW, ASK, DENY`
  - `has_permissions_to_use_tool(tool, params, mode)` 函数
  - 检查链: deny_rules → allow_rules → tool_specific → mode_check
  - 初期: 只实现 allow/deny rule matching + plan mode (只读)
  - 预留 hook 入口
- **测试**: 验证 plan mode 下拒绝写工具

### 2.6 — 工具去重 + non-repeatable 增强
- **文件**: `agent/loop.py` (修改)
- **参考**: Claude Code tool call dedup + cooldown
- **内容**:
  - 增强现有去重: 添加基于 (tool_name, sha256(params_json)) 的去重 key
  - 添加 `cooldown_seconds` 支持: 工具在冷却期内不重复调用
  - 添加 `max_calls_per_turn` 限制 (e.g., get_price 最多 5 次/轮)
- **测试**: 发送 3 个完全相同的 get_price 请求, 验证只执行 1 次

### 2.7 — 工具结果截断与 preview
- **文件**: `agent/tools/base.py` 或 `agent/loop.py` (修改)
- **参考**: Claude Code tool result preview + content replacement
- **内容**:
  - 每个 tool result 存储: `{"status": "ok", "data": {...}, "preview": "...", "full_size": N, "truncated": bool}`
  - 大结果 (>10K chars) 截断为 preview (前 200 + 后 100 chars)
  - 完整结果写入 trace.jsonl blobs/
- **测试**: 返回 50K chars 结果的工具, 验证 preview 截断

### 2.8 — Bash/Shell 工具安全增强
- **文件**: `agent/tools/workspace.py` (修改 BashTool)
- **参考**: Claude Code Bash tool — AST parsing, 20+ injection patterns
- **内容**:
  - 添加命令注入检测: `$(...)`, `` `cmd` ``, `| sh`, `curl|bash`, `rm -rf /`
  - 添加危险命令警告: `chmod 777`, `mkfs`, `dd if=`, `> /dev/`
  - 添加路径安全: 限制在 workspace root 内
  - 添加 `is_readonly=False` 标记为写工具
- **测试**: 分别测试安全命令和危险命令, 验证拒绝危险命令

### 2.9 — 工具调用统计
- **文件**: `agent/loop.py` (修改)
- **参考**: Claude Code tool usage tracking
- **内容**:
  - 在 WorkspaceMemory 中记录: `tool_call_counts: dict[str, int]`
  - 每次调用累加
  - 在 done 事件中返回 `tool_stats: {name: count, ...}`
  - 在 session.json 中持久化
- **测试**: 运行多工具请求, 验证统计正确

### 2.10 — PostToolUse hook 预留
- **文件**: `agent/tools/hooks.py` (新建)
- **参考**: Claude Code PostToolUse/PostToolUseFailure hooks
- **内容**:
  - `HookEvent` 枚举: `PRE_TOOL_USE, POST_TOOL_USE, POST_TOOL_USE_FAILURE, PRE_COMPACT, STOP, SESSION_START...`
  - `HookManager` 类: 注册/执行 hooks
  - 初期空实现 (回调为空), 为后续扩展准备
  - 在 `_execute_batch()` 中调用 pre/post hooks
- **测试**: 注册一个 no-op hook, 验证被调用

---

## Phase 3: 上下文压缩增强 (P0, 6 条)

### 3.1 — 压缩 pipeline 串联
- **文件**: `agent/compression.py` (修改)
- **参考**: Claude Code 5-layer 压缩串行 pipeline
- **内容**:
  - 添加 `compress_pipeline(messages, config)` 统一入口
  - 串联: budget → micro → collapse → autocompact
  - 每个阶段返回 `(messages, CompressionResult)` 元组
  - `CompressionResult` 包含: `layer_applied, tokens_before, tokens_after, details`
- **测试**: 构造 50K token messages, 验证 pipeline 各层触发

### 3.2 — Predictive autocompact
- **文件**: `agent/compression.py` (修改)
- **参考**: Claude Code predictive autocompact — 预估本轮增长, 提前压缩
- **内容**:
  - 在 LLM 调用前: `predicted_tokens = current_tokens + expected_growth`
  - `expected_growth` = 上一轮增长量的移动平均
  - 如果 `predicted_tokens > threshold`, 先 compact 再调 LLM
- **测试**: 模拟快速增长的对话, 验证提前触发 compact

### 3.3 — Compact boundary 机制
- **文件**: `agent/compression.py` (修改)
- **参考**: Claude Code `SystemCompactBoundaryMessage`
- **内容**:
  - 每次 compact 后插入 `{"role": "system", "content": "[Compacted at ...]"}`
  - 后续操作只处理 boundary 之后的消息 (非 boundary 前的)
  - 添加 `get_messages_after_boundary(messages)` 辅助函数
- **测试**: compact 后验证 boundary message 存在

### 3.4 — Transcript 备份
- **文件**: `agent/loop.py` (修改)
- **参考**: Claude Code full transcript save before compaction
- **内容**:
  - L3 compact 前自动保存完整 messages 到 `run_dir/transcripts/`
  - 文件名: `transcript_YYYYMMDD_HHMMSS.jsonl`
  - 使用 TraceWriter 写入
- **测试**: 触发 compact, 验证 transcript 文件存在

### 3.5 — Tool pair integrity fix
- **文件**: `agent/compression.py` (修改 `_fix_tool_pairs`)
- **参考**: Claude Code fix tool_call/tool_result pairing after compact
- **内容**:
  - 增强现有 `_fix_tool_pairs()`: 确保每个 tool_result 有对应 tool_call
  - 移除 orphaned tool_result (无匹配 tool_call)
  - 移除 orphaned tool_call (无匹配 tool_result) → 或补充 synthetic error
- **测试**: 构造 orphaned messages, 验证清理正确

### 3.6 — 压缩事件通知前端
- **文件**: `agent/loop.py` (修改)
- **参考**: Claude Code compact boundary + UI notification
- **内容**:
  - 添加 SSE event `compact_boundary` 通知前端
  - 携带 `before_tokens, after_tokens, layer: "L1"|"L2"|"L3"`
  - 前端在 conversation 中显示 "📦 Context compacted" 标记
- **测试**: 触发 compact, 验证 SSE event 发出

---

## Phase 4: 记忆系统 (P1, 8 条)

### 4.1 — 4-Type 记忆模型
- **文件**: `memory/models.py` (修改)
- **参考**: Claude Code 4-type taxonomy: user, feedback, project, reference
- **内容**:
  - 修改 `MemoryRecord`: 添加 `memory_type` 字段 (USER/FEEDBACK/PROJECT/REFERENCE)
  - 添加 `MemoryType` 枚举
  - 每种类型有不同存储目录: `data/memory/{type}/`
- **测试**: 创建各类型记忆, 验证分目录存储

### 4.2 — MEMORY.md 索引文件
- **文件**: `memory/indexer.py` (新建)
- **参考**: Claude Code `MEMORY.md` — 入口索引, 每对话加载
- **内容**:
  - 生成/更新 `data/memory/MEMORY.md`
  - 每条记忆一行: `- [Title](file.md) — one-line hook`
  - 200 行 / 25KB 上限, 超出截断
  - 每次 `_build_default_system_prompt()` 加载
- **测试**: 创建 5 条记忆, 验证 MEMORY.md 正确生成

### 4.3 — 记忆自动召回注入
- **文件**: `agent/loop.py` (修改 `_build_default_system_prompt()`)
- **参考**: Claude Code Sonnet side query for relevant memories (≤5)
- **内容**:
  - 从用户消息提取关键词
  - 用关键词匹配 MEMORY.md 中的记忆标题
  - 将匹配的记忆 (最多 5 条) 注入 system prompt
  - 格式: "## Relevant Memories\n- memory_title: key_point"
- **测试**: 发送与已存储记忆相关的查询, 验证记忆被注入

### 4.4 — 记忆去重 + 更新
- **文件**: `memory/store.py` (修改)
- **参考**: Claude Code memory dedup by title/tag
- **内容**:
  - `remember()` 前检查同名记忆是否存在
  - 存在则更新 content + updated_at
  - 不存在则创建
  - 添加 `update_memory(id, content)` 方法
- **测试**: 创建同名记忆两次, 验证第二次是更新而非重复

### 4.5 — Context 级记忆文件 (CLAUDE.md 模式)
- **文件**: `agent/context_builder.py` (新建)
- **参考**: Claude Code CLAUDE.md loading (6 级优先级)
- **内容**:
  - 加载顺序: managed > user > project > local
  - 项目根目录 `CLAUDE.md` 自动读取
  - 注入 system prompt
  - 支持 `@include` 指令 (最多 3 层递归)
- **测试**: 项目根已有 CLAUDE.md, 验证被加载

### 4.6 — 记忆文件 MCP 工具 (remember/recall/forget)
- **文件**: `agent/tools/memory_tools.py` (新建)
- **参考**: Claude Code memory management via tools
- **内容**:
  - `RememberTool`: 创建/更新记忆 (name, content, type)
  - `RecallTool`: 按名称召回记忆
  - `ForgetTool`: 删除记忆
  - 注册到 ToolRegistry
- **测试**: Agent 对话中说 "记住: AAPL 的 PE 通常在 25-30 之间", 验证记忆被创建

### 4.7 — Session Memory (自动对话笔记)
- **文件**: `agent/session_memory.py` (新建)
- **参考**: Claude Code SessionMemory — forked subagent writes notes
- **内容**:
  - 每轮对话后, 用 LLM 生成简要笔记 (forked subagent)
  - 存储到 `run_dir/session_notes.md`
  - 下一轮对话时注入 system prompt
- **测试**: 完成一轮对话, 验证 session_notes.md 有内容

### 4.8 — 记忆漂移防御
- **文件**: `agent/loop.py` (修改)
- **参考**: Claude Code `TRUSTING_RECALL_SECTION` — 告诉 AI 验证记忆
- **内容**:
  - 在注入记忆时附带提示: "Memory claims may be outdated — verify against current data before recommending"
  - 嵌入 system prompt 的记忆区域
- **测试**: 注入过期记忆 (e.g., "AAPL PE=15"), 验证 AI 从实际数据验证

---

## Phase 5: Skills 系统增强 (P1, 6 条)

### 5.1 — Skill trigger 自动加载
- **文件**: `skills/loader.py` (修改)
- **参考**: Claude Code skill `when_to_use` / trigger patterns
- **内容**:
  - SKILL.md frontmatter 添加 `triggers: [keyword1, keyword2]` 字段
  - 用户消息匹配 trigger 时自动加载 skill (无需 LLM 调 load_skill)
  - 匹配规则: 任意 trigger keyword 出现在用户消息中
- **测试**: 创建 test skill with `triggers: ["测试"]`, 发送 "测试一下", 验证 skill 被自动注入

### 5.2 — Skill 执行模式分离 (inline vs fork)
- **文件**: `agent/loop.py` (修改)
- **参考**: Claude Code `context: inline | fork`
- **内容**:
  - `context: inline` (默认): skill prompt 注入主会话 UserMessage
  - `context: fork`: 启动隔离子 agent (独立 token 预算)
  - SKILL.md frontmatter 添加 `context: inline|fork` 字段
- **测试**: 创建 fork mode skill, 验证子 agent 独立运行

### 5.3 — Skill 工具白名单
- **文件**: `skills/loader.py` + `agent/loop.py` (修改)
- **参考**: Claude Code `allowed-tools` in SKILL.md
- **内容**:
  - SKILL.md frontmatter 已有 `tools:` 字段
  - 加载 skill 时解析 `tools:` 为工具白名单
  - 在 skill 执行期间限制 agent 只能使用白名单工具
- **测试**: 创建 skill with `tools: [get_price]`, 验证 agent 不能调其他工具

### 5.4 — Skill 使用统计
- **文件**: `skills/usage.py` (新建)
- **参考**: Claude Code skill tracking, Voyager skill refinement pattern
- **内容**:
  - 记录 skill 使用次数、成功率、最后使用时间
  - 存储到 SQLite `skill_usage` 表
  - 前端技能浏览器显示使用统计
  - 低成功率 skill 标记为 deprecated
- **测试**: 多次 load_skill("candlestick"), 验证统计数据递增

### 5.5 — Skill `$ARGUMENTS` 替换
- **文件**: `skills/loader.py` (修改)
- **参考**: Claude Code `$ARGUMENTS` substitution in skill prompt
- **内容**:
  - 在 skill body 中支持 `$ARGUMENTS` 占位符
  - `load_skill(name, arguments)` — 加载时替换占位符
  - 例如: "分析 $ARGUMENTS 的技术面" → "分析 AAPL 的技术面"
- **测试**: load_skill with arguments, 验证占位符被替换

### 5.6 — 技能推荐 (end-of-response)
- **文件**: `agent/loop.py` (修改 system prompt)
- **参考**: Claude Code skill suggestion hints
- **内容**:
  - System prompt 添加: "分析完成后建议 1-3 个相关技能供用户探索"
  - Agent 在回答末尾生成类似: `**相关技能**: load_skill("candlestick")`
  - 前端识别并渲染为可点击按钮
- **测试**: 分析 AAPL, 验证回答中包含技能建议

---

## Phase 6: System Prompt 优化 (P1, 5 条)

### 6.1 — 分块 System Prompt (string[] 风格)
- **文件**: `agent/loop.py` (修改 `_build_default_system_prompt()`)
- **参考**: Claude Code SystemPrompt as string[] for per-chunk caching
- **内容**:
  - 将 system prompt 拆分为逻辑块: intro + tools + skills + guidelines + memory
  - 每个块独立生成
  - 返回 `list[str]` 而非单个 string
  - 发送给 LLM 时用 "\n\n".join()
- **测试**: 验证生成的 system prompt 分块正确

### 6.2 — 静态/动态 content 分离
- **文件**: `agent/loop.py` (修改)
- **参考**: Claude Code `SYSTEM_PROMPT_DYNAMIC_BOUNDARY`
- **内容**:
  - 静态块 (不变): intro, guidelines, how-to-work
  - 动态块 (每轮变化): tools list, skills list, memory injection, date
  - 标记 `DYNAMIC_BOUNDARY = "---DYNAMIC---"`
  - 静态块只在 session 开始时构建一次
- **测试**: 验证动态块随不同轮次变化, 静态块不变

### 6.3 — Context Injection 位置优化
- **文件**: `agent/loop.py` (修改)
- **参考**: Claude Code system context → system prompt tail, user context → first user message
- **内容**:
  - System context (git status, 环境信息) → system prompt 尾部
  - User context (CLAUDE.md, 日期, 记忆) → 第一条 user message (用 `<system-reminder>` 包裹)
  - 不混在一起
- **测试**: 验证 CLAUDE.md 内容出现在 user message 而非 system prompt

### 6.4 — Token budget 意识注入
- **文件**: `agent/loop.py` (修改 system prompt)
- **参考**: Claude Code token budget awareness
- **内容**:
  - 在 system prompt 中提示当前 context window 大小
  - 工具描述按使用频率排序 (常用工具在前)
  - Skills 列表按相关性排序 (不是字母序)
- **测试**: 验证 tools list 按 category 和 frequency 排序

### 6.5 — Needle-in-haystack 保护
- **文件**: `agent/loop.py` (修改)
- **参考**: Claude Code tail protection after compact
- **内容**:
  - 每次 LLM 调用前, 确保关键数据 (ticker, date, position) 在最后 2 条消息中
  - 如果不在: 追加一条 user message 重复关键信息
  - 对抗 "lost in the middle" 问题
- **测试**: 构造长对话 (50+ turns), 验证后几轮的 ticker 信息仍然正确

---

## Phase 7: 会话管理增强 (P1, 4 条)

### 7.1 — JSONL transcript 格式
- **文件**: `agent/trace.py` (修改) + `server/routes/agent.py` (修改)
- **参考**: Claude Code JSONL one-json-per-line transcript
- **内容**:
  - 每条消息/事件独立一行 JSON
  - 支持增量追加 (非整体覆写)
  - 支持 chunked 读取 (1MB chunks)
  - 50MB 读取上限 (防止大文件 OOM)
- **测试**: 长时间对话后, 验证 transcript.jsonl 格式正确可逐行解析

### 7.2 — Session resume 增强
- **文件**: `server/routes/agent.py` (修改)
- **参考**: Claude Code session restore pipeline
- **内容**:
  - 增强 `_reconstruct_history()`: 恢复 cost state, file snapshots
  - 添加 `restore_session(session_id)` — 完整恢复流程
  - 支持 `?resume=true` query param in SSE endpoint
- **测试**: 中断对话 → 用 resume 恢复, 验证上下文完整

### 7.3 — 全局 prompt history
- **文件**: `server/routes/agent.py` (修改)
- **参考**: Claude Code `~/.claude/history.jsonl` — 原始 prompt 记录
- **内容**:
  - 所有 user message 追加到 `data/agent-runs/_history.jsonl`
  - 文件锁保证并发安全
  - 100 entries per project 限制
  - 支持 up-arrow 回放
- **测试**: 发送 5 条不同消息, 验证 history.jsonl 记录完整

### 7.4 — Fork session 支持
- **文件**: `agent/loop.py` (新增 `run_forked_agent()`)
- **参考**: Claude Code `runForkedAgent()` — 隔离子 agent, 共享 prompt cache
- **内容**:
  - `run_forked_agent(instruction, max_turns=5, tools=None) -> str`
  - 独立 messages list (不污染主会话)
  - 独立 token budget
  - 结果以 system message 返回主会话
  - 用于: skill fork mode, session memory generation, compact summary
- **测试**: 在主对话中 fork 一个子 agent "分析 AAPL 基本面", 验证结果返回且主会话不变

---

## Phase 8: UI/前端增强 (P1, 4 条)

### 8.1 — Compact boundary 显示
- **文件**: `frontend/app/agent/page.tsx` (修改)
- **参考**: Claude Code compact notification in UI
- **内容**:
  - 收到 `compact_boundary` SSE event 时
  - 在聊天中插入分隔线: "📦 Context compacted (before: X tokens, after: Y tokens)"
  - 灰显, 不可点击, 纯信息
- **测试**: 触发 compact, 验证前端显示分隔线

### 8.2 — 工具调用详情面板增强
- **文件**: `frontend/app/agent/page.tsx` (修改)
- **参考**: Claude Code TUI tool display with timing + status
- **内容**:
  - 工具卡片显示更多信息: 开始时间, 耗时, 是否 truncated
  - 展开后显示: full args JSON (pretty-printed), preview, full result (折叠)
  - 颜色编码: read=蓝, write=橙, error=红
- **测试**: 运行多工具请求, 验证面板信息完整

### 8.3 — 打字机效果增强 (streaming cursor)
- **文件**: `frontend/app/agent/page.tsx` (修改)
- **参考**: Claude Code TUI streaming display
- **内容**:
  - 当前已有 streaming text + cursor
  - 增强: 显示 estimated tokens consumed / context window
  - 添加 "正在思考..." 的详细状态文字 (e.g., "正在读取 AAPL 价格数据...")
- **测试**: 发送请求, 验证状态文字随工具调用更新

### 8.4 — 对话导航 (jump to compact point)
- **文件**: `frontend/app/agent/page.tsx` (修改)
- **参考**: Claude Code compact boundary navigation
- **内容**:
  - 侧边栏/header 显示 compact 点标记
  - 点击跳转到对应位置
  - 方便长对话导航
- **测试**: 触发 compact 后, 验证导航标记可用

---

## Phase 9: 测试与验证 (每次开发都要做)

### T1 — Regression test: agent 基本对话
```bash
curl -X POST http://localhost:8000/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Say hello in Chinese"}' \
  --max-time 30 2>&1 | grep "event: done"
```
期望: `event: done` 出现, 无 error event

### T2 — Regression test: 多工具调用
```bash
curl -X POST http://localhost:8000/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Get AAPL price and news"}' \
  --max-time 60 2>&1 | grep -c "event: tool_done"
```
期望: >=2 个 tool_done events

### T3 — Regression test: 流式输出
```bash
curl -X POST http://localhost:8000/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Write a 100-word analysis of TSLA"}' \
  --max-time 60 2>&1 | grep -c "event: thinking_delta"
```
期望: >10 个 thinking_delta events

### T4 — Regression test: 多轮对话
```bash
# 第一轮
SID=$(curl -s -X POST http://localhost:8000/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What is AAPL price?"}' \
  --max-time 30 2>&1 | grep "session_id" | head -1 | grep -o '"session_id":"[^"]*"' | cut -d'"' -f4)

# 第二轮 (用同一个 session_id)
curl -X POST http://localhost:8000/api/agent/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"Compare with MSFT\",\"session_id\":\"$SID\"}" \
  --max-time 30 2>&1 | grep "event: done"
```
期望: 两轮都返回 done

### T5 — 前端编译检查
```bash
cd frontend && npm run build 2>&1 | grep -E "(✓|error)"
```
期望: ✓ Compiled successfully
