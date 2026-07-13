const INSIGHT_GENERATION_ID_PATTERN = /^[0-9a-f]{32}$/;

export function createInsightGenerationId(): string {
  return crypto.randomUUID().replaceAll("-", "");
}

export type InsightGenerationPersistenceStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed";

export function parseInsightGenerationId(
  value: string | null | undefined,
): string | null {
  return value !== null &&
    value !== undefined &&
    INSIGHT_GENERATION_ID_PATTERN.test(value)
    ? value
    : null;
}

export function activeInsightGenerationId(
  generationId: string,
  status: InsightGenerationPersistenceStatus,
): string | null {
  const parsedGenerationId = parseInsightGenerationId(generationId);
  if (parsedGenerationId === null) return null;
  return status === "pending" || status === "running"
    ? parsedGenerationId
    : null;
}

export function encodeInsightGenerationIdPathSegment(
  generationId: string,
): string {
  const parsedGenerationId = parseInsightGenerationId(generationId);
  if (parsedGenerationId === null) {
    throw new Error("Invalid insight generation ID.");
  }
  return encodeURIComponent(parsedGenerationId);
}
