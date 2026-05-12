import type {
  ChatThreadSummary,
  PersistedThreadDetailPayload,
  PersistedThreadSummaryPayload,
} from "./types";

export function toTimestamp(value: string | number | null | undefined): number {
  if (typeof value === "number") {
    return value;
  }
  if (!value) {
    return Date.now();
  }
  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? Date.now() : parsed;
}

export function buildThreadTitle(prompt: string): string {
  const normalized = prompt.replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "New Chat";
  }
  if (normalized.length <= 72) {
    return normalized;
  }
  return `${normalized.slice(0, 69).trimEnd()}...`;
}

export function buildThreadPreview(content: string): string {
  const normalized = content.replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "";
  }
  if (normalized.length <= 120) {
    return normalized;
  }
  return `${normalized.slice(0, 117).trimEnd()}...`;
}

export function createGuestThread(jurisdiction: string | null): ChatThreadSummary {
  const now = Date.now();
  const suffix = Math.random().toString(36).slice(2, 8);
  return {
    id: `guest-${now}-${suffix}`,
    title: "New Chat",
    jurisdiction: jurisdiction || null,
    preview: null,
    messageCount: 0,
    createdAt: now,
    updatedAt: now,
    persisted: false,
  };
}

export function mapPersistedThreadSummary(
  payload: PersistedThreadSummaryPayload,
): ChatThreadSummary {
  return {
    id: String(payload.id),
    title: payload.title,
    jurisdiction: payload.jurisdiction ?? null,
    preview: payload.preview ?? null,
    messageCount: payload.message_count,
    createdAt: toTimestamp(payload.created_at),
    updatedAt: toTimestamp(payload.updated_at),
    persisted: true,
  };
}

export function mapPersistedMessage(payload: PersistedThreadDetailPayload["messages"][number]) {
  return {
    id: `server-${payload.id}`,
    role: payload.role,
    content: payload.content,
    accuracy: payload.accuracy,
    resolvedJurisdiction: payload.resolved_jurisdiction ?? null,
    navigation: payload.navigation,
    sources: payload.sources,
    timestamp: toTimestamp(payload.created_at),
  };
}
