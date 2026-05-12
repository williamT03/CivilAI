import { useCallback, useRef, useState } from "react";
import type { FormEvent } from "react";

import { parseApiResponse } from "../lib/apiClient";
import { CUSTOM_API_BASE } from "../lib/apiConfig";
import type { JurisdictionOption, UploadJobResponse, UploadResult } from "./types";

interface UsePdfUploadOptions {
  buildApiHeaders: () => HeadersInit;
  loadJurisdictions: () => Promise<JurisdictionOption[]>;
  onJurisdictionDetected: (jurisdiction: string) => void;
}

export function usePdfUpload({
  buildApiHeaders,
  loadJurisdictions,
  onJurisdictionDetected,
}: UsePdfUploadOptions) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);

  const waitForUploadJob = useCallback(
    async (jobId: string) => {
      for (let attempt = 0; attempt < 90; attempt += 1) {
        const response = await fetch(`${CUSTOM_API_BASE}/ingestion-jobs/${jobId}`, {
          headers: buildApiHeaders(),
        });
        const job = await parseApiResponse<UploadJobResponse>(response);

        if (job.status === "succeeded") {
          return job;
        }
        if (job.status === "failed") {
          throw new Error(job.error || "Indexing failed.");
        }

        setUploadStatus(`Indexing ${job.filename || "PDF"}... ${job.progress ?? 0}% complete`);
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
      }

      throw new Error("Indexing is still running. Refresh the filter in a moment.");
    },
    [buildApiHeaders],
  );

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
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

      const response = await fetch(`${CUSTOM_API_BASE}/upload-pdf`, {
        method: "POST",
        headers: buildApiHeaders(),
        body: formData,
      });

      const payload = await parseApiResponse<{
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
      }>(response);

      let parseResult = payload.parse_result;
      if (!parseResult && payload.job?.id) {
        setUploadStatus("Upload complete. Indexing the PDF now...");
        const completedJob = await waitForUploadJob(payload.job.id);
        parseResult = completedJob.result ?? undefined;
      }

      const indexedStatus = payload.replaced_existing
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
        onJurisdictionDetected(uploadedJurisdiction.name);
        setUploadStatus(`${indexedStatus} Code focus switched to ${uploadedJurisdiction.name}.`);
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
      setUploadError(caughtError instanceof Error ? caughtError.message : "Upload failed.");
    } finally {
      setIsUploading(false);
    }
  }

  return {
    fileInputRef,
    handleUpload,
    isUploading,
    setUploadFile,
    uploadError,
    uploadFile,
    uploadResult,
    uploadStatus,
  };
}
