import type { ChatThreadSummary } from "./types";

interface ThreadListProps {
  activeThreadId: string | null;
  isGuest: boolean;
  isLoadingThreads: boolean;
  threads: ChatThreadSummary[];
  onNewChat: () => void;
  onSelectThread: (threadId: string) => void;
}

export function ThreadList({
  activeThreadId,
  isGuest,
  isLoadingThreads,
  threads,
  onNewChat,
  onSelectThread,
}: ThreadListProps) {
  return (
    <div className="rail-block chat-control-card chat-memory-panel">
      <div className="message-meta">
        <div>
          <p className="eyebrow">Research Threads</p>
          <h3 className="feature-title">Keep every lookup traceable</h3>
        </div>
        <button type="button" className="button button-subtle" onClick={onNewChat}>
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
                onClick={() => onSelectThread(thread.id)}
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
          No research threads yet. Start with one real code question and CivilAI will keep the
          lookup grouped for follow-up.
        </p>
      )}
      <p className="upload-note">
        {isGuest
          ? "Guest mode keeps history in this browser for quick tests."
          : "Signed-in accounts keep the source trail available across sessions."}
      </p>
    </div>
  );
}
