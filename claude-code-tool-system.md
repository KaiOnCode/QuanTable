# Claude Code Tool System — Comprehensive Analysis

## 1. How Many Tools Are There?

Claude Code has **60+ built-in tools**, organized in `/tmp/claude-code/packages/builtin-tools/src/tools/`. The exact count depends on feature flags (Bun's `feature()` dead-code elimination) and environment variables. All tools are listed below by category:

### File System Tools (5)
| Tool | Name | Description | R/W |
|------|------|-------------|-----|
| **Read** (FileReadTool) | `Read` | Read files, images, PDFs, Jupyter notebooks. Supports offset/limit. Auto-detects binary vs text. Handles images with token-budget compression. | Read |
| **Write** (FileWriteTool) | `Write` | Write/create files with content. Creates parent directories automatically. | Write |
| **Edit** (FileEditTool) | `Edit` | Search/replace editing of files. Uses `old_string`/`new_string` with optional `replace_all`. Validates that old_string exists (and is unique or replace_all is set). Staleness detection. | Write |
| **NotebookEdit** (NotebookEditTool) | `NotebookEdit` | Edit Jupyter notebooks (`.ipynb`) — replace/insert/delete cells. | Write |
| **Glob** (GlobTool) | `Glob` | Fast file pattern matching. Uses glob patterns like `**/*.ts`. | Read |

### Search Tools (2)
| Tool | Name | Description | R/W |
|------|------|-------------|-----|
| **Grep** (GrepTool) | `Grep` | Search file contents with regex (delegates to ripgrep). Supports content/files_with_matches/count modes, context lines, glob filtering, multiline. Cap: 250 results default, 0 = unlimited. | Read |
| **SearchExtraTools** | `SearchExtraTools` | Enables deferred-loading tool discovery. Models that don't receive all tools upfront use this to discover tools by name/keyword. | Read |

### Shell/Command Tools (3)
| Tool | Name | Description | R/W |
|------|------|-------------|-----|
| **Bash** (BashTool) | `Bash` | Execute arbitrary shell commands. EXTENSIVE security: sandboxing, permission rules, command injection detection, destructive command warnings, AST-based parsing, path constraints, sed validation, safe wrapper stripping. | Write |
| **PowerShell** (PowerShellTool) | `PowerShell` | PowerShell equivalent of Bash. Similar security model. Requires explicit user permission in auto mode. | Write |
| **REPL** (REPLTool) | `REPL` | Ant-only interactive REPL environment. Wraps primitive tools in a VM context. | Write |

### Web/Network Tools (3)
| Tool | Name | Description | R/W |
|------|------|-------------|-----|
| **WebFetch** (WebFetchTool) | `WebFetch` | Fetch web content and process with a prompt. Uses Tavily extract API by default. Handles redirects. Preapproved hosts list. 15-minute self-cleaning cache. | Read |
| **WebSearch** (WebSearchTool) | `WebSearch` | Search the web via multiple adapters (Tavily, Brave, Bing, Exa, custom API). Returns structured results with titles and links. Domain filtering. Requires web search adapter configured. | Read |
| **WebBrowser** (WebBrowserTool) | `WebBrowser` | Full browser automation (feature-flagged: `WEB_BROWSER_TOOL`). | Read |

### Agent/Task Tools (13)
| Tool | Name | Description | R/W |
|------|------|-------------|-----|
| **Agent** (AgentTool) | `Task` | Spawn sub-agents. Supports built-in agent types (general-purpose, explore, plan, verify, claude-code-guide) and user-defined custom agents. Sub-agents get filtered tool sets. | Write |
| **TaskCreate** | `TaskCreate` | Create a new task in the task system. | Write |
| **TaskGet** | `TaskGet` | Get task details. | Read |
| **TaskUpdate** | `TaskUpdate` | Update task status/details. | Write |
| **TaskList** | `TaskList` | List tasks. | Read |
| **TaskStop** | `TaskStop` | Stop a running task/sub-agent (aliased from KillShell). | Write |
| **TaskOutput** | `TaskOutput` | Get task output. | Read |
| **TodoWrite** | `TodoWrite` | Write/update a structured todo list. UI renders in a side panel. | Write |
| **Goal** | `Goal` | Goal tracking (feature-flagged: `GOAL`). | Write |
| **ExitPlanMode** | `ExitPlanModeV2` | Exit plan mode and optionally execute the plan. | Write |
| **EnterPlanMode** | `EnterPlanMode` | Enter plan mode. | Write |
| **VerifyPlanExecution** | `VerifyPlanExecution` | Verify plan execution (env: `CLAUDE_CODE_VERIFY_PLAN`). | Read |
| **ReviewArtifact** | `ReviewArtifact` | Review artifacts (feature-flagged: `REVIEW_ARTIFACT`). | Read |

### Interaction Tools (4)
| Tool | Name | Description | R/W |
|------|------|-------------|-----|
| **AskUserQuestion** | `AskUserQuestion` | Ask the user a structured question. Blocks for user response. | Write |
| **SendMessage** | `SendMessage` | Send a message to another peer/team member (UDS channels). | Write |
| **ListPeers** | `ListPeers` | List available peers (feature-flagged: `UDS_INBOX`). | Read |
| **SendUserFile** | `SendUserFile` | Send files to the user (feature-flagged: `KAIROS`). | Write |

### Scheduling/Remote Tools (5)
| Tool | Name | Description | R/W |
|------|------|-------------|-----|
| **CronCreate** | `CronCreate` | Create scheduled cron jobs. | Write |
| **CronDelete** | `CronDelete` | Delete scheduled cron jobs. | Write |
| **CronList** | `CronList` | List scheduled cron jobs. | Read |
| **RemoteTrigger** | `RemoteTrigger` | Trigger remote agents (feature-flagged: `AGENT_TRIGGERS_REMOTE`). | Write |
| **Monitor** | `Monitor` | Monitor tool (feature-flagged: `MONITOR_TOOL`). | Read |

### Skill/Plugin Tools (3)
| Tool | Name | Description | R/W |
|------|------|-------------|-----|
| **Skill** (SkillTool) | `Skill` | Invoke a skill (slash command). Skills are markdown-defined domain-specific instructions that extend Claude's capabilities. | Write |
| **DiscoverSkills** | `DiscoverSkills` | Discover available skills (feature-flagged: `EXPERIMENTAL_SKILL_SEARCH`). | Read |
| **Execute** (ExecuteTool) | `Execute` | Execute a deferred tool by name. Used with SearchExtraTools for tool discovery. | Write |

### Memory/Context Tools (3)
| Tool | Name | Description | R/W |
|------|------|-------------|-----|
| **LocalMemoryRecall** | `LocalMemoryRecall` | Recall from local memory. Reads project memory files. | Read |
| **CtxInspect** | `CtxInspect` | Inspect context (feature-flagged: `CONTEXT_COLLAPSE`). | Read |
| **Snip** | `Snip` | Snip history (feature-flagged: `HISTORY_SNIP`). | Write |

### Workflow/Config Tools (7)
| Tool | Name | Description | R/W |
|------|------|-------------|-----|
| **Config** | `Config` | Modify Claude Code configuration (ant-only). | Write |
| **EnterWorktree** | `EnterWorktree` | Enter a git worktree for isolation. | Write |
| **ExitWorktree** | `ExitWorktree` | Exit a git worktree. | Write |
| **Workflow** | `Workflow` | Workflow scripts (feature-flagged: `WORKFLOW_SCRIPTS`). | Write |
| **Brief** | `Brief` | Brief tool for context management. | Read |
| **SubscribePR** | `SubscribePR` | Subscribe to PR notifications (feature-flagged: `KAIROS_GITHUB_WEBHOOKS`). | Write |
| **PushNotification** | `PushNotification` | Send push notifications (feature-flagged: `KAIROS_PUSH_NOTIFICATION`). | Write |

### Team Tools (3)
| Tool | Name | Description | R/W |
|------|------|-------------|-----|
| **TeamCreate** | `TeamCreate` | Create a team (lazy-required to break circular deps). | Write |
| **TeamDelete** | `TeamDelete` | Delete a team. | Write |
| **SuggestBackgroundPR** | `SuggestBackgroundPR` | Suggest background PRs (ant-only). | Read |

### MCP Bridge Tools (4)
| Tool | Name | Description | R/W |
|------|------|-------------|-----|
| **MCPTool** | `mcp__*` | Dynamic bridge for MCP (Model Context Protocol) tools. All MCP tools are accessed through this namespace. | Varies |
| **ListMcpResources** | `ListMcpResources` | List MCP resources. | Read |
| **ReadMcpResource** | `ReadMcpResource` | Read an MCP resource. | Read |
| **McpAuth** | `McpAuth` | Handle MCP authentication. | Write |

### Special/Ant-Only Tools (6+)
| Tool | Name | Description | R/W |
|------|------|-------------|-----|
| **TestingPermission** | `TestingPermission` | Test-only permission tool (NODE_ENV=test only). | Read |
| **OverflowTest** | `OverflowTest` | Overflow testing (feature-flagged: `OVERFLOW_TEST_TOOL`). | Read |
| **Sleep** | `Sleep` | Sleep/delay (feature-flagged: `PROACTIVE` or `KAIROS`). | Write |
| **LSP** | `LSP` | Language Server Protocol integration (env: `ENABLE_LSP_TOOL`). | Read |
| **TerminalCapture** | `TerminalCapture` | Terminal capture (feature-flagged: `TERMINAL_PANEL`). | Read |
| **Tungsten** | `Tungsten` | Tungsten tool (ant-only, monorepo tool). | Write |
| **VaultHttpFetch** | `VaultHttpFetch` | Vault HTTP fetch with credential scrubbing. Ant-only. | Read |
| **Artifact** | `Artifact` | Create/display artifacts. | Write |
| **SyntheticOutput** | `SyntheticOutput` | Synthetic output tool for testing. | Write |

---

## 2. Tool Registration and Discovery

### Registration
All tools are registered in `/tmp/claude-code/src/tools.ts` via `getAllBaseTools()`:

```typescript
export function getAllBaseTools(): Tools {
  return [
    AgentTool,
    TaskOutputTool,
    BashTool,
    ...(hasEmbeddedSearchTools() ? [] : [GlobTool, GrepTool]),
    ExitPlanModeV2Tool,
    FileReadTool,
    FileEditTool,
    FileWriteTool,
    NotebookEditTool,
    ArtifactTool,
    WebFetchTool,
    TodoWriteTool,
    WebSearchTool,
    TaskStopTool,
    AskUserQuestionTool,
    SkillTool,
    EnterPlanModeTool,
    LocalMemoryRecallTool,
    VaultHttpFetchTool,
    // ... more conditionally via feature()/env
  ]
}
```

Tools are conditionally included based on:
- **Bun `feature()` dead-code elimination**: `feature('KAIROS')`, `feature('COORDINATOR_MODE')`, etc.
- **Environment variables**: `USER_TYPE === 'ant'`, `ENABLE_LSP_TOOL`, `CLAUDE_CODE_VERIFY_PLAN`
- **`require()`-based lazy loading**: Feature-flagged tools are conditionally `require()`'d so they are excluded from the production bundle entirely.

### Tool Assembly Pipeline
The function `assembleToolPool()` in `tools.ts` combines built-in tools with MCP tools from connected servers. It:
1. Gets built-in tools via `getTools()` (respects permission mode and deny rules)
2. Filters MCP tools by deny rules
3. Deduplicates by name (built-in tools take precedence)
4. Sorts built-ins first, then MCP tools (for prompt-cache stability)

### Tool Construction
Every tool is built via `buildTool()` from `src/Tool.ts`. This factory provides defaults for:
- `isEnabled` → `true`
- `isConcurrencySafe` → `false` (assume not safe)
- `isReadOnly` → `false` (assume writes)
- `isDestructive` → `false`
- `checkPermissions` → `{ behavior: 'allow', updatedInput }` (defer to general system)
- `toAutoClassifierInput` → `''` (skip classifier)
- `userFacingName` → tool name

### Input Validation
Tools use **Zod v4** for schema validation. Each tool defines an `inputSchema` that is lazy-evaluated (`lazySchema()`) to avoid circular dependency issues. The input validation runs in `checkPermissionsAndCallTool()`:
1. `tool.inputSchema.safeParse(input)` — Zod structural validation
2. `tool.validateInput(parsedData, context)` — tool-specific semantic validation (file existence, string uniqueness, etc.)

---

## 3. Tool Execution Strategy

### Parallel Read, Serial Write
The core orchestration is in `src/services/tools/toolOrchestration.ts`:

```typescript
function partitionToolCalls(toolUseMessages, toolUseContext): Batch[] {
  // Partitions tool calls into batches where each batch is either:
  // 1. A single non-read-only tool, or
  // 2. Multiple consecutive read-only tools
}
```

- **Read-only tools** are grouped into concurrent batches and execute in parallel via `all()` (limited to `CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY`, default 10)
- **Write tools** execute serially, one at a time
- A tool's concurrency safety is determined by `tool.isConcurrencySafe(input)` which returns `true` for read-only tools like Read, Grep, Glob, WebFetch, WebSearch

### StreamingToolExecutor
For streaming scenarios, `StreamingToolExecutor` (`src/services/tools/StreamingToolExecutor.ts`) manages tools that are still being received from the model stream. It:
- Maintains a queue of tools with status: `queued`, `executing`, `completed`, `yielded`
- Respects concurrency: read-only tools can execute in parallel; writes block the queue
- Buffers results and emits them in order
- Handles abort/cancellation with sibling error propagation
- Only Bash errors cancel sibling tools (to handle implicit dependency chains like `mkdir` → subsequent commands)
- Supports `discard()` for streaming fallback scenarios

---

## 4. Tool Approval/Permission System

The permission system is EXTREMELY sophisticated. Each tool call goes through multiple layers:

### Permission Pipeline (in order):

1. **Zod schema validation** — Reject malformed input
2. **`validateInput()`** — Tool-specific validation (e.g., file exists, old_string found)
3. **Abort check** — Check if context is aborted
4. **PreToolUse hooks** — User-defined hooks can allow/deny/ask/modify input
5. **Deny rules** (rule-based):
   - 1a. Entire tool denied by rule (e.g., `WebFetch: deny`)
   - 1b. Tool-specific deny rules (e.g., `Bash(rm:*): deny`)
6. **Ask rules**: `Bash(npm publish:*): ask`
7. **Tool-specific `checkPermissions()`** — Each tool can have custom logic
8. **Safety checks**: Sensitive paths (`.git/`, `.claude/`, shell configs) are bypass-immune
9. **Mode checks**:
   - `bypassPermissions` — All tools auto-allowed (except safety checks and user-interaction tools)
   - `acceptEdits` — Edit tools in working directory auto-allowed
   - `auto` — AI classifier (YOLO) decides
   - `dontAsk` — All asks become silent denies
   - `plan` — Respects `isBypassPermissionsModeAvailable`
10. **Always-allowed rules**: Tool-level allow rules
11. **Read-only auto-allow**: Read-only Bash commands auto-allowed
12. **Auto mode classifier** (when enabled): Uses a Haiku model to classify actions as safe/dangerous based on past conversation
13. **Sandbox auto-allow**: When sandboxing is enabled + `autoAllowBashIfSandboxed`, sandboxable commands auto-allow
14. **Headless agent handling**: PermissionRequest hooks run; auto-deny if none matches
15. **PostToolUse hooks**: Can modify output, prevent continuation
16. **PostToolUseFailure hooks**: Run on errors

### Permission Rule Format
```
ToolName(ruleContent)
```
- `Bash` — blanket deny/allow/ask for all Bash
- `Bash(git commit:*)` — prefix rule
- `Bash(rm -rf /)` — exact match
- `Bash(ls *)` — wildcard
- `WebFetch(domain:github.com)` — content-specific rule
- `mcp__server__*` — MCP server-level permission

### Rule Sources (priority-ordered):
1. `command` — CLI flags
2. `flagSettings` — GrowthBook feature flags
3. `policySettings` — Managed/IT policy
4. `userSettings` — `~/.claude/settings.json`
5. `projectSettings` — `.claude/settings.json`
6. `localSettings` — `.claude/settings.local.json`
7. `cliArg` — `--allowedTools`, `--disallowedTools`
8. `session` — Runtime-only (MemoryStore, never persisted)

---

## 5. Bash Tool Implementation (Security Deep-Dive)

The Bash tool is the most heavily guarded tool. Security layers:

### AST-Based Parsing (tree-sitter-bash)
- When available, the entire command is parsed by tree-sitter into an AST
- This reveals hidden substitutions, malformed syntax, and structural tricks that regex-based splitters miss
- If AST parsing shows: `too-complex` (command substitution, expansion, control flow) → ask for permission
- `parse-unavailable` → fall back to legacy shell-quote + regex path
- Shadow mode (`TREE_SITTER_BASH_SHADOW`) runs both paths in parallel for validation

### Safe Wrapper Stripping
Commands are stripped of harmless wrappers before permission matching:
- `timeout N cmd` → `cmd`
- `nice -n N cmd` → `cmd`
- `nohup cmd` → `cmd`
- `stdbuf -o0 cmd` → `cmd`
- Safe env vars (NODE_ENV, GOOS, RUST_LOG, etc.) are also stripped

### Command Injection Detection
20+ security checks in `bashSecurity.ts`:
- `$()` command substitution
- `${}` parameter substitution
- Backtick injection
- Process substitution `<()`, `>()`
- Zsh-specific dangerous commands (zmodload, emulate, zpty, etc.)
- IFS injection
- Newline injection
- Obfuscated flags
- Unicode homoglyphs
- Backslash-escaped operators
- Heredoc substitution detection
- Control characters
- Mid-word hash injection

### Path Constraints
`checkPathConstraints()` validates:
- Output redirection targets (can't write outside project/approved dirs)
- `cd` + redirect combinations (prevent bypassing directory checks)
- Working directory boundaries
- Deny rules for paths

### Sed Validation
`sedValidation.ts` contains a comprehensive sed allowlist/denylist:
- Only allows: print commands (`sed -n 'Np'`) and substitution commands (`sed 's/x/y/'`)
- Blocks: write commands (`w`), execute commands (`e`), negations, blocks, comments
- Flag allowlist: only `-n`, `-E`, `-r`, `-z` (read-only); `-i` in acceptEdits mode

### Destructive Command Warning
Commands like `rm -rf`, `git push --force`, `dd`, `mkfs` trigger explicit warnings before execution.

### Sandboxing
When enabled, bash commands run in a containerized/sandboxed environment:
- Auto-allow in sandbox mode when `autoAllowBashIfSandboxed` is on
- Checks excluded commands (commands that must NOT run sandboxed)
- `dangerouslyDisableSandbox` flag gates escape

### Shell-Specific Security
- Only `bash`, `zsh`, `fish`, `csh`, `tcsh`, `ksh`, `dash` as shell prefixes blocked
- Zsh glob qualifiers (`(e:)`, `(+)`) detected
- Equals expansion (`=cmd`) blocked
- `cd` + `git` in compound commands blocked (bare repository RCE protection)

---

## 6. MCP Client Implementation

Located in `/tmp/claude-code/packages/mcp-client/src/`:

### Architecture
```
McpManager (manager.ts)
  ├── connect/disconnect/disconnectAll
  ├── getTools/getAllTools
  ├── callTool
  ├── Event-driven: connected, disconnected, toolsChanged, error, authRequired
  └── delegates to:
      ├── discovery.ts — tool discovery (listTools)
      ├── execution.ts — tool execution (callTool)
      ├── connection.ts — transport connection
      └── cache.ts — LRU caching
```

### Key Details:
- **Timeout**: Default MCP_TOOL_TIMEOUT = ~27.8 hours (100,000,000ms), overridable via `MCP_TOOL_TIMEOUT` env
- **Transport types**: `stdio`, `sse`, `http`, `ws`, `sdk`, `sse-ide`, `ws-ide`, `claudeai-proxy`
- **Tool naming**: MCP tools get `mcp__serverName__toolName` prefix to avoid collisions
- **Auth handling**: `McpAuthError` triggers OAuth re-authorization flow; clients get marked as `needs-auth`
- **Progress**: 30-second interval logging for long-running tools
- **Connection lifecycle**: `connected` → `connected` (with client) → `needs-auth` → `failed`

### Tool Result Processing:
MCP tool results may contain:
- `content` — text/image/resource content blocks
- `structuredContent` — structured JSON output
- `_meta` — metadata for SDK consumers
- `isError` — error flag that gets wrapped as `McpToolCallError`

---

## 7. File Edit Tool (Diff-Based Editing)

### How It Works:
1. Receives: `file_path`, `old_string`, `new_string`, `replace_all` (optional)
2. **Validation**:
   - Expands `~` and relative paths
   - Checks file size (cap: 1 GiB)
   - Reads current file content
   - Finds exact `old_string` match (handles whitespace, line endings)
   - If not found → error with suggested similar filename
   - If multiple matches and `replace_all=false` → error
   - Staleness check: file modified since last read → error
   - Settings file validation (prevents corrupting configs)
   - Jupyter notebook detection → redirects to NotebookEdit
3. **Execution**:
   - Creates parent directories if needed
   - Backs up file (if fileHistoryEnabled)
   - Reads file content in critical section (sync read)
   - Finds actual string match
   - Generates unified diff (`getPatchForEdit`)
   - Writes modified content to disk
   - Notifies LSP servers (didChange + didSave)
   - Notifies VS Code for diff view
   - Updates readFileState cache

### String Matching:
`findActualString()` does fuzzy matching:
- Tries exact match first
- Then line-ending normalized match
- Then whitespace-trimmed match
- Returns the actual string from file (preserving exact formatting)

---

## 8. Tool Execution Lifecycle (Single Tool)

From `src/services/tools/toolExecution.ts`:

1. **Look up tool** by name (or alias) from available tools
2. **Abort check** — return cancel message if aborted
3. **Schema validation** — Zod `safeParse`
4. **ValidateInput** — tool-specific validation
5. **Speculative bash classifier** — start early for Bash commands
6. **Defense-in-depth strip** — remove `_simulatedSedEdit`
7. **Backfill observable input** — expand paths for hooks
8. **PreToolUse hooks** — can allow/deny/modify input/stop execution
9. **Permission check** — via `canUseTool` which runs the full pipeline
10. **Tool call** — `tool.call()` with progress callbacks
11. **Map result** — `tool.mapToolResultToToolResultBlockParam()`
12. **Result processing** — size-based persistence to disk if > maxResultSizeChars
13. **PostToolUse hooks** — can modify MCP outputs, provide context
14. **Result messages** — assemble final user messages
15. **Error handling** — `PostToolUseFailure` hooks, MCP auth errors

---

## 9. Tool Progress/Streaming

Tools report progress via `onToolProgress()` callback:
- **BashTool**: Reports bash execution progress (stdout lines, status)
- **AgentTool**: Reports sub-agent streaming progress
- **SkillTool**: Reports skill execution progress
- **WebSearchTool**: Reports search progress
- **WebFetchTool**: Reports fetch progress
- **MCP tools**: Forward MCP progress notifications

Progress messages are yielded as `ProgressMessage` and displayed in the UI via `renderToolUseProgressMessage()`.

---

## 10. Error Handling

### Error Classification:
- `tool_use_error` — generic tool errors
- `InputValidationError` — Zod schema validation failures
- `McpToolCallError` — MCP server errors
- `McpAuthError` — MCP auth errors (triggers re-auth flow)
- `AbortError` — User interrupt or streaming fallback
- `ShellError` — Bash execution errors
- `MaxFileReadTokenExceededError` — File too large

### Error Telemetry:
- `classifyToolError()` maps errors to telemetry-safe strings
- Node.js fs errors use errno codes (ENOENT, EACCES)
- Known error types use stable names
- ShellErrors are NOT logged as ERROR (expected for failed commands)

### Sibling Error Propagation:
In concurrent tool batches, only Bash errors cancel sibling tools. Read/WebFetch/etc errors are independent and don't cascade.

---

## 11. Tool Timeouts

- **Bash Tool**: Configurable via `timeout` parameter, defaults from environment
- **MCP Tools**: ~27.8 hours default, overridable via `MCP_TOOL_TIMEOUT`
- **WebFetch**: Internal timeout via Tavily/HTTP client
- **Read/Edit/Grep**: No explicit timeout; use abort signal
- **General**: Child abort controllers allow granular cancellation

---

## 12. Key Design Patterns

### `buildTool()` Factory
All tools use `buildTool(def)` which merges defaults with the tool definition. This ensures consistent behavior for `isConcurrencySafe`, `isReadOnly`, `checkPermissions`, etc.

### Zod v4 + `lazySchema()`
Input/output schemas use Zod v4 with lazy evaluation to handle circular module dependencies.

### BackfillObservableInput
`backfillObservableInput()` modifies a copy of tool input for hooks/permissions without altering the original (preserves API prompt cache).

### `preparePermissionMatcher()`
Tools that operate on paths/patterns can provide a matcher function so hooks can use content-specific permission patterns (e.g., `Bash(git *)` matching against a command).

### `mapToolResultToToolResultBlockParam()`
Each tool maps its output to the Anthropic API's tool result format. Supports:
- Text results (string)
- Image results (base64 with media type)
- Notebook results (cell arrays)
- PDF results (base64 document blocks)

### Tool Aliases
Tools can have `aliases` for backwards compatibility (e.g., `KillShell` → `TaskStop`).

---

## 13. Safety/Security Checks Summary

1. **Zod schema strict validation** — Rejects unexpected fields
2. **UNC path blocking** — Prevents NTLM credential leaks on Windows
3. **Device file blocking** — Prevents `/dev/zero`, `/dev/random`, `/dev/stdin` reads
4. **Binary file detection** — Prevents reading binary files (except images/PDFs)
5. **File size limits** — Read: 256KB default (configurable); Edit: 1 GiB
6. **Token limits** — Files exceeding max tokens rejected with pagination guidance
7. **Staleness detection** — Files modified since last read rejected
8. **Path expansion** — `~` and relative paths expanded before permission checks
9. **Settings file validation** — Special validation for .claude/settings.json edits
10. **Secrets detection** — Team memory files checked for credential leakage
11. **Command injection detection** — 20+ patterns in bashSecurity.ts
12. **Shell wrapper stripping** — Prevents bypass via `timeout`, `nice`, etc.
13. **Safe env var allowlist** — Only specific env vars stripped from permission checks
14. **Compound command splitting** — Each subcommand independently permission-checked
15. **cd + redirect guarding** — Prevents directory-change-based path bypass
16. **cd + git blocking** — Prevents bare repository RCE attacks
17. **Sed strict allowlist** — Only print + substitution commands allowed
18. **Auto mode classifier** — AI-based safety classification of tool calls
19. **Denial tracking** — Limits consecutive/total denials, falls back to prompting
20. **Sandboxing** — Containerized execution when enabled
