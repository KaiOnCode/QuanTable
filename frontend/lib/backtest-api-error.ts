function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function displayBacktestError(error: unknown): string {
  if (!(error instanceof Error)) return "The request could not be completed.";
  const match = /^HTTP \d+: (.+)$/.exec(error.message);
  if (!match) return error.message;
  try {
    const payload: unknown = JSON.parse(match[1]);
    if (!isRecord(payload) || !isRecord(payload.detail)) {
      return "The request could not be completed.";
    }
    const { code, message } = payload.detail;
    if (typeof message !== "string" || message.trim() === "") {
      return "The request could not be completed.";
    }
    return typeof code === "string" && /^[a-z_]+$/.test(code)
      ? `${message} (${code})`
      : message;
  } catch {
    return "The request could not be completed.";
  }
}

export function isBacktestNotFoundError(error: unknown): boolean {
  return error instanceof Error && error.message.startsWith("HTTP 404:");
}
