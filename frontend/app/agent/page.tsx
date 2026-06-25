"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Shell } from "@/components/layout/shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip as ReTooltip } from "recharts";
import {
  Send, Loader2, CheckCircle2, AlertCircle, Circle,
  ChevronDown, ChevronRight, ChevronLeft, Zap, StopCircle, Plug, Copy, RefreshCw, Trash2, BookOpen,
} from "lucide-react";

import { SkillsPanel } from "@/components/agent/skills-panel";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

type ToolCall = {
  tool: string;
  args?: Record<string, unknown>;
  status: "running" | "ok" | "error";
  preview?: string;
  elapsed_s?: number;
  error?: string;
  stage?: string;
  message?: string;
};

type AgentMessage = {
  id: string;
  role: "user" | "agent";
  content: string;
  thinking: string;
  toolCalls: ToolCall[];
  done: boolean;
  elapsed_s?: number;
  toolCount?: number;
  error?: string;
};

export default function AgentPage() {
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [connected, setConnected] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [sessionName, setSessionName] = useState("");
  const [sessions, setSessions] = useState<{ session_id: string; modified: number; first_message?: string; tool_count?: number }[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [skillsPanelOpen, setSkillsPanelOpen] = useState(false);
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const scrollBottom = useCallback(() => {
    requestAnimationFrame(() => {
      const el = scrollRef.current?.querySelector("[data-scroll-viewport]");
      if (el) el.scrollTop = el.scrollHeight;
    });
  }, []);

  const toggleTool = (id: string) => {
    setExpandedTools((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  // Update agent message in-place
  const updateLastAgent = useCallback((updater: (msg: AgentMessage) => void) => {
    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      if (last && last.role === "agent") {
        const copy = { ...last, toolCalls: [...last.toolCalls] };
        updater(copy);
        next[next.length - 1] = copy;
      }
      return next;
    });
    scrollBottom();
  }, [scrollBottom]);

  const handleSend = useCallback(() => {
    if (!input.trim() || running) return;
    const msg = input.trim();
    setInput("");
    setConnected(false);

    const uid = `u-${Date.now()}`;
    const aid = `a-${Date.now()}`;

    setMessages((prev) => [
      ...prev,
      { id: uid, role: "user", content: msg, thinking: "", toolCalls: [], done: true },
      { id: aid, role: "agent", content: "", thinking: "", toolCalls: [], done: false },
    ]);
    setRunning(true);
    // Set session name from first message if starting a new session
    if (!sessionId) {
      setSessionName(msg.slice(0, 60));
    }
    scrollBottom();

    const controller = new AbortController();
    abortRef.current = controller;

    fetch(`${API_BASE}/agent/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ message: msg, session_id: sessionId || undefined }),
      signal: controller.signal,
    })
      .then(async (resp) => {
        if (!resp.ok) throw new Error(`Server returned ${resp.status}`);
        setConnected(true);
        const reader = resp.body!.getReader();
        const decoder = new TextDecoder();
        let buf = "", ev = "message", dataLines: string[] = [];

        const flush = () => {
          const dataStr = dataLines.join("\n");
          const currentEv = ev;
          dataLines = []; ev = "message";
          if (!dataStr.trim()) return;

          try {
            const p = JSON.parse(dataStr);

            if (currentEv === "thinking_delta") {
              updateLastAgent((a) => { a.thinking += p.text || ""; });
            } else if (currentEv === "thinking_end") {
              updateLastAgent((a) => {
                a.content = p.text || "";
                a.thinking = "";
              });
            } else if (currentEv === "tool_call") {
              updateLastAgent((a) => {
                a.toolCalls.push({ tool: p.tool || "?", args: p.args || {}, status: "running" });
              });
            } else if (currentEv === "tool_progress") {
              updateLastAgent((a) => {
                const tc = a.toolCalls.find((t) => t.tool === p.tool && t.status === "running");
                if (tc) { tc.stage = p.stage; tc.message = p.message; }
              });
            } else if (currentEv === "tool_done") {
              updateLastAgent((a) => {
                const tc = a.toolCalls.find((t) => t.tool === p.tool && t.status === "running");
                if (tc) {
                  tc.status = "ok"; tc.preview = p.preview; tc.elapsed_s = p.elapsed_s;
                  if (p.chart_data) (tc as any).chartData = p.chart_data;
                }
              });
            } else if (currentEv === "tool_error") {
              updateLastAgent((a) => {
                const tc = a.toolCalls.find((t) => t.tool === p.tool && t.status === "running");
                if (tc) {
                  tc.status = "error"; tc.error = p.error; tc.elapsed_s = p.elapsed_s;
                }
              });
            } else if (currentEv === "answer") {
              updateLastAgent((a) => { a.content = p.text || ""; });
            } else if (currentEv === "done") {
              updateLastAgent((a) => {
                a.done = true; a.elapsed_s = p.elapsed_s; a.toolCount = p.tool_count;
              });
              setRunning(false);
              if (p.session_id) setSessionId(p.session_id);
            } else if (currentEv === "error") {
              updateLastAgent((a) => {
                a.error = p.message || "Unknown error"; a.done = true;
              });
              setRunning(false);
            }
          } catch { /* skip parse errors */ }
        };

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const lines = buf.split(/\r?\n/);
          buf = lines.pop() ?? "";
          for (const line of lines) {
            if (line === "") flush();
            else if (line.startsWith("event:")) ev = line.slice(6).trim();
            else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
          }
        }
        if (dataLines.length) flush();
      })
      .catch((err) => {
        if (err.name === "AbortError") return;
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last && last.role === "agent") {
            last.error = `Connection failed: ${err.message || String(err)}`;
            last.done = true;
          }
          return next;
        });
        setRunning(false);
      });
  }, [input, running, sessionId, updateLastAgent, scrollBottom]);

  const handleStop = () => { abortRef.current?.abort(); setRunning(false); };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  useEffect(() => { inputRef.current?.focus(); }, [running]);

  const fetchSessions = useCallback(() => {
    fetch(`${API_BASE}/agent/sessions`)
      .then((r) => r.json())
      .then((d) => setSessions(d.sessions || []))
      .catch(() => {});
  }, []);

  const loadSession = useCallback((sid: string) => {
    setSessionId(sid);
    fetch(`${API_BASE}/agent/sessions/${sid}`)
      .then((r) => r.json())
      .then((data) => {
        // Set the session display name from stored first_message
        if (data.first_message) {
          setSessionName(data.first_message.slice(0, 60));
        }
        const msgs = data.messages || [];
        if (msgs.length === 0) return;
        // Reconstruct message blocks from stored data
        const blocks: AgentMessage[] = [];
        let currentAgent: AgentMessage | null = null;
        for (const m of msgs) {
          if (m.role === "user") {
            blocks.push({
              id: `hist-u-${blocks.length}`, role: "user", content: m.content || "",
              thinking: "", toolCalls: [], done: true,
            });
            currentAgent = {
              id: `hist-a-${blocks.length}`, role: "agent", content: "",
              thinking: "", toolCalls: [], done: true, toolCount: 0,
            };
            blocks.push(currentAgent);
          } else if (m.role === "assistant" && currentAgent) {
            // Accumulate text across multiple assistant messages
            if (m.content) currentAgent.content += (currentAgent.content ? "\n\n" : "") + (m.content || "");
            if (m.tool_calls) {
              for (const tc of m.tool_calls) {
                currentAgent.toolCalls.push({
                  tool: tc.name || "?", args: tc.args || {},
                  status: "ok", preview: m.preview,
                });
                currentAgent.toolCount = (currentAgent.toolCount || 0) + 1;
              }
            }
          } else if (m.role === "tool" && currentAgent) {
            // Tool results: update the matching tool call with preview + chart
            const tc = currentAgent.toolCalls.find(
              (t) => t.tool === m.name && !t.preview);
            if (tc) {
              if (m.preview) tc.preview = m.preview;
              if (m.chart_data) (tc as any).chartData = m.chart_data;
            }
          }
        }
        setMessages(blocks);
      })
      .catch(() => {});
  }, []);

  const deleteSession = async (e: React.MouseEvent, sid: string) => {
    e.stopPropagation();
    await fetch(`${API_BASE}/agent/sessions/${sid}`, { method: "DELETE" });
    if (sessionId === sid) { setSessionId(""); setMessages([]); }
    fetchSessions();
  };

  useEffect(() => { fetchSessions(); }, [fetchSessions]);


  return (
    <Shell>
      <div className="flex h-[calc(100vh-4rem)]">
        {sidebarOpen ? (
        <div className="w-56 border-r flex flex-col shrink-0 bg-muted/10">
          <div className="px-3 py-2.5 border-b flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Sessions</span>
            <div className="flex items-center gap-0.5">
              <Button variant="ghost" size="sm" className="h-6 text-[10px] px-1.5"
                onClick={() => { setSessionId(""); setSessionName(""); setMessages([]); }}>+ New</Button>
              <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => setSidebarOpen(false)}>
                <ChevronLeft className="h-3 w-3" />
              </Button>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-1.5 space-y-0.5">
            {sessions.length === 0 ? (
              <p className="text-[10px] text-muted-foreground px-2 py-4 text-center">No sessions yet</p>
            ) : (
              sessions.map((s) => (
                <div key={s.session_id} role="button" tabIndex={0}
                  className={`w-full text-left px-2 py-1.5 rounded text-[11px] transition-colors group cursor-pointer ${sessionId === s.session_id ? "bg-primary/10 border border-primary/20" : "hover:bg-muted/50"}`}
                  onClick={() => loadSession(s.session_id)}
                  onKeyDown={(e) => { if (e.key === "Enter") loadSession(s.session_id); }}>
                  <div className="flex items-start justify-between">
                    <p className="truncate leading-snug flex-1 min-w-0">{s.first_message || s.session_id.slice(0, 12)}</p>
                    <button className="p-0.5 rounded hover:bg-destructive/10 shrink-0 ml-1 opacity-0 group-hover:opacity-100 transition-opacity"
                      onClick={(e) => deleteSession(e, s.session_id)} title="Delete">
                      <Trash2 className="h-3 w-3 text-muted-foreground hover:text-destructive" />
                    </button>
                  </div>
                  <div className="flex items-center gap-1.5 text-[9px] text-muted-foreground mt-0.5">
                    <span>{new Date(s.modified * 1000).toLocaleDateString()}</span>
                    {s.tool_count != null && <span>&middot; {s.tool_count}t</span>}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
        ) : (
          <Button variant="ghost" size="sm" className="h-8 w-8 p-0 mt-2 ml-1 shrink-0"
            onClick={() => setSidebarOpen(true)} title="Show sessions">
            <ChevronRight className="h-4 w-4" />
          </Button>
        )}

        <div className="flex-1 flex flex-col min-w-0">
          <div className="flex items-center justify-between px-4 py-2 border-b shrink-0">
            <div className="flex items-center gap-2 min-w-0">
              <Zap className="h-4 w-4 text-primary shrink-0" />
              <span className="font-semibold text-sm truncate" title={sessionName || sessionId}>
                {sessionName || (sessionId ? `Session ${sessionId.slice(0, 8)}` : "New Session")}
              </span>
              {connected && <Badge variant="outline" className="text-[10px] shrink-0"><Plug className="h-2.5 w-2.5 mr-0.5" />Connected</Badge>}
            </div>
            <div className="flex items-center gap-1.5">
              <Button variant="ghost" size="sm" onClick={() => setSkillsPanelOpen(!skillsPanelOpen)} className="shrink-0 text-xs">
                <BookOpen className="h-3.5 w-3.5 mr-1" />Skills
              </Button>
              {running && <Button variant="outline" size="sm" onClick={handleStop} className="shrink-0"><StopCircle className="mr-1 h-3.5 w-3.5" />Stop</Button>}
            </div>
          </div>

          <div ref={scrollRef} className="flex-1 overflow-y-auto">
            <div className="p-4 space-y-4 min-h-full">
              {messages.length === 0 && (
                <div className="text-center py-24 space-y-4">
                  <Zap className="h-12 w-12 mx-auto text-muted-foreground/20" />
                  <p className="text-muted-foreground text-sm">Financial AI agent. Ask anything about markets.</p>
                  <div className="flex gap-2 justify-center flex-wrap">
                    {["What is the current price of AAPL?", "Analyze TSLA technicals and fundamentals", "Search for latest news about AI chip stocks"].map((q) => (
                      <Button key={q} variant="outline" size="sm" className="text-xs" onClick={() => { setInput(q); inputRef.current?.focus(); }}>{q}</Button>
                    ))}
                  </div>
                </div>
              )}
              {messages.map((block) => (
                <div key={block.id} className="space-y-2">
                  {block.role === "user" && (
                    <div className="flex justify-end"><div className="bg-primary/10 rounded-2xl rounded-br-md px-4 py-2.5 max-w-[80%]"><p className="text-sm whitespace-pre-wrap">{block.content}</p></div></div>
                  )}
                  {block.role === "agent" && (
                    <div className="space-y-2">
                      {block.thinking && !block.content && (
                        <div className="text-sm text-muted-foreground">
                          <div className="flex items-center gap-2 mb-1">
                            <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" />
                            <span className="text-xs font-medium">Thinking...</span>
                          </div>
                          <div className="pl-6 text-xs leading-relaxed whitespace-pre-wrap max-h-40 overflow-y-auto">
                            {block.thinking.slice(-800)}
                            <span className="inline-block w-1.5 h-3.5 bg-primary animate-pulse ml-0.5 align-middle" />
                          </div>
                        </div>
                      )}
                      {block.toolCalls.map((tc, i) => {
                        const tid = `${block.id}-tc-${i}`;
                        const open = expandedTools.has(tid);
                        return (
                          <div key={tid} className="border border-muted/30 rounded-lg overflow-hidden">
                            <div className="flex items-center gap-1.5 px-2 py-1 cursor-pointer hover:bg-muted/20 text-[11px]" onClick={() => toggleTool(tid)}>
                              {tc.status === "running" ? <Loader2 className="h-3 w-3 animate-spin text-blue-500 shrink-0" /> : tc.status === "ok" ? <CheckCircle2 className="h-3 w-3 text-green-500 shrink-0" /> : <AlertCircle className="h-3 w-3 text-red-500 shrink-0" />}
                              <span className="font-mono font-medium">{tc.tool}</span>
                              <span className="text-muted-foreground truncate">{formatToolPreview(tc.tool, tc.preview || "")}</span>
                              {tc.elapsed_s != null && <span className="text-muted-foreground ml-auto shrink-0">{tc.elapsed_s.toFixed(1)}s</span>}
                              {open ? <ChevronDown className="h-3 w-3 text-muted-foreground shrink-0" /> : <ChevronRight className="h-3 w-3 text-muted-foreground shrink-0" />}
                            </div>
                            {/* Chart shown outside collapsible — always visible when data exists */}
                            {((tc as any).chartData || parseChartData(tc.preview)) && (
                              <div className="h-32 w-full px-2 pb-1">
                                <ResponsiveContainer width="100%" height="100%">
                                  <LineChart data={(tc as any).chartData || parseChartData(tc.preview)!} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
                                    <YAxis domain={["auto", "auto"]} hide width={0} />
                                    <XAxis dataKey="d" tick={{ fontSize: 8 }} interval="preserveStartEnd" />
                                    <ReTooltip contentStyle={{ fontSize: 10, padding: "2px 6px", borderRadius: 4 }} labelFormatter={(l: any) => String(l)} />
                                    <Line type="monotone" dataKey="v" stroke="#22c55e" strokeWidth={1.5} dot={false} />
                                  </LineChart>
                                </ResponsiveContainer>
                              </div>
                            )}
                            {open && (
                              <div className="px-2 pb-2 space-y-1.5 border-t border-muted/20 pt-1.5">
                                {tc.args && Object.keys(tc.args).length > 0 && <div className="text-[10px] text-muted-foreground font-mono bg-muted/30 px-2 py-1 rounded">{JSON.stringify(tc.args)}</div>}
                                {tc.preview && (
                                  <div className="text-[11px] text-muted-foreground max-h-40 overflow-y-auto bg-muted/20 p-1.5 rounded whitespace-pre-wrap font-mono">
                                    {formatToolPreview(tc.tool, tc.preview)}
                                  </div>
                                )}
                                {tc.error && (
                                  <div className="text-[11px] text-red-500 bg-red-500/5 p-1.5 rounded">
                                    {tc.error}
                                    <div className="text-[10px] mt-1 text-muted-foreground">Try rephrasing your request or using different parameters.</div>
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })}
                      {block.content && (
                        <div className="relative group/content">
                          <div className="text-sm leading-relaxed prose prose-sm dark:prose-invert max-w-none"><ReactMarkdown remarkPlugins={[remarkGfm]}>{block.content}</ReactMarkdown></div>
                          <button className="absolute top-0 right-0 p-1 rounded bg-muted/50 opacity-0 group-hover/content:opacity-100 transition-opacity"
                            onClick={() => navigator.clipboard.writeText(block.content)} title="Copy">
                            <Copy className="h-3 w-3 text-muted-foreground" />
                          </button>
                        </div>
                      )}
                      {block.error && <div className="text-sm text-red-500 bg-red-500/5 p-3 rounded-lg"><AlertCircle className="h-4 w-4 inline mr-1" />{block.error}</div>}
                      {block.done && !block.error && (
                        <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                          <span className="flex items-center gap-1"><CheckCircle2 className="h-3 w-3 text-green-500" />
                            {(block.toolCount ?? 0) > 0 ? `${block.toolCount} tools` : "Done"}
                            {block.elapsed_s != null && ` \u00b7 ${block.elapsed_s.toFixed(1)}s`}
                          </span>
                          <button className="hover:text-foreground flex items-center gap-1"
                            onClick={() => {
                              const lastUser = [...messages].reverse().find((m) => m.role === "user");
                              if (lastUser) { setInput(lastUser.content); inputRef.current?.focus(); }
                            }} title="Regenerate">
                            <RefreshCw className="h-3 w-3" /> Retry
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
              {running && messages.length > 0 && messages[messages.length - 1]?.role === "agent" && !messages[messages.length - 1]?.content && messages[messages.length - 1]?.toolCalls.length === 0 && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin" /><span>Thinking...</span></div>
              )}
            </div>
          </div>

          <div className="border-t p-3 shrink-0">
            <div className="flex gap-2">
              <Input ref={inputRef} value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={handleKeyDown}
                placeholder={running ? "Agent is working..." : "Ask anything..."} disabled={running} className="h-10 text-sm" />
              <Button onClick={handleSend} disabled={running || !input.trim()} className="h-10 px-4">
                {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </Button>
            </div>
          </div>
        </div>
        {skillsPanelOpen && (
          <div className="w-72 shrink-0">
            <SkillsPanel onClose={() => setSkillsPanelOpen(false)} />
          </div>
        )}
      </div>
    </Shell>
  );
}

function formatToolPreview(tool: string, preview: string): string {
  try {
    const d = JSON.parse(preview);
    if (d.status !== "ok") return preview.slice(0, 500);
    // Extract key info for common tools
    if (tool === "get_price" && d.latest)
      return `Price: $${d.latest.close} | Change: ${d.change_pct ?? "?"}% | Date: ${d.latest.date} | Bars: ${d.bars_count}`;
    if (tool === "get_indicators")
      return `RSI: ${d.rsi14 ?? "?"} | MACD: ${d.macd_signal ?? "?"} | SMA20: ${d.sma20 ?? "?"} | SMA50: ${d.sma50 ?? "?"}`;
    if (tool === "get_news" || tool === "search_news" || tool === "web_search")
      return `${d.count ?? 0} articles found`;
    if (tool === "get_fundamentals")
      return `PE: ${d.pe ?? "?"} | PB: ${d.pb ?? "?"} | EPS: ${d.eps ?? "?"} | ROE: ${d.roe ?? "?"}`;
    if (tool === "get_sentiment")
      return `Score: ${d.score ?? "?"} | Articles: ${d.article_count ?? "?"}`;
  } catch { return preview.slice(0, 500); }
  return preview.slice(0, 500);
}

function parseChartData(preview?: string): { date?: string; v: number }[] | null {
  if (!preview) return null;
  try { const d = JSON.parse(preview);
    if (d.recent && Array.isArray(d.recent) && d.recent.length >= 2)
      return d.recent.map((b: any) => ({ date: (b.date||"").slice(5), v: Number(b.close??b.c??0) }));
    if (d.bars && Array.isArray(d.bars) && d.bars.length >= 2)
      return d.bars.slice(-30).map((b: any) => ({ date: (b.date||"").slice(5), v: Number(b.close??b.c??0) }));
  } catch { return null; }
  return null;
}
