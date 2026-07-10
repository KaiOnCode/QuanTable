import type {
  AnalyzeRequest,
  SSEDebateEvent,
  SSEErrorEvent,
  SSEProgressEvent,
  SSEResultEvent,
} from "@/lib/types/models";

type SSEHandlers = {
  onProgress?: (event: SSEProgressEvent) => void;
  onDebate?: (event: SSEDebateEvent) => void;
  onResult?: (event: SSEResultEvent) => void;
  onError?: (event: SSEErrorEvent) => void;
  onComplete?: () => void;
};

const DEFAULT_API_BASE = "http://localhost:8000/api";

export function apiUrl(path: string) {
  const base = process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_BASE;
  return `${base.replace(/\/$/, "")}/${path.replace(/^\//, "")}`;
}

function dispatchEvent(
  eventName: string,
  data: string,
  handlers: SSEHandlers
) {
  if (!data.trim()) return;

  const payload = JSON.parse(data);

  switch (eventName) {
    case "progress":
      handlers.onProgress?.(payload as SSEProgressEvent);
      break;
    case "debate":
      handlers.onDebate?.(payload as SSEDebateEvent);
      break;
    case "result":
      handlers.onResult?.(payload as SSEResultEvent);
      break;
    case "error":
      handlers.onError?.(payload as SSEErrorEvent);
      break;
    default:
      break;
  }
}

async function readSSEStream(response: Response, handlers: SSEHandlers) {
  if (!response.body) {
    throw new Error("The browser does not support readable response streams.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let eventName = "message";
  let dataLines: string[] = [];

  const flush = () => {
    dispatchEvent(eventName, dataLines.join("\n"), handlers);
    eventName = "message";
    dataLines = [];
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (line === "") {
        flush();
      } else if (line.startsWith("event:")) {
        eventName = line.slice("event:".length).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice("data:".length).trimStart());
      }
    }
  }

  if (dataLines.length > 0) {
    flush();
  }
}

export function createSSEStream(
  path: string,
  body: AnalyzeRequest,
  handlers: SSEHandlers
) {
  const controller = new AbortController();

  void fetch(apiUrl(path), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(body),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }

      await readSSEStream(response, handlers);
      handlers.onComplete?.();
    })
    .catch((error: unknown) => {
      if (controller.signal.aborted) return;

      handlers.onError?.({
        agent: "client",
        error: error instanceof Error ? error.message : String(error),
      });
    });

  return controller;
}

// ── Standard JSON request helpers ──────────────────────────

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = apiUrl(path);
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...options.headers as Record<string, string> },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  get<T>(path: string): Promise<T> { return request<T>(path); },
  post<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });
  },
  put<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, { method: "PUT", body: body ? JSON.stringify(body) : undefined });
  },
  delete<T>(path: string): Promise<T> {
    return request<T>(path, { method: "DELETE" });
  },
  sse: createSSEStream,
};
