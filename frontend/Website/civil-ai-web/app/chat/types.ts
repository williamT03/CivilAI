export interface JurisdictionOption {
  name: string;
  chunks: number;
}

export interface UploadResult {
  filename?: string;
  documentTitle?: string;
  chapterCount?: number;
  sectionCount?: number;
  subsectionCount?: number;
  replacedExisting?: boolean;
  focusSwitchedTo?: string;
}

export interface UploadJobResponse {
  id: string;
  filename?: string;
  status: "queued" | "running" | "succeeded" | "failed" | string;
  stage?: string;
  progress?: number;
  error?: string | null;
  result?: {
    document_title?: string;
    chapter_count?: number;
    section_count?: number;
    subsection_count?: number;
  } | null;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  accuracy?: {
    score: number;
    label: string;
    reason: string;
  };
  resolvedJurisdiction?: string | null;
  navigation?: {
    summary_preview?: string | null;
    top_chapters?: Array<{
      chapter_number: string;
      chapter_name: string;
    }>;
  };
  sources?: Array<{
    jurisdiction?: string;
    section?: string;
    subsection?: string;
    title?: string;
    page?: number;
    score?: number;
    url?: string;
  }>;
  timestamp: number;
}

export interface ChatThreadSummary {
  id: string;
  title: string;
  jurisdiction?: string | null;
  preview?: string | null;
  messageCount: number;
  createdAt: number;
  updatedAt: number;
  persisted: boolean;
}

export interface PersistedThreadSummaryPayload {
  id: number;
  title: string;
  jurisdiction?: string | null;
  preview?: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface PersistedThreadDetailPayload {
  thread: PersistedThreadSummaryPayload;
  messages: Array<{
    id: number;
    role: "user" | "assistant";
    content: string;
    accuracy?: Message["accuracy"];
    resolved_jurisdiction?: string | null;
    navigation?: Message["navigation"];
    sources?: Message["sources"];
    created_at: string;
  }>;
}

export interface GuestChatStorage {
  threads: ChatThreadSummary[];
  messagesByThread: Record<string, Message[]>;
  activeThreadId: string | null;
}
