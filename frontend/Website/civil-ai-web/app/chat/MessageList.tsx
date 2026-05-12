import type { RefObject } from "react";

import type { Message } from "./types";

interface MessageListProps {
  isLoadingResponse: boolean;
  messages: Message[];
  messagesEndRef: RefObject<HTMLDivElement | null>;
  threadCount: number;
}

export function MessageList({
  isLoadingResponse,
  messages,
  messagesEndRef,
  threadCount,
}: MessageListProps) {
  return (
    <div className="message-list">
      {messages.length === 0 ? (
        <div className="chat-empty">
          <h3>
            {threadCount
              ? "Open a research trail or start a fresh one."
              : "Ask the kind of question that slows a review down."}
          </h3>
          <p>
            Try “What does Broward County say about noise after 9 p.m.?” or “Summarize section 1-2
            for Cooper City and cite the source.”
          </p>
        </div>
      ) : (
        messages.map((message) => <MessageCard key={message.id} message={message} />)
      )}

      {isLoadingResponse ? (
        <article className="message-card message-assistant">
          <div className="spinner-row" style={{ justifyContent: "flex-start", marginTop: 0 }}>
            <span className="spinner" />
            <span className="muted-label">Checking the ordinance trail</span>
          </div>
        </article>
      ) : null}

      <div ref={messagesEndRef} />
    </div>
  );
}

function MessageCard({ message }: { message: Message }) {
  return (
    <article
      className={`message-card ${message.role === "user" ? "message-user" : "message-assistant"}`}
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
              <div className="accuracy-fill" style={{ width: `${message.accuracy.score}%` }} />
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
                const label = [source.section, source.subsection].filter(Boolean).join(" › ");
                const meta = [source.jurisdiction, source.page ? `p.${source.page}` : null]
                  .filter(Boolean)
                  .join(" · ");
                const text = meta ? `${label || "Code source"} · ${meta}` : label || "Code source";

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
          <p className="field-hint">Backend focus: {message.resolvedJurisdiction}</p>
        ) : null}
      </div>
    </article>
  );
}
