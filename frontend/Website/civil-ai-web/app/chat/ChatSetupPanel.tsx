import type { FormEvent, RefObject } from "react";

import { ThreadList } from "./ThreadList";
import type { ChatThreadSummary, JurisdictionOption, UploadResult } from "./types";

interface ChatSetupPanelProps {
  activeThreadId: string | null;
  fileInputRef: RefObject<HTMLInputElement | null>;
  isGuest: boolean;
  isLoadingThreads: boolean;
  isUploading: boolean;
  jurisdictionSearch: string;
  jurisdictions: JurisdictionOption[];
  threads: ChatThreadSummary[];
  uploadError: string;
  uploadFile: File | null;
  uploadResult: UploadResult | null;
  uploadStatus: string;
  onClearJurisdiction: () => void;
  onJurisdictionSearchChange: (value: string) => void;
  onNewChat: () => void;
  onPdfChange: (file: File | null) => void;
  onSelectThread: (threadId: string) => void;
  onUpload: (event: FormEvent<HTMLFormElement>) => void;
}

export function ChatSetupPanel({
  activeThreadId,
  fileInputRef,
  isGuest,
  isLoadingThreads,
  isUploading,
  jurisdictionSearch,
  jurisdictions,
  threads,
  uploadError,
  uploadFile,
  uploadResult,
  uploadStatus,
  onClearJurisdiction,
  onJurisdictionSearchChange,
  onNewChat,
  onPdfChange,
  onSelectThread,
  onUpload,
}: ChatSetupPanelProps) {
  return (
    <div className="chat-setup-grid">
      <ThreadList
        activeThreadId={activeThreadId}
        isGuest={isGuest}
        isLoadingThreads={isLoadingThreads}
        threads={threads}
        onNewChat={onNewChat}
        onSelectThread={onSelectThread}
      />

      <div className="rail-block chat-control-card">
        <div>
          <p className="eyebrow">Jurisdiction Lens</p>
          <h3 className="feature-title">Aim the answer at the right code</h3>
        </div>
        <div className="field">
          <label className="field-label" htmlFor="jurisdictionSearch">
            Search scope
          </label>
          <div className="searchable-select-row">
            <input
              id="jurisdictionSearch"
              className="field-input"
              type="search"
              list="jurisdictionOptions"
              value={jurisdictionSearch}
              placeholder="Type a city or county..."
              autoComplete="off"
              onChange={(event) => onJurisdictionSearchChange(event.target.value)}
            />
            {jurisdictionSearch ? (
              <button
                type="button"
                className="button button-subtle compact-action"
                onClick={onClearJurisdiction}
              >
                Clear
              </button>
            ) : null}
          </div>
          <datalist id="jurisdictionOptions">
            {jurisdictions.map((option) => (
              <option key={option.name} value={option.name} />
            ))}
          </datalist>
        </div>
        <p className="upload-note">
          Type a city or county, or leave this blank to search all indexed codes.
        </p>
      </div>

      <div className="rail-block chat-control-card">
        <div>
          <p className="eyebrow">Document Intake</p>
          <h3 className="feature-title">Add the ordinance you need searched</h3>
        </div>
        <form className="form-grid" onSubmit={onUpload}>
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
              onChange={(event) => onPdfChange(event.target.files?.[0] ?? null)}
            />
          </div>
          {uploadFile ? (
            <p className="field-hint">
              Ready to upload: <strong>{uploadFile.name}</strong>
            </p>
          ) : (
            <p className="field-hint">
              CivilAI stores the PDF, extracts sections and subsections, then makes the document
              searchable for grounded answers.
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
          {uploadStatus ? <div className="status-banner status-success">{uploadStatus}</div> : null}
          {uploadError ? <div className="status-banner status-error">{uploadError}</div> : null}
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
                {uploadResult.sectionCount ?? 0} sections, {uploadResult.subsectionCount ?? 0}{" "}
                subsections
              </p>
              {uploadResult.focusSwitchedTo ? (
                <p className="field-hint">
                  Active code focus switched to <strong>{uploadResult.focusSwitchedTo}</strong>.
                </p>
              ) : null}
            </div>
          ) : null}
        </form>
      </div>
    </div>
  );
}
