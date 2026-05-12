import { useCallback, useEffect, useState } from "react";

import { fetchJurisdictions } from "../lib/chatApi";
import type { JurisdictionOption } from "./types";

interface UseJurisdictionsOptions {
  buildApiHeaders: () => HeadersInit;
  defaultJurisdiction?: string | null;
}

export function useJurisdictions({
  buildApiHeaders,
  defaultJurisdiction,
}: UseJurisdictionsOptions) {
  const [jurisdictions, setJurisdictions] = useState<JurisdictionOption[]>([]);
  const [selectedJurisdiction, setSelectedJurisdiction] = useState(() => {
    if (typeof window === "undefined") {
      return "";
    }
    return localStorage.getItem("civilai_selected_jurisdiction") ?? "";
  });

  const loadJurisdictions = useCallback(async () => {
    const nextJurisdictions = await fetchJurisdictions(buildApiHeaders());
    setJurisdictions(nextJurisdictions);
    return nextJurisdictions;
  }, [buildApiHeaders]);

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
    if (selectedJurisdiction || !defaultJurisdiction) {
      return;
    }

    const timeout = window.setTimeout(() => {
      setSelectedJurisdiction(defaultJurisdiction);
    }, 0);
    return () => window.clearTimeout(timeout);
  }, [defaultJurisdiction, selectedJurisdiction]);

  useEffect(() => {
    if (selectedJurisdiction) {
      localStorage.setItem("civilai_selected_jurisdiction", selectedJurisdiction);
    } else {
      localStorage.removeItem("civilai_selected_jurisdiction");
    }
  }, [selectedJurisdiction]);

  function handleJurisdictionSearchChange(value: string) {
    setSelectedJurisdiction(value.trim());
  }

  function clearJurisdictionSearch() {
    setSelectedJurisdiction("");
  }

  return {
    clearJurisdictionSearch,
    handleJurisdictionSearchChange,
    jurisdictionSearch: selectedJurisdiction,
    jurisdictions,
    loadJurisdictions,
    selectedJurisdiction,
    setSelectedJurisdiction,
  };
}
