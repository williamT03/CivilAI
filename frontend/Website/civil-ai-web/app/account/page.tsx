"use client";

import { useEffect, useMemo, useState } from "react";

import { ProtectedRoute } from "../components/ProtectedRoute";
import { Reveal } from "../components/Reveal";
import { WorkspaceScaffold } from "../components/WorkspaceScaffold";
import { useAuth } from "../context/AuthContext";

const CUSTOM_API_BASE =
  process.env.NEXT_PUBLIC_CUSTOM_API_BASE ?? "http://localhost:8000/api/custom";
const AUTH_API_BASE =
  process.env.NEXT_PUBLIC_AUTH_API_BASE ?? "http://localhost:8000/api/auth";

interface JurisdictionOption {
  name: string;
  chunks: number;
}

interface UploadedDocument {
  id: number;
  filename: string;
  document_title?: string | null;
  stored_path: string;
  chapter_count?: number | null;
  section_count?: number | null;
  subsection_count?: number | null;
  replaced_existing: boolean;
  uploaded_at: string;
}

interface SavedChatSummary {
  id: number;
  title: string;
  message_count: number;
  updated_at: string;
}

function formatDate(value?: string | null) {
  if (!value) {
    return "Not available yet";
  }

  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function AccountContent() {
  const { user, token, isGuest, updateProfile } = useAuth();
  const [fullName, setFullName] = useState("");
  const [jurisdiction, setJurisdiction] = useState("");
  const [jurisdictions, setJurisdictions] = useState<JurisdictionOption[]>([]);
  const [uploads, setUploads] = useState<UploadedDocument[]>([]);
  const [savedChats, setSavedChats] = useState<SavedChatSummary[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    setFullName(user?.full_name ?? "");
    setJurisdiction(user?.jurisdiction ?? "");
  }, [user]);

  useEffect(() => {
    let isMounted = true;

    async function loadJurisdictions() {
      try {
        const response = await fetch(`${CUSTOM_API_BASE}/jurisdictions`);
        if (!response.ok) {
          return;
        }
        const payload = (await response.json()) as {
          jurisdictions?: JurisdictionOption[];
        };
        if (isMounted) {
          setJurisdictions(payload.jurisdictions ?? []);
        }
      } catch {
        if (isMounted) {
          setJurisdictions([]);
        }
      }
    }

    void loadJurisdictions();

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (!token || isGuest) {
      setUploads([]);
      setSavedChats([]);
      return;
    }

    let isMounted = true;

    async function loadWorkspaceData() {
      try {
        const [uploadsResponse, chatsResponse] = await Promise.all([
          fetch(`${AUTH_API_BASE}/uploads`, {
            headers: {
              Authorization: `Bearer ${token}`,
            },
          }),
          fetch(`${AUTH_API_BASE}/chats`, {
            headers: {
              Authorization: `Bearer ${token}`,
            },
          }),
        ]);

        if (!isMounted) {
          return;
        }

        if (uploadsResponse.ok) {
          setUploads((await uploadsResponse.json()) as UploadedDocument[]);
        } else {
          setUploads([]);
        }

        if (chatsResponse.ok) {
          setSavedChats((await chatsResponse.json()) as SavedChatSummary[]);
        } else {
          setSavedChats([]);
        }
      } catch {
        if (isMounted) {
          setUploads([]);
          setSavedChats([]);
        }
      }
    }

    void loadWorkspaceData();

    return () => {
      isMounted = false;
    };
  }, [isGuest, token]);

  const stats = useMemo(
    () => [
      { label: "Username", value: isGuest ? "guest" : user?.username ?? "--" },
      { label: "Session", value: isGuest ? "Guest workspace" : "Registered account" },
      { label: "Saved chats", value: isGuest ? "Local only" : String(savedChats.length) },
      { label: "Uploaded docs", value: isGuest ? "Guest upload" : String(uploads.length) },
    ],
    [isGuest, savedChats.length, uploads.length, user],
  );

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");
    setIsSaving(true);

    try {
      await updateProfile({
        full_name: fullName.trim() || "",
        jurisdiction: jurisdiction || "",
      });
      if (typeof window !== "undefined") {
        window.localStorage.setItem("civilai_selected_jurisdiction", jurisdiction || "");
      }
      setSuccess("Your account settings were saved.");
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "We could not save your account changes.",
      );
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <WorkspaceScaffold mainClassName="account-main">
      <Reveal className="page-heading">
        <div>
          <p className="eyebrow">Account workspace</p>
          <h1 className="hero-title account-title">
            Keep every <span className="heading-accent">code trail</span> tied to your work.
          </h1>
        </div>
        <p className="section-copy page-heading-copy">
          Your account turns CivilAI from a quick lookup tool into a reusable research desk:
          preferred jurisdictions stay ready, ordinance uploads remain visible, and saved chats
          keep the reasoning behind project decisions from disappearing.
        </p>
      </Reveal>

      <Reveal className="sheet-band account-info-band" delay={0.08}>
        <div className="four-streams account-overview-strip">
          {stats.map((stat) => (
            <div key={stat.label} className="stream">
              <p className="eyebrow">{stat.label}</p>
              <h3 className="feature-title">{stat.value}</h3>
            </div>
          ))}
        </div>
      </Reveal>

      <div className="account-stack">
        <Reveal className="sheet-band profile-band" delay={0.14}>
          <div className="section-grid">
            <div>
              <p className="eyebrow">Profile</p>
              <h2 className="section-title">
                Set the <span className="heading-accent">jurisdiction</span> CivilAI should reach
                for first.
              </h2>
            </div>
            <p className="section-copy">
              {isGuest
                ? "Guest preferences can guide this browser session, but signed-in accounts are better when the same code questions will come back later."
                : "Signed-in profiles help every new chat begin closer to the city, county, or code family you use most."}
            </p>
          </div>

          {error ? <div className="status-banner status-error">{error}</div> : null}
          {success ? <div className="status-banner status-success">{success}</div> : null}

          <form className="profile-form" onSubmit={handleSubmit}>
            <div className="field">
              <label className="field-label" htmlFor="email">
                Email
              </label>
              <input
                id="email"
                className="field-input zen-field"
                type="email"
                value={isGuest ? "Guest session" : user?.email ?? ""}
                disabled
              />
            </div>

            <div className="field">
              <label className="field-label" htmlFor="fullName">
                Full name
              </label>
              <input
                id="fullName"
                className="field-input zen-field"
                type="text"
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                placeholder="How should CivilAI address you?"
              />
            </div>

            <div className="field">
              <label className="field-label" htmlFor="jurisdiction">
                Default code focus
              </label>
              <select
                id="jurisdiction"
                className="field-select zen-field"
                value={jurisdiction}
                onChange={(event) => setJurisdiction(event.target.value)}
              >
                <option value="">No default focus</option>
                {jurisdictions.map((option) => (
                  <option key={option.name} value={option.name}>
                    {option.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="inline-actions">
              <button type="submit" className="button button-primary" disabled={isSaving}>
                {isSaving ? "Saving..." : isGuest ? "Save guest preferences" : "Save changes"}
              </button>
            </div>
          </form>

          <div className="micro-ledger">
            <span>Joined: {formatDate(user?.created_at)}</span>
            <span>Last login: {isGuest ? "This browser session" : formatDate(user?.last_login)}</span>
          </div>
        </Reveal>

        <Reveal className="sheet-band memory-band" delay={0.2}>
          <div className="rail-stack">
            <div className="rail-block">
              <p className="eyebrow">Recent uploads</p>
              {isGuest ? (
                <p className="section-copy">
                  Guest uploads can prove the parser works, but account uploads are better for
                  project documents you expect to revisit.
                </p>
              ) : uploads.length ? (
                <div className="ledger-list">
                  {uploads.slice(0, 5).map((upload) => (
                    <div key={upload.id} className="ledger-row">
                      <div>
                        <strong>{upload.document_title || upload.filename}</strong>
                        <p className="field-hint">
                          {upload.section_count ?? 0} sections · {upload.subsection_count ?? 0} subsections
                        </p>
                      </div>
                      <span className="field-hint">{formatDate(upload.uploaded_at)}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="section-copy">
                  Upload an ordinance PDF from chat and CivilAI will add it here with its parsed
                  sections, subsections, and account trail.
                </p>
              )}
            </div>

            <div className="rail-block">
              <p className="eyebrow">Recent saved chats</p>
              {isGuest ? (
                <p className="section-copy">
                  Guest chat history stays local in this browser. Create an account when a thread
                  becomes part of a real review record.
                </p>
              ) : savedChats.length ? (
                <div className="ledger-list">
                  {savedChats.slice(0, 5).map((chat) => (
                    <div key={chat.id} className="ledger-row">
                      <div>
                        <strong>{chat.title}</strong>
                        <p className="field-hint">{chat.message_count} messages</p>
                      </div>
                      <span className="field-hint">{formatDate(chat.updated_at)}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="section-copy">
                  Start a code question in chat and CivilAI will keep the answer, source list, and
                  follow-up trail with your account.
                </p>
              )}
            </div>
          </div>
        </Reveal>
      </div>
    </WorkspaceScaffold>
  );
}

export default function AccountPage() {
  return (
    <ProtectedRoute>
      <AccountContent />
    </ProtectedRoute>
  );
}
