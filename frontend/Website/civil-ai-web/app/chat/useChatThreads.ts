import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";

import { messageFromError, parseApiResponse } from "../lib/apiClient";
import { AUTH_API_BASE } from "../lib/apiConfig";
import { queryCivilAi } from "../lib/chatApi";
import { consumePendingChatPrompt } from "../lib/chatIntent";
import type {
  ChatThreadSummary,
  GuestChatStorage,
  Message,
  PersistedThreadDetailPayload,
  PersistedThreadSummaryPayload,
} from "./types";
import {
  buildThreadPreview,
  buildThreadTitle,
  createGuestThread,
  mapPersistedMessage,
  mapPersistedThreadSummary,
} from "./utils";

interface ChatUser {
  id?: string | number;
  jurisdiction?: string | null;
}

interface UseChatThreadsOptions {
  isGuest: boolean;
  selectedJurisdiction: string;
  setSelectedJurisdiction: (jurisdiction: string) => void;
  token: string | null;
  user: ChatUser | null;
}

export function useChatThreads({
  isGuest,
  selectedJurisdiction,
  setSelectedJurisdiction,
  token,
  user,
}: UseChatThreadsOptions) {
  const [threads, setThreads] = useState<ChatThreadSummary[]>([]);
  const [messagesByThread, setMessagesByThread] = useState<Record<string, Message[]>>({});
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [isLoadingThreads, setIsLoadingThreads] = useState(false);
  const [hasHydratedThreads, setHasHydratedThreads] = useState(false);
  const [input, setInput] = useState("");
  const [isLoadingResponse, setIsLoadingResponse] = useState(false);
  const homePromptHandledRef = useRef(false);
  const createNewThreadRef = useRef<() => Promise<string | null>>(async () => null);
  const sendPromptRef = useRef<
    (promptText: string, preferredThreadId?: string | null) => Promise<void>
  >(async () => undefined);

  const activeMessages = useMemo(
    () => (activeThreadId ? (messagesByThread[activeThreadId] ?? []) : []),
    [activeThreadId, messagesByThread],
  );

  const guestThreadsKey = useMemo(() => `civilai_guest_threads_${user?.id ?? "guest"}`, [user?.id]);
  const guestActiveThreadKey = useMemo(
    () => `civilai_guest_active_thread_${user?.id ?? "guest"}`,
    [user?.id],
  );
  const legacyGuestMessagesKey = useMemo(
    () => `civilai_chat_${user?.id ?? "anonymous"}`,
    [user?.id],
  );

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
        const migratedThread = createGuestThread(
          selectedJurisdiction || user?.jurisdiction || null,
        );
        migratedThread.title = legacyMessages.find((message) => message.role === "user")?.content
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
  }, [
    guestActiveThreadKey,
    guestThreadsKey,
    isGuest,
    legacyGuestMessagesKey,
    selectedJurisdiction,
    setSelectedJurisdiction,
    user?.jurisdiction,
  ]);

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

        const payload = await parseApiResponse<PersistedThreadSummaryPayload[]>(response);
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
  }, [activeThreadId, isGuest, setSelectedJurisdiction, token, user]);

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
        const payload = await parseApiResponse<PersistedThreadDetailPayload>(response);
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

    const payload = await parseApiResponse<PersistedThreadSummaryPayload>(response);
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

    const payload = await parseApiResponse<PersistedThreadDetailPayload>(response);
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

  async function sendPrompt(promptText: string, preferredThreadId?: string | null): Promise<void> {
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
      const headers: HeadersInit = {};
      if (token && !isGuest) {
        headers.Authorization = `Bearer ${token}`;
      }
      const data = await queryCivilAi(userMessage.content, selectedJurisdiction, headers);

      assistantMessage = {
        id: `local-assistant-${Date.now()}`,
        role: "assistant",
        content: data.answer || "CivilAI could not find a grounded answer for that request.",
        accuracy: data.accuracy,
        resolvedJurisdiction: data.jurisdiction,
        navigation: data.navigation,
        sources: data.sources,
        timestamp: Date.now(),
      };
    } catch (caughtError) {
      assistantMessage = {
        id: `local-assistant-error-${Date.now()}`,
        role: "assistant",
        content: messageFromError(
          caughtError,
          "CivilAI could not reach the query service. Please try again in a moment.",
        ),
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
          const payload = await parseApiResponse<PersistedThreadSummaryPayload>(response);
          updateThreadSummary(mapPersistedThreadSummary(payload));
        }
      } catch {
        // Keep the local thread view even if persistence has a temporary hiccup.
      }
    }
  }

  async function handleSend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await sendPrompt(input);
  }

  useEffect(() => {
    createNewThreadRef.current = createNewThread;
    sendPromptRef.current = sendPrompt;
  });

  useEffect(() => {
    if (
      !hasHydratedThreads ||
      isLoadingThreads ||
      isLoadingResponse ||
      homePromptHandledRef.current
    ) {
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

  return {
    activeMessages,
    activeThreadId,
    handleNewChat,
    handleSelectThread,
    handleSend,
    input,
    isLoadingResponse,
    isLoadingThreads,
    setInput,
    threads,
  };
}
