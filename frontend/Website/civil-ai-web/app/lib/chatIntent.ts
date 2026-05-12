"use client";

const PENDING_CHAT_PROMPT_KEY = "civilai_pending_chat_prompt";

export interface PendingChatPrompt {
  prompt: string;
  source: "home";
  createdAt: number;
}

function readStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }

  return window.sessionStorage;
}

export function savePendingChatPrompt(prompt: string): void {
  const storage = readStorage();
  const normalizedPrompt = prompt.trim();

  if (!storage) {
    return;
  }

  if (!normalizedPrompt) {
    storage.removeItem(PENDING_CHAT_PROMPT_KEY);
    return;
  }

  const payload: PendingChatPrompt = {
    prompt: normalizedPrompt,
    source: "home",
    createdAt: Date.now(),
  };

  storage.setItem(PENDING_CHAT_PROMPT_KEY, JSON.stringify(payload));
}

export function readPendingChatPrompt(): PendingChatPrompt | null {
  const storage = readStorage();
  if (!storage) {
    return null;
  }

  const rawValue = storage.getItem(PENDING_CHAT_PROMPT_KEY);
  if (!rawValue) {
    return null;
  }

  try {
    const parsed = JSON.parse(rawValue) as PendingChatPrompt;
    if (parsed && typeof parsed.prompt === "string" && parsed.prompt.trim()) {
      return {
        prompt: parsed.prompt.trim(),
        source: "home",
        createdAt: typeof parsed.createdAt === "number" ? parsed.createdAt : Date.now(),
      };
    }
  } catch {
    storage.removeItem(PENDING_CHAT_PROMPT_KEY);
    return null;
  }

  storage.removeItem(PENDING_CHAT_PROMPT_KEY);
  return null;
}

export function consumePendingChatPrompt(): PendingChatPrompt | null {
  const storage = readStorage();
  const pendingPrompt = readPendingChatPrompt();

  if (storage) {
    storage.removeItem(PENDING_CHAT_PROMPT_KEY);
  }

  return pendingPrompt;
}

export function clearPendingChatPrompt(): void {
  const storage = readStorage();
  storage?.removeItem(PENDING_CHAT_PROMPT_KEY);
}
