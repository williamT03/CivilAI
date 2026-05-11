"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ProtectedRoute } from "../components/ProtectedRoute";
import { SiteHeader } from "../components/SiteHeader";
import { useAuth } from "../context/AuthContext";
import { AUTH_API_BASE, CUSTOM_API_BASE } from "../lib/apiConfig";
import { consumePendingChatPrompt } from "../lib/chatIntent";

interface JurisdictionOption {
  name: string;
  chunks: number;
}

interface UploadResult {
  filename?: string;
  documentTitle?: string;
  chapterCount?: number;
  sectionCount?: number;
  subsectionCount?: number;
  replacedExisting?: boolean;
  focusSwitchedTo?: string;
}

interface UploadJobResponse {
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

interface Message {
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

interface ChatThreadSummary {
  id: string;
  title: string;
  jurisdiction?: string | null;
  preview?: string | null;
  messageCount: number;
  createdAt: number;
  updatedAt: number;
  persisted: boolean;
}

interface PersistedThreadSummaryPayload {
  id: number;
  title: string;
  jurisdiction?: string | null;
  preview?: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
}

interface PersistedThreadDetailPayload {
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

interface GuestChatStorage {
  threads: ChatThreadSummary[];
  messagesByThread: Record<string, Message[]>;
  activeThreadId: string | null;
}

function toTimestamp(value: string | number | null | undefined): number {
  if (typeof value === "number") {
    return value;
  }
  if (!value) {
    return Date.now();
  }
  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? Date.now() : parsed;
}

function buildThreadTitle(prompt: string): string {
  const normalized = prompt.replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "New Chat";
  }
  if (normalized.length <= 72) {
    return normalized;
  }
  return `${normalized.slice(0, 69).trimEnd()}...`;
}

function buildThreadPreview(content: string): string {
  const normalized = content.replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "";
  }
  if (normalized.length <= 120) {
    return normalized;
  }
  return `${normalized.slice(0, 117).trimEnd()}...`;
}

function createGuestThread(jurisdiction: string | null): ChatThreadSummary {
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

function mapPersistedThreadSummary(payload: PersistedThreadSummaryPayload): ChatThreadSummary {
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

function mapPersistedMessage(
  payload: PersistedThreadDetailPayload["messages"][number],
): Message {
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

function ChatWorkspace() {
  const { user, token, isGuest } = useAuth();
  const [threads, setThreads] = useState<ChatThreadSummary[]>([]);
  const [messagesByThread, setMessagesByThread] = useState<Record<string, Message[]>>({});
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [isLoadingThreads, setIsLoadingThreads] = useState(false);
  const [hasHydratedThreads, setHasHydratedThreads] = useState(false);
  const [input, setInput] = useState("");
  const [isLoadingResponse, setIsLoadingResponse] = useState(false);
  const [jurisdictions, setJurisdictions] = useState<JurisdictionOption[]>([]);
  const [selectedJurisdiction, setSelectedJurisdiction] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [isSetupExpanded, setIsSetupExpanded] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const homePromptHandledRef = useRef(false);
  const createNewThreadRef = useRef<() => Promise<string | null>>(async () => null);
  const sendPromptRef = useRef<
    (promptText: string, preferredThreadId?: string | null) => Promise<void>
  >(async () => undefined);

  const activeMessages = useMemo(
    () => (activeThreadId ? (messagesByThread[activeThreadId] ?? []) : []),
    [activeThreadId, messagesByThread],
  );

  const guestThreadsKey = useMemo(
    () => `civilai_guest_threads_${user?.id ?? "guest"}`,
    [user?.id],
  );
  const guestActiveThreadKey = useMemo(
    () => `civilai_guest_active_thread_${user?.id ?? "guest"}`,
    [user?.id],
  );
  const legacyGuestMessagesKey = useMemo(
    () => `civilai_chat_${user?.id ?? "anonymous"}`,
    [user?.id],
  );

  const buildApiHeaders = useCallback((): HeadersInit => {
    if (token && !isGuest) {
      return { Authorization: `Bearer ${token}` };
    }
    return {};
  }, [isGuest, token]);

  const loadJurisdictions = useCallback(async () => {
    const response = await fetch(`${CUSTOM_API_BASE}/jurisdictions`, {
      headers: buildApiHeaders(),
    });
    if (!response.ok) {
      throw new Error("Could not load jurisdictions");
    }
    const payload = (await response.json()) as {
      jurisdictions?: JurisdictionOption[];
    };
    const nextJurisdictions = payload.jurisdictions ?? [];
    setJurisdictions(nextJurisdictions);
    return nextJurisdictions;
  }, [buildApiHeaders]);

  const waitForUploadJob = useCallback(
    async (jobId: string) => {
      for (let attempt = 0; attempt < 90; attempt += 1) {
        const response = await fetch(`${CUSTOM_API_BASE}/ingestion-jobs/${jobId}`, {
          headers: buildApiHeaders(),
        });
        if (!response.ok) {
          throw new Error("Could not check indexing progress.");
        }
        const job = (await response.json()) as UploadJobResponse;

        if (job.status === "succeeded") {
          return job;
        }
        if (job.status === "failed") {
          throw new Error(job.error || "Indexing failed.");
        }

        setUploadStatus(
          `Indexing ${job.filename || "PDF"}... ${job.progress ?? 0}% complete`,
        );
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
      }

      throw new Error("Indexing is still running. Refresh the filter in a moment.");
    },
    [buildApiHeaders],
  );

  useEffect(() => {
    let isMounted = true;

    async function hydrateJurisdictions() {
      try {
        if (isMounted) {
          await loadJurisdictions();
        }
      } catch {
        if (isMounted) {
          setJurisdictions([]);
        }
      }
    }

    void hydrateJurisdictions();

    return () => {
      isMounted = false;
    };
  }, [loadJurisdictions]);

  useEffect(() => {
    const storedFocus = localStorage.getItem("civilai_selected_jurisdiction");
    if (storedFocus) {
      setSelectedJurisdiction(storedFocus);
      return;
    }
    if (user?.jurisdiction) {
      setSelectedJurisdiction(user.jurisdiction);
    }
  }, [user?.jurisdiction]);

  useEffect(() => {
    if (selectedJurisdiction) {
      localStorage.setItem("civilai_selected_jurisdiction", selectedJurisdiction);
    }
  }, [selectedJurisdiction]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeMessages, activeThreadId]);

  useEffect(() => {
    if (!isGuest) {
      return;
    }

    const storedThreadsRaw = localStorage.getItem(guestThreadsKey);
    const storedActiveThread = localStorage.getItem(guestActiveThreadKey);

    if (storedThreadsRaw) {
      try {
        const parsed = JSON.parse(storedThreadsRaw) as GuestChatStorage;
        const nextThreads = parsed.threads ?? [];
        const nextMessagesByThread = parsed.messagesByThread ?? {};
        const nextActiveThreadId =
          storedActiveThread || parsed.activeThreadId || nextThreads[0]?.id || null;

        setThreads(nextThreads);
        setMessagesByThread(nextMessagesByThread);
        setActiveThreadId(nextActiveThreadId);

        const activeThread = nextThreads.find((thread) => thread.id === nextActiveThreadId);
        if (activeThread?.jurisdiction) {
          setSelectedJurisdiction(activeThread.jurisdiction);
        }
        setHasHydratedThreads(true);
        return;
      } catch {
        // Fall through to migration or empty guest state.
      }
    }

    const legacyMessagesRaw = localStorage.getItem(legacyGuestMessagesKey);
    if (legacyMessagesRaw) {
      try {
        const legacyMessages = JSON.parse(legacyMessagesRaw) as Message[];
        const migratedThread = createGuestThread(selectedJurisdiction || user?.jurisdiction || null);
        migratedThread.title =
          legacyMessages.find((message) => message.role === "user")?.content
            ? buildThreadTitle(
                legacyMessages.find((message) => message.role === "user")?.content ?? "",
              )
            : "Recent Chat";
        migratedThread.messageCount = legacyMessages.length;
        migratedThread.preview = legacyMessages.length
          ? buildThreadPreview(legacyMessages[legacyMessages.length - 1].content)
          : null;
        migratedThread.updatedAt = legacyMessages.length
          ? legacyMessages[legacyMessages.length - 1].timestamp
          : migratedThread.updatedAt;

        setThreads([migratedThread]);
        setMessagesByThread({ [migratedThread.id]: legacyMessages });
        setActiveThreadId(migratedThread.id);
        localStorage.removeItem(legacyGuestMessagesKey);
        setHasHydratedThreads(true);
        return;
      } catch {
        // Ignore a broken legacy payload and start fresh.
      }
    }

    setThreads([]);
    setMessagesByThread({});
    setActiveThreadId(null);
    setHasHydratedThreads(true);
  }, [guestActiveThreadKey, guestThreadsKey, isGuest, legacyGuestMessagesKey, selectedJurisdiction, user?.jurisdiction]);

  useEffect(() => {
    if (!isGuest) {
      return;
    }

    const payload: GuestChatStorage = {
      threads,
      messagesByThread,
      activeThreadId,
    };
    localStorage.setItem(guestThreadsKey, JSON.stringify(payload));
    if (activeThreadId) {
      localStorage.setItem(guestActiveThreadKey, activeThreadId);
    } else {
      localStorage.removeItem(guestActiveThreadKey);
    }
  }, [activeThreadId, guestActiveThreadKey, guestThreadsKey, isGuest, messagesByThread, threads]);

  useEffect(() => {
    if (!user || isGuest || !token) {
      if (!isGuest) {
        setThreads([]);
        setMessagesByThread({});
        setActiveThreadId(null);
        setHasHydratedThreads(false);
      }
      return;
    }

    let isMounted = true;
    setHasHydratedThreads(false);

    async function loadSavedThreads() {
      setIsLoadingThreads(true);
      try {
        const response = await fetch(`${AUTH_API_BASE}/chats`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        if (!response.ok) {
          throw new Error("Could not load saved chats.");
        }

        const payload = (await response.json()) as PersistedThreadSummaryPayload[];
        const nextThreads = payload.map(mapPersistedThreadSummary);

        if (!isMounted) {
          return;
        }

        setThreads(nextThreads);
        setMessagesByThread((previous) => {
          const nextMessagesByThread: Record<string, Message[]> = {};
          for (const thread of nextThreads) {
            if (previous[thread.id]) {
              nextMessagesByThread[thread.id] = previous[thread.id];
            }
          }
          return nextMessagesByThread;
        });

        const nextActiveThreadId =
          nextThreads.find((thread) => thread.id === activeThreadId)?.id ??
          nextThreads[0]?.id ??
          null;
        setActiveThreadId(nextActiveThreadId);

        const activeThread = nextThreads.find((thread) => thread.id === nextActiveThreadId);
        if (activeThread?.jurisdiction) {
          setSelectedJurisdiction(activeThread.jurisdiction);
        }
      } catch {
        if (isMounted) {
          setThreads([]);
          setMessagesByThread({});
          setActiveThreadId(null);
        }
      } finally {
        if (isMounted) {
          setIsLoadingThreads(false);
          setHasHydratedThreads(true);
        }
      }
    }

    void loadSavedThreads();

    return () => {
      isMounted = false;
    };
  }, [activeThreadId, isGuest, token, user]);

  useEffect(() => {
    if (!activeThreadId || isGuest || !token || messagesByThread[activeThreadId]) {
      return;
    }

    let isMounted = true;

    async function loadThreadDetail(threadId: string) {
      try {
        const response = await fetch(`${AUTH_API_BASE}/chats/${threadId}`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
        if (!response.ok) {
          throw new Error("Could not load thread detail.");
        }

        const payload = (await response.json()) as PersistedThreadDetailPayload;
        if (!isMounted) {
          return;
        }

        setMessagesByThread((previous) => ({
          ...previous,
          [threadId]: payload.messages.map(mapPersistedMessage),
        }));
      } catch {
        if (!isMounted) {
          return;
        }
        setMessagesByThread((previous) => ({
          ...previous,
          [threadId]: [],
        }));
      }
    }

    void loadThreadDetail(activeThreadId);

    return () => {
      isMounted = false;
    };
  }, [activeThreadId, isGuest, messagesByThread, token]);

  function updateThreadSummary(nextThread: ChatThreadSummary) {
    setThreads((previous) => {
      const remaining = previous.filter((thread) => thread.id !== nextThread.id);
      return [nextThread, ...remaining].sort((left, right) => right.updatedAt - left.updatedAt);
    });
  }

  function updateMessagesForThread(threadId: string, updater: (previous: Message[]) => Message[]) {
    setMessagesByThread((previous) => ({
      ...previous,
      [threadId]: updater(previous[threadId] ?? []),
    }));
  }

  function getThreadById(threadId: string | null) {
    return threads.find((thread) => thread.id === threadId) ?? null;
  }

  async function createNewThread(): Promise<string | null> {
    const preferredJurisdiction = selectedJurisdiction || user?.jurisdiction || null;

    if (isGuest) {
      const nextThread = createGuestThread(preferredJurisdiction);
      setMessagesByThread((previous) => ({
        ...previous,
        [nextThread.id]: [],
      }));
      updateThreadSummary(nextThread);
      setActiveThreadId(nextThread.id);
      return nextThread.id;
    }

    if (!token) {
      return null;
    }

    const response = await fetch(`${AUTH_API_BASE}/chats`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        jurisdiction: preferredJurisdiction,
      }),
    });

    if (!response.ok) {
      throw new Error("Could not create a new chat.");
    }

    const payload = (await response.json()) as PersistedThreadSummaryPayload;
    const nextThread = mapPersistedThreadSummary(payload);
    setMessagesByThread((previous) => ({
      ...previous,
      [nextThread.id]: [],
    }));
    updateThreadSummary(nextThread);
    setActiveThreadId(nextThread.id);
    if (nextThread.jurisdiction) {
      setSelectedJurisdiction(nextThread.jurisdiction);
    }
    return nextThread.id;
  }

  async function handleSelectThread(threadId: string) {
    setActiveThreadId(threadId);
    const selectedThread = getThreadById(threadId);
    if (selectedThread?.jurisdiction) {
      setSelectedJurisdiction(selectedThread.jurisdiction);
    }

    if (isGuest || messagesByThread[threadId] || !token) {
      return;
    }

    const response = await fetch(`${AUTH_API_BASE}/chats/${threadId}`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      return;
    }

    const payload = (await response.json()) as PersistedThreadDetailPayload;
    setMessagesByThread((previous) => ({
      ...previous,
      [threadId]: payload.messages.map(mapPersistedMessage),
    }));
  }

  async function handleNewChat() {
    try {
      await createNewThread();
    } catch {
      // Keep this non-blocking so the workspace still feels responsive.
    }
  }

  async function ensureActiveThreadId(): Promise<string | null> {
    if (activeThreadId) {
      return activeThreadId;
    }
    return createNewThread();
  }

  async function sendPrompt(
    promptText: string,
    preferredThreadId?: string | null,
  ): Promise<void> {
    const normalizedPrompt = promptText.trim();
    if (!normalizedPrompt || isLoadingResponse) {
      return;
    }

    const threadId = preferredThreadId ?? (await ensureActiveThreadId());
    if (!threadId) {
      return;
    }

    const activeThread = getThreadById(threadId);
    const now = Date.now();
    const userMessage: Message = {
      id: `local-user-${now}`,
      role: "user",
      content: normalizedPrompt,
      timestamp: now,
    };

    setInput("");
    setIsLoadingResponse(true);

    updateMessagesForThread(threadId, (previous) => [...previous, userMessage]);
    updateThreadSummary({
      id: threadId,
      title:
        activeThread && activeThread.messageCount > 0
          ? activeThread.title
          : buildThreadTitle(userMessage.content),
      jurisdiction: selectedJurisdiction || activeThread?.jurisdiction || null,
      preview: buildThreadPreview(userMessage.content),
      messageCount: (activeThread?.messageCount ?? 0) + 1,
      createdAt: activeThread?.createdAt ?? now,
      updatedAt: now,
      persisted: activeThread?.persisted ?? !isGuest,
    });

    let assistantMessage: Message;
    try {
      const params = new URLSearchParams();
      params.set("q", userMessage.content);
      if (selectedJurisdiction) {
        params.set("jurisdiction", selectedJurisdiction);
      }

      const headers: HeadersInit = {};
      if (token && !isGuest) {
        headers.Authorization = `Bearer ${token}`;
      }
      const response = await fetch(`${CUSTOM_API_BASE}/query?${params.toString()}`, { headers });
      const data = (await response.json()) as {
        answer?: string;
        accuracy?: Message["accuracy"];
        jurisdiction?: string | null;
        navigation?: Message["navigation"];
        sources?: Message["sources"];
        detail?: string;
      };

      assistantMessage = {
        id: `local-assistant-${Date.now()}`,
        role: "assistant",
        content: response.ok
          ? data.answer || "Sorry, I couldn't get a response."
          : data.detail || "Sorry, I couldn't get a response.",
        accuracy: data.accuracy,
        resolvedJurisdiction: data.jurisdiction,
        navigation: data.navigation,
        sources: data.sources,
        timestamp: Date.now(),
      };
    } catch {
      assistantMessage = {
        id: `local-assistant-error-${Date.now()}`,
        role: "assistant",
        content: "Sorry, there was an error processing your request.",
        timestamp: Date.now(),
      };
    } finally {
      setIsLoadingResponse(false);
    }

    updateMessagesForThread(threadId, (previous) => [...previous, assistantMessage]);
    updateThreadSummary({
      id: threadId,
      title:
        activeThread && activeThread.messageCount > 0
          ? activeThread.title
          : buildThreadTitle(userMessage.content),
      jurisdiction:
        selectedJurisdiction ||
        assistantMessage.resolvedJurisdiction ||
        activeThread?.jurisdiction ||
        null,
      preview: buildThreadPreview(assistantMessage.content),
      messageCount: (activeThread?.messageCount ?? 0) + 2,
      createdAt: activeThread?.createdAt ?? now,
      updatedAt: assistantMessage.timestamp,
      persisted: activeThread?.persisted ?? !isGuest,
    });

    if (!isGuest && token) {
      try {
        const response = await fetch(`${AUTH_API_BASE}/chats/${threadId}/turns`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            jurisdiction: selectedJurisdiction || assistantMessage.resolvedJurisdiction || null,
            user_message: {
              content: userMessage.content,
              timestamp: new Date(userMessage.timestamp).toISOString(),
            },
            assistant_message: {
              content: assistantMessage.content,
              timestamp: new Date(assistantMessage.timestamp).toISOString(),
              accuracy: assistantMessage.accuracy,
              resolved_jurisdiction: assistantMessage.resolvedJurisdiction,
              navigation: assistantMessage.navigation,
              sources: assistantMessage.sources,
            },
          }),
        });

        if (response.ok) {
          const payload = (await response.json()) as PersistedThreadSummaryPayload;
          updateThreadSummary(mapPersistedThreadSummary(payload));
        }
      } catch {
        // Keep the local thread view even if persistence has a temporary hiccup.
      }
    }
  }

  async function handleSend(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await sendPrompt(input);
  }

  useEffect(() => {
    createNewThreadRef.current = createNewThread;
    sendPromptRef.current = sendPrompt;
  });

  useEffect(() => {
    if (!hasHydratedThreads || isLoadingThreads || isLoadingResponse || homePromptHandledRef.current) {
      return;
    }

    const pendingPrompt = consumePendingChatPrompt();
    homePromptHandledRef.current = true;

    if (!pendingPrompt) {
      return;
    }

    void (async () => {
      try {
        const threadId = await createNewThreadRef.current();
        if (!threadId) {
          setInput(pendingPrompt.prompt);
          return;
        }
        await sendPromptRef.current(pendingPrompt.prompt, threadId);
      } catch {
        setInput(pendingPrompt.prompt);
      }
    })();
  }, [hasHydratedThreads, isLoadingResponse, isLoadingThreads]);

  async function handleUpload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!uploadFile || isUploading) {
      setUploadError("Choose a PDF before uploading.");
      return;
    }

    setIsUploading(true);
    setUploadError("");
    setUploadResult(null);
    setUploadStatus("Uploading and parsing the PDF...");

    try {
      const formData = new FormData();
      formData.append("file", uploadFile);
      const headers: HeadersInit = {};
      if (token && !isGuest) {
        headers.Authorization = `Bearer ${token}`;
      }

      const response = await fetch(`${CUSTOM_API_BASE}/upload-pdf`, {
        method: "POST",
        headers,
        body: formData,
      });

      const payload = (await response.json()) as {
        detail?: string;
        filename?: string;
        replaced_existing?: boolean;
        job?: {
          id?: string;
          status?: string;
          stage?: string;
          progress?: number;
        };
        parse_result?: {
          document_title?: string;
          chapter_count?: number;
          section_count?: number;
          subsection_count?: number;
        };
      };

      if (!response.ok) {
        throw new Error(payload.detail || "Upload failed.");
      }

      let parseResult = payload.parse_result;
      if (!parseResult && payload.job?.id) {
        setUploadStatus("Upload complete. Indexing the PDF now...");
        const completedJob = await waitForUploadJob(payload.job.id);
        parseResult = completedJob.result ?? undefined;
      }

      const indexedStatus =
        payload.replaced_existing
          ? `Replaced and re-indexed ${payload.filename ?? uploadFile.name}.`
          : `Indexed ${payload.filename ?? uploadFile.name}.`;

      setUploadStatus(indexedStatus);
      setUploadResult({
        filename: payload.filename ?? uploadFile.name,
        documentTitle: parseResult?.document_title,
        chapterCount: parseResult?.chapter_count,
        sectionCount: parseResult?.section_count,
        subsectionCount: parseResult?.subsection_count,
        replacedExisting: payload.replaced_existing ?? false,
        focusSwitchedTo: undefined,
      });
      setUploadFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }

      const nextJurisdictions = await loadJurisdictions();
      const uploadedDocumentTitle = parseResult?.document_title;
      const uploadedJurisdiction = nextJurisdictions.find(
        (option) => option.name === uploadedDocumentTitle,
      );
      if (uploadedJurisdiction) {
        setSelectedJurisdiction(uploadedJurisdiction.name);
        setUploadStatus(
          `${indexedStatus} Code focus switched to ${uploadedJurisdiction.name}.`,
        );
        setUploadResult((previous) =>
          previous
            ? {
                ...previous,
                focusSwitchedTo: uploadedJurisdiction.name,
              }
            : previous,
        );
      }
    } catch (caughtError) {
      setUploadStatus("");
      setUploadError(
        caughtError instanceof Error ? caughtError.message : "Upload failed.",
      );
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <div className="app-shell revamp-shell">
      <div className="page-frame scene-page-frame">
        <SiteHeader />

        <main className="scene-main chat-scene chat-main">
          <div className="page-title-row">
            <div>
              <p className="eyebrow">Chat Workspace</p>
              <h1 className="panel-title">
                Turn <span className="heading-accent">ordinance pages</span> into project-ready
                answers.
              </h1>
            </div>
            <div className="inline-actions">
              <button className="button button-secondary" onClick={() => void handleNewChat()}>
                New Chat
              </button>
              <button
                type="button"
                className="button button-secondary"
                onClick={() => setIsSetupExpanded((isExpanded) => !isExpanded)}
              >
                {isSetupExpanded ? "Minimize Setup" : "Expand Setup"}
              </button>
              <Link href="/account" className="button button-subtle">
                Account Settings
              </Link>
            </div>
          </div>

          <section
            className={`chat-setup-section chat-sidebar-section page-grid ${
              isSetupExpanded ? "" : "chat-setup-section-collapsed"
            }`}
          >
            <div className="section-grid chat-setup-head">
              <div>
                <p className="eyebrow">Workspace Setup</p>
                <h2 className="section-title">Set the code focus and add source PDFs.</h2>
              </div>
              <div className="chat-setup-summary">
                <p className="section-copy">
                  Choose the jurisdiction for this thread, index ordinance PDFs, and reopen prior
                  research trails from one setup tray.
                </p>
                <div className="micro-ledger">
                  <span>{threads.length} research thread{threads.length === 1 ? "" : "s"}</span>
                  <span>{selectedJurisdiction || "All indexed codes"}</span>
                  <span>{uploadFile ? uploadFile.name : "No PDF selected"}</span>
                </div>
              </div>
            </div>

            {isSetupExpanded ? (
            <div className="chat-setup-grid">
              <div className="rail-block chat-control-card chat-memory-panel">
                <div className="message-meta">
                  <div>
                    <p className="eyebrow">Research Threads</p>
                    <h3 className="feature-title">Keep every lookup traceable</h3>
                  </div>
                  <button
                    type="button"
                    className="button button-subtle"
                    onClick={() => void handleNewChat()}
                  >
                    New Chat
                  </button>
                </div>
                {isLoadingThreads ? (
                  <div className="spinner-row" style={{ justifyContent: "flex-start" }}>
                    <span className="spinner" />
                    <span className="muted-label">Loading saved chats</span>
                  </div>
                ) : threads.length ? (
                  <div className="page-grid chat-history-list">
                    {threads.map((thread) => {
                      const isActive = thread.id === activeThreadId;
                      return (
                        <button
                          key={thread.id}
                          type="button"
                          className={`thread-row ${isActive ? "thread-row-active" : ""}`}
                          onClick={() => void handleSelectThread(thread.id)}
                        >
                          <div className="message-meta">
                            <span>{thread.title}</span>
                            <span>{new Date(thread.updatedAt).toLocaleDateString()}</span>
                          </div>
                          {thread.preview ? (
                            <p className="field-hint">{thread.preview}</p>
                          ) : (
                            <p className="field-hint">No messages yet.</p>
                          )}
                          <p className="field-hint">
                            {thread.messageCount} message{thread.messageCount === 1 ? "" : "s"}
                            {thread.jurisdiction ? ` · ${thread.jurisdiction}` : ""}
                          </p>
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <p className="upload-note">
                    No research threads yet. Start with one real code question and CivilAI will
                    keep the lookup grouped for follow-up.
                  </p>
                )}
                <p className="upload-note">
                  {isGuest
                    ? "Guest mode keeps history in this browser for quick tests."
                    : "Signed-in accounts keep the source trail available across sessions."}
                </p>
              </div>

              <div className="rail-block chat-control-card">
                <div>
                  <p className="eyebrow">Jurisdiction Lens</p>
                  <h3 className="feature-title">Aim the answer at the right code</h3>
                </div>
                <div className="field">
                  <label className="field-label" htmlFor="jurisdiction">
                    Search scope
                  </label>
                  <select
                    id="jurisdiction"
                    className="field-select"
                    value={selectedJurisdiction}
                    onChange={(event) => setSelectedJurisdiction(event.target.value)}
                  >
                    <option value="">All indexed codes</option>
                    {jurisdictions.map((option) => (
                      <option key={option.name} value={option.name}>
                        {option.name}
                      </option>
                    ))}
                  </select>
                </div>
                <p className="upload-note">
                  Choose a city or county when the answer needs to stay inside one indexed code.
                </p>
              </div>

              <div className="rail-block chat-control-card">
                <div>
                  <p className="eyebrow">Document Intake</p>
                  <h3 className="feature-title">Add the ordinance you need searched</h3>
                </div>
                <form className="form-grid" onSubmit={handleUpload}>
                  <div className="field">
                    <label className="field-label" htmlFor="pdfFile">
                      PDF file
                    </label>
                    <input
                      id="pdfFile"
                      ref={fileInputRef}
                      className="field-input"
                      type="file"
                      accept="application/pdf"
                      disabled={isUploading}
                      onChange={(event) =>
                        setUploadFile(event.target.files?.[0] ?? null)
                      }
                    />
                  </div>
                  {uploadFile ? (
                    <p className="field-hint">
                      Ready to upload: <strong>{uploadFile.name}</strong>
                    </p>
                  ) : (
                    <p className="field-hint">
                      CivilAI stores the PDF, extracts sections and subsections, then makes the
                      document searchable for grounded answers.
                    </p>
                  )}
                  <div className="upload-row">
                    <button
                      type="submit"
                      className="button button-primary"
                      disabled={!uploadFile || isUploading}
                    >
                      {isUploading ? "Indexing..." : "Index PDF"}
                    </button>
                  </div>
                  {uploadStatus ? (
                    <div className="status-banner status-success">{uploadStatus}</div>
                  ) : null}
                  {uploadError ? (
                    <div className="status-banner status-error">{uploadError}</div>
                  ) : null}
                  {uploadResult ? (
                    <div className="upload-result-panel">
                      <p className="eyebrow">Indexed and Ready</p>
                      <p className="section-copy">
                        <strong>{uploadResult.filename}</strong>
                        {uploadResult.documentTitle
                          ? uploadResult.replacedExisting
                            ? ` replaced the existing PDF and was re-indexed as ${uploadResult.documentTitle}.`
                            : ` was indexed as ${uploadResult.documentTitle}.`
                          : uploadResult.replacedExisting
                            ? " replaced the existing PDF and was indexed successfully."
                            : " was indexed successfully."}
                      </p>
                      <p className="field-hint">
                        Parsed structure: {uploadResult.chapterCount ?? 0} chapters,{" "}
                        {uploadResult.sectionCount ?? 0} sections,{" "}
                        {uploadResult.subsectionCount ?? 0} subsections
                      </p>
                      {uploadResult.focusSwitchedTo ? (
                        <p className="field-hint">
                          Active code focus switched to{" "}
                          <strong>{uploadResult.focusSwitchedTo}</strong>.
                        </p>
                      ) : null}
                    </div>
                  ) : null}
                </form>
              </div>
            </div>
            ) : null}
          </section>

          <section className="chat-workbench-section chat-workbench-no-memory">
            <section className="chat-conversation-sheet page-grid">
              <div className="message-list">
                {activeMessages.length === 0 ? (
                  <div className="chat-empty">
                    <h3>{threads.length ? "Open a research trail or start a fresh one." : "Ask the kind of question that slows a review down."}</h3>
                    <p>
                      Try “What does Broward County say about noise after 9 p.m.?” or “Summarize
                      section 1-2 for Cooper City and cite the source.”
                    </p>
                  </div>
                ) : (
                  activeMessages.map((message) => (
                    <article
                      key={message.id}
                      className={`message-card ${
                        message.role === "user" ? "message-user" : "message-assistant"
                      }`}
                    >
                      <div className="message-meta">
                        <span>{message.role === "user" ? "You" : "Civil AI"}</span>
                        <span>{new Date(message.timestamp).toLocaleTimeString()}</span>
                      </div>

                      <div className="message-stack">
                        <div className="message-body">{message.content}</div>

                        {message.accuracy ? (
                          <div className="accuracy-panel">
                            <div className="message-meta">
                              <span>Confidence Check</span>
                              <span>
                                {message.accuracy.score}% · {message.accuracy.label}
                              </span>
                            </div>
                            <div className="accuracy-bar">
                              <div
                                className="accuracy-fill"
                                style={{ width: `${message.accuracy.score}%` }}
                              />
                            </div>
                            <p className="field-hint">{message.accuracy.reason}</p>
                          </div>
                        ) : null}

                        {message.navigation?.summary_preview ? (
                          <div className="message-detail-panel">
                            <p className="eyebrow">Code Map</p>
                            <p className="section-copy">{message.navigation.summary_preview}</p>
                          </div>
                        ) : null}

                        {message.navigation?.top_chapters?.length ? (
                          <div className="page-grid">
                            <p className="eyebrow">Likely Chapters</p>
                            <div className="chapter-list">
                              {message.navigation.top_chapters.map((chapter) => (
                                <span
                                  key={`${chapter.chapter_number}-${chapter.chapter_name}`}
                                  className="chapter-chip"
                                >
                                  {chapter.chapter_number} · {chapter.chapter_name}
                                </span>
                              ))}
                            </div>
                          </div>
                        ) : null}

                        {message.sources?.length ? (
                          <div className="page-grid">
                            <p className="eyebrow">Sources Behind The Answer</p>
                            <div className="source-list">
                              {message.sources.map((source, index) => {
                                const label = [source.section, source.subsection]
                                  .filter(Boolean)
                                  .join(" › ");
                                const meta = [
                                  source.jurisdiction,
                                  source.page ? `p.${source.page}` : null,
                                ]
                                  .filter(Boolean)
                                  .join(" · ");
                                const text = meta
                                  ? `${label || "Code source"} · ${meta}`
                                  : label || "Code source";

                                return source.url ? (
                                  <a
                                    key={`${message.id}-${index}`}
                                    className="source-link"
                                    href={source.url}
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    {text}
                                  </a>
                                ) : (
                                  <span key={`${message.id}-${index}`} className="source-link">
                                    {text}
                                  </span>
                                );
                              })}
                            </div>
                          </div>
                        ) : null}

                        {message.resolvedJurisdiction ? (
                          <p className="field-hint">
                            Backend focus: {message.resolvedJurisdiction}
                          </p>
                        ) : null}
                      </div>
                    </article>
                  ))
                )}

                {isLoadingResponse ? (
                  <article className="message-card message-assistant">
                    <div
                      className="spinner-row"
                      style={{ justifyContent: "flex-start", marginTop: 0 }}
                    >
                      <span className="spinner" />
                      <span className="muted-label">Checking the ordinance trail</span>
                    </div>
                  </article>
                ) : null}

                <div ref={messagesEndRef} />
              </div>

              <form className="composer-form" onSubmit={handleSend}>
                <div className="field">
                  <label className="field-label" htmlFor="chatPrompt">
                    Ask for a cited code answer
                  </label>
                  <textarea
                    id="chatPrompt"
                    className="field-textarea composer-input"
                    value={input}
                    onChange={(event) => setInput(event.target.value)}
                    placeholder="Ask about setbacks, penalties, permitted uses, noise rules, or a specific section."
                    disabled={isLoadingResponse}
                  />
                </div>
                <div className="composer-actions">
                  <button
                    type="submit"
                    className="button button-primary"
                    disabled={!input.trim() || isLoadingResponse}
                  >
                    {isLoadingResponse ? "Checking..." : "Ask CivilAI"}
                  </button>
                </div>
              </form>
            </section>
          </section>
        </main>
      </div>
    </div>
  );
}

export default function ChatPage() {
  return (
    <ProtectedRoute>
      <ChatWorkspace />
    </ProtectedRoute>
  );
}
