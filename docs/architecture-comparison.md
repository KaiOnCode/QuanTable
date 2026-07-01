# Architecture Comparison: Our Agent vs Claude Code

Generated 2026-07-01. Claude Code source: `/tmp/claude-code`. Our code: `agent/`.

---

## 1. Agent Loop

| Dimension | Claude Code (`query.ts`, 2057 lines) | Our (`loop.py`, 765 lines) | Gap |
|-----------|--------------------------------------|---------------------------|-----|
| **Loop structure** | `while(true)` with `State` immutable pattern | Generator-based `_query_loop` with `yield from` | Different style, both work |
| **State immutability** | Every iteration creates new `State` object. 10 fields tracked immutably. | `AgentLoopState` (frozen=True) **designed but never used**. Loop mutates `messages` list directly. | **GAP** — designed for immutability but bypassed |
| **Transition tracking** | `transition: Continue \| undefined` tracks WHY each iteration happened. 7 Continue types (next_turn, collapse_drain_retry, reactive_compact_retry, etc.) | `TransitionType` enum with 6 values — exists but **never wired into loop** | **GAP** — no transition tracking at runtime |
| **Termination** | `needsFollowUp = false` → comprehensive decision tree: prompt-too-long recovery → max_output_tokens recovery → API error check → stop hooks → token budget → `{ reason: 'completed' }` | `_check_termination()` = `bool(content.strip())` | **CRITICAL GAP** — 1 line vs 100+ lines of decision logic |
| **Recovery pipeline** | 3-stage for prompt-too-long (collapse drain → reactive compact → surface error). 2-stage for max_output_tokens (escalate 64k → multi-turn recovery up to 3). | None. Any error kills the loop. | **CRITICAL GAP** |
| **Model fallback** | Catches `FallbackTriggeredError`, clears partial results, strips thinking signatures, retries with fallback model | None | **GAP** |
| **Streaming tool execution** | `StreamingToolExecutor` starts tools **as they arrive** in the stream. Model is still generating while tools run. | Tools execute only AFTER full model response is received. | **GAP** — serial model→tools vs parallel |
| **Abort handling** | `getRemainingResults()` generates synthetic tool_results for in-flight tools. `yieldMissingToolResultBlocks()` for non-streaming. | None | **GAP** |
| **Error withholding** | Recoverable errors held back until ALL recovery paths attempted, then surfaced together | Errors surfaced immediately | Design choice |
| **Token budget** | Feature-gated. Checks output tokens vs budget. Under 90% → continue with `token_budget_continuation`. | Max iterations = 25 hard cap. | Different approach |
| **Max turns** | Configurable, not a hard-coded constant | `DEFAULT_MAX_ITERATIONS = 25` | Minor |

### Key takeaway

Our loop has the **shape** of Claude Code's (phases, needsFollowUp, dedup, circuit breaker) but misses the **depth**: recovery pipelines, transition tracking, streaming tool execution, and proper termination logic. The `AgentLoopState` immutability was designed correctly but the actual loop ignores it.

---

## 2. State Management

| Dimension | Claude Code | Our | Gap |
|-----------|-------------|-----|-----|
| **State type** | Mutable `State` type inside `queryLoop` | `AgentLoopState` dataclass (frozen=True) | We over-engineered — Claude Code uses mutable state in the loop |
| **State fields** | messages, toolUseContext, autoCompactTracking, maxOutputTokensRecoveryCount, hasAttemptedReactiveCompact, maxOutputTokensOverride, pendingToolUseSummary, stopHookActive, turnCount, transition | messages(tuple), iteration, transition, cost_usd, started_at, tool_call_counts | We track cost but not recovery state |
| **Actual usage** | State destructured at top of each iteration, new State at continue | `AgentLoopState` NOT used in `_query_loop`. Loop uses local `messages` list. | **GAP** — dead code |

---

## 3. Tool System

| Dimension | Claude Code | Our | Gap |
|-----------|-------------|-----|-----|
| **Tool type** | Plain object with 30+ methods | `BaseTool` ABC with `execute()` | Different philosophy (object vs class) |
| **Metadata** | name, aliases, searchHint, inputSchema (Zod), outputSchema, maxResultSizeChars, strict, isMcp, isLsp, shouldDefer, alwaysLoad, mcpInfo | `ToolMeta`: name, description, is_readonly, is_destructive, timeout, repeatable, category, cooldown_seconds, input_schema | We have 9 fields vs Claude Code's 15+ |
| **Lifecycle methods** | `call()`, `description()`, `prompt()`, `isEnabled()`, `isConcurrencySafe()`, `isReadOnly()`, `isDestructive()`, `interruptBehavior()`, `isSearchOrReadCommand()`, `isOpenWorld()`, `requiresUserInteraction()`, `validateInput()`, `checkPermissions()`, `getPath()`, `backfillObservableInput()`, `userFacingName()`, 7 render methods | `execute()`, `to_openai_schema()`, `validate_params()` | **CRITICAL GAP** — no per-tool prompt(), no validateInput(), no checkPermissions(), no interrupt behavior |
| **Prompt generation** | Each tool has `prompt()` method that generates its section of system prompt | `get_description_text()` generates static listing | **GAP** — tools can't self-describe to LLM |
| **Schema validation** | Zod schema + `validateInput()` returning `ValidationResult` | `input_schema` dict with manual validation in `validate_params()` | Adequate |
| **Permission model** | deny/allow/ask rules from 5 sources (cliArg, localSettings, userSettings, projectSettings, flagSettings). Auto-mode classifier. | 4 modes (default/plan/accept_edits/bypass). Basic check per tool. | **GAP** — no classifier, no per-source rules |
| **MCP integration** | Full MCP protocol mapping to Tool type. Resources, tools, prompts. | None | Not needed yet |
| **Tool discovery** | `getAllBaseTools()` + feature gates + MCP tools + SearchExtraTools for deferred tools | `__subclasses__()` auto-discovery | Simpler but adequate |
| **Registry** | Merged tool pool with dedup (built-in wins over MCP). Coordinator filtering. | Single `ToolRegistry` singleton. Category-based filtering. | Adequate for our scale |

---

## 4. Context Compression

| Dimension | Claude Code | Our | Gap |
|-----------|-------------|-----|-----|
| **Pipeline stages** | Snip → Microcompact → Context Collapse → Autocompact (4 stages) | L0 (tool_result_budget) → L1 (micro_compact) → L2 (collapse) → L3 (LLM summary) | Similar shape |
| **Predictive compaction** | Estimates if NEXT turn will overflow, compacts preemptively | Not implemented | **GAP** |
| **Collapse drain** | Releases staged collapses WITHOUT API call (free recovery) | Not implemented | **GAP** |
| **Reactive compact** | Triggered by 413 errors, costs one API call | Not implemented | **GAP** |
| **Tool result budget** | Per-result character limit | `apply_tool_result_budget()` — 50K max | Same |
| **Microcompact** | Clears old tool results, preserves non-whitelisted | `micro_compact()` — keeps last 3, 17-tool whitelist | Same concept |
| **LLM compression** | Autocompact: full summarization when approaching limits | `llm_compress()` — summarize head, protect tail 20K tokens | Adequate |

---

## 5. System Prompt

| Dimension | Claude Code | Our | Gap |
|-----------|-------------|-----|-----|
| **Sections** | 18 sections (Intro, System, Doing Tasks, Actions, Using Tools, Communication Style, Mode Persona, Session Guidance, Memory, Ant Override, Environment, Language, Output Style, MCP Instructions, Scratchpad, Summarize, Token Budget, Brief) | 4 sections (Identity, Task Rules, Tool Rules, Output Rules) + Skills (dynamic) | **GAP** — missing 14 sections |
| **Static/dynamic split** | Boundary marker (`__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__`) for cache optimization. Static has `global` cache scope. | Static cached by tool count. Dynamic (skills) per query. | Adequate approach, simpler |
| **Section caching** | `systemPromptSection()` registry with memoization, per-name cache, /clear invalidation | `_static_cache` dict, keyed by tool count | Adequate |
| **Mode support** | 5 built-in modes + custom modes. Mode persona injected as section. | None | **GAP** |
| **Memory prompt** | Full file-based memory instructions (types, when_to_save, how_to_use, frontmatter format). MEMORY.md content loaded. | Not implemented | **CRITICAL GAP** |
| **Environment info** | CWD, git status, platform, shell, OS version, model name, knowledge cutoff date | `build_user_context()` has date + tools. Not in system prompt. | **GAP** — missing git, platform, model info |
| **Output styles** | 3 built-in (Default, Explanatory, Learning) + custom | None | Not needed yet |
| **System-reminder pattern** | ~30 attachment types. Per-turn injection. `wrapInSystemReminder()`. `smooshSystemReminderSiblings()` merges adjacent. | One injection at start. **BUG: injected every turn instead of once.** `_needle_protection` extracts system text as tickers. | **BUG** — needs fix |
| **Tool usage guidance** | Detailed: "Core tools vs deferred tools". "Prefer dedicated tools over Bash". "Search before saying unknown". | Basic tool rules (6 rules) | **GAP** |
| **Output rules** | 12 detailed rules: write for person not console, don't narrate tools, cold pickup, one sentence summary, no "anything else?", file_path:line_number pattern | 10 rules adapted from Claude Code | Good |
| **Task rules** | 18 rules: scope creep, no unnecessary error handling, no premature abstractions, default to no comments, verify before reporting | 4 rules | **GAP** |
| **Action safety** | Reversibility, blast radius, risky operations checklist | Not implemented | **GAP** |

---

## 6. Skills System

| Dimension | Claude Code | Our | Gap |
|-----------|-------------|-----|-----|
| **Sources** | 5 sources (bundled, user/skills, project/.claude/skills, plugin, MCP) | 2 sources (bundled, user) | Adequate |
| **Bundled skills** | 17+ programmatic skills (TypeScript code, not files) | 76 SKILL.md files | Different approach |
| **File format** | `skill-name/SKILL.md` with YAML frontmatter (20 fields: name, description, when_to_use, paths, allowed-tools, arguments, model, context, agent, hooks, etc.) | `skills/bundled/<cat>/<name>/SKILL.md` with YAML frontmatter (~8 fields: name, description, category, version, prompt_type, tools) | **GAP** — missing when_to_use, paths (conditional), allowed-tools, context (fork), hooks |
| **Skill invocation** | `SkillTool`: validates input, checks permissions, TWO modes: inline (inject as messages) or forked (sub-agent) | `load_skill`: reads file, returns content | **GAP** — no forked execution |
| **Discovery** | TF-IDF search. Turn-0 search. Per-turn async prefetch. | Keyword matching. Select at system prompt build time. | **GAP** — no TF-IDF, no async discovery |
| **Conditional skills** | Skills with `paths` frontmatter activate when matching files are touched | Not implemented | **GAP** |
| **Dynamic skills** | `discoverSkillDirsForPaths()` — discovers new skills during session | Not implemented | **GAP** |
| **Compaction persistence** | Invoked skills serialized via `invoked_skills` attachment, restored after compaction | Not implemented | Not needed yet |
| **CRUD** | Write via FileWriteTool. No explicit save/delete tools. | `save_skill`, `delete_skill`, `search_skills`, `list_skills` tools | We have MORE tools than Claude Code |
| **MCP skills** | Skills from MCP servers via `skill://` resources | Not implemented | Not needed |

---

## 7. Memory System

| Dimension | Claude Code | Our | Gap |
|-----------|-------------|-----|-----|
| **Storage** | `~/.claude/projects/<hash>/memory/` directory. MEMORY.md index + individual .md files. | `WorkspaceMemory` — runtime-only counter. `_inject_attachments()` is a no-op placeholder. | **CRITICAL GAP** — entire system missing |
| **Types** | user, feedback, project, reference — each with specific `when_to_save` / `how_to_use` guidance | None | **GAP** |
| **Relevance** | Sonnet side-query selects top 5 relevant memories per turn. Injected as system-reminder. | None | **GAP** |
| **Staleness** | Age computation + freshness warnings for memories >1 day old | None | **GAP** |
| **Team memory** | Shared `team/` subdirectory. Two-pass containment checking for security. | None | Not needed |
| **Write path** | Model uses FileWriteTool directly. Memory dir pre-created. | None | **GAP** |

---

## 8. Query Planning

| Dimension | Claude Code | Our | Gap |
|-----------|-------------|-----|-----|
| **Planning** | No explicit planner. LLM decides based on system prompt. | `AnalysisPlan.from_query()` — regex-based extraction of tickers and data types. Plan injected into system prompt. | We have a planner that Claude Code doesn't have |
| **Verdict** | — | — | Our planner is fine but shouldn't be a crutch. Claude Code trusts the model more. |

---

## 9. Known Bugs (Our Code)

1. **System-reminder injected every turn** — `_build_user_context()` adds `<system-reminder>` as a separate user message. Should only inject once per session.

2. **`_needle_protection` extracts system text as user context** — When conversation is long, it reads the "first user message" which may be the system-reminder, then extracts nonsense keywords like "WAS", "ABOUT", "DATE".

3. **Dead evaluator messages** — "Still need: missing price for..." messages from removed evaluator still firing.

4. **`AgentLoopState` not used** — Designed as frozen dataclass with `next_iteration()`, `with_messages()`, but `_query_loop` uses plain mutable `messages` list directly.

5. **`TransitionType` never wired** — 6 transition types exist but loop never sets them.

---

## 10. Summary: What Matters Most

### Critical (fix now)
1. **Recovery pipeline** — any error kills the loop. Add: prompt-too-long recovery, max_output_tokens recovery, model fallback.
2. **Termination logic** — `bool(content)` is too simple. Claude Code has 100 lines of decision tree.
3. **Bug fixes** — system-reminder injection, needle_protection extraction, dead evaluator messages.
4. **Memory system** — entirely missing. Start with file-based memory using Claude Code's format.

### Important (fix next)
5. **Streaming tool execution** — tools should start as they arrive in stream, not after.
6. **State immutability** — either use `AgentLoopState` in the loop or delete it.
7. **Transition tracking** — wire `TransitionType` into the loop for recovery path auditing.
8. **Per-tool prompt()** — tools should self-describe, not rely on static registry listing.
9. **System prompt sections** — add Environment, Memory, and Actions sections.

### Nice-to-have (later)
10. **Predictive compaction** — estimate if next turn will overflow
11. **Mode personas** — different agent personalities
12. **Forked skill execution** — skills that run in sub-agents
13. **MCP integration** — external tool servers
14. **Permission classifier** — auto-mode with speculative execution
