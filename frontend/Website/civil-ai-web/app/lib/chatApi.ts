import { CUSTOM_API_BASE } from "./apiConfig";
import { parseApiResponse } from "./apiClient";

export interface QuerySourcePayload {
  jurisdiction?: string;
  section?: string;
  subsection?: string;
  title?: string;
  page?: number;
  score?: number;
  url?: string;
}

export interface QueryResponsePayload {
  answer?: string;
  accuracy?: {
    score: number;
    label: string;
    reason: string;
  };
  jurisdiction?: string | null;
  navigation?: {
    summary_preview?: string | null;
    top_chapters?: Array<{
      chapter_number: string;
      chapter_name: string;
    }>;
  };
  sources?: QuerySourcePayload[];
}

export interface JurisdictionOptionPayload {
  name: string;
  chunks: number;
}

export async function fetchJurisdictions(
  headers: HeadersInit,
): Promise<JurisdictionOptionPayload[]> {
  const response = await fetch(`${CUSTOM_API_BASE}/jurisdictions`, { headers });
  const payload = await parseApiResponse<{ jurisdictions?: JurisdictionOptionPayload[] }>(response);
  return payload.jurisdictions ?? [];
}

export async function queryCivilAi(
  question: string,
  jurisdiction: string,
  headers: HeadersInit,
): Promise<QueryResponsePayload> {
  const params = new URLSearchParams();
  params.set("q", question);
  if (jurisdiction) {
    params.set("jurisdiction", jurisdiction);
  }

  const response = await fetch(`${CUSTOM_API_BASE}/query?${params.toString()}`, { headers });
  return parseApiResponse<QueryResponsePayload>(response);
}
