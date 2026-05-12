"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { ProtectedRoute } from "../components/ProtectedRoute";
import { SiteHeader } from "../components/SiteHeader";
import { useAuth } from "../context/AuthContext";
import { ChatComposer } from "./ChatComposer";
import { ChatSetupPanel } from "./ChatSetupPanel";
import { MessageList } from "./MessageList";
import { useChatThreads } from "./useChatThreads";
import { useJurisdictions } from "./useJurisdictions";
import { usePdfUpload } from "./usePdfUpload";

function ChatWorkspace() {
  const { user, token, isGuest } = useAuth();
  const [isSetupExpanded, setIsSetupExpanded] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const buildApiHeaders = useCallback((): HeadersInit => {
    if (token && !isGuest) {
      return { Authorization: `Bearer ${token}` };
    }
    return {};
  }, [isGuest, token]);

  const {
    clearJurisdictionSearch,
    handleJurisdictionSearchChange,
    jurisdictionSearch,
    jurisdictions,
    loadJurisdictions,
    selectedJurisdiction,
    setSelectedJurisdiction,
  } = useJurisdictions({
    buildApiHeaders,
    defaultJurisdiction: user?.jurisdiction,
  });

  const {
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
  } = useChatThreads({
    isGuest,
    selectedJurisdiction,
    setSelectedJurisdiction,
    token,
    user,
  });

  const {
    fileInputRef,
    handleUpload,
    isUploading,
    setUploadFile,
    uploadError,
    uploadFile,
    uploadResult,
    uploadStatus,
  } = usePdfUpload({
    buildApiHeaders,
    loadJurisdictions,
    onJurisdictionDetected: setSelectedJurisdiction,
  });

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeMessages, activeThreadId]);

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
                  <span>
                    {threads.length} research thread{threads.length === 1 ? "" : "s"}
                  </span>
                  <span>{selectedJurisdiction || "All indexed codes"}</span>
                  <span>{uploadFile ? uploadFile.name : "No PDF selected"}</span>
                </div>
              </div>
            </div>

            {isSetupExpanded ? (
              <ChatSetupPanel
                activeThreadId={activeThreadId}
                fileInputRef={fileInputRef}
                isGuest={isGuest}
                isLoadingThreads={isLoadingThreads}
                isUploading={isUploading}
                jurisdictionSearch={jurisdictionSearch}
                jurisdictions={jurisdictions}
                threads={threads}
                uploadError={uploadError}
                uploadFile={uploadFile}
                uploadResult={uploadResult}
                uploadStatus={uploadStatus}
                onClearJurisdiction={clearJurisdictionSearch}
                onJurisdictionSearchChange={handleJurisdictionSearchChange}
                onNewChat={() => void handleNewChat()}
                onPdfChange={setUploadFile}
                onSelectThread={(threadId) => void handleSelectThread(threadId)}
                onUpload={handleUpload}
              />
            ) : null}
          </section>

          <section className="chat-workbench-section chat-workbench-no-memory">
            <section className="chat-conversation-sheet page-grid">
              <MessageList
                isLoadingResponse={isLoadingResponse}
                messages={activeMessages}
                messagesEndRef={messagesEndRef}
                threadCount={threads.length}
              />
              <ChatComposer
                input={input}
                isLoadingResponse={isLoadingResponse}
                onInputChange={setInput}
                onSubmit={handleSend}
              />
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
