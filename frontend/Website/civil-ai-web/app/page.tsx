"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Reveal } from "./components/Reveal";
import { WorkspaceScaffold } from "./components/WorkspaceScaffold";
import { useAuth } from "./context/AuthContext";
import { CUSTOM_API_BASE } from "./lib/apiConfig";
import { savePendingChatPrompt } from "./lib/chatIntent";

export default function HomePage() {
  const { user, isAuthenticated, isLoading, continueAsGuest } = useAuth();
  const [jurisdictionCount, setJurisdictionCount] = useState<number | null>(null);
  const [promptDraft, setPromptDraft] = useState("");
  const [promptGateVisible, setPromptGateVisible] = useState(false);
  const [promptStatus, setPromptStatus] = useState("");
  const [isStartingPrompt, setIsStartingPrompt] = useState(false);
  const router = useRouter();

  useEffect(() => {
    let isMounted = true;

    async function loadJurisdictionCount() {
      try {
        const response = await fetch(`${CUSTOM_API_BASE}/jurisdictions`);
        if (!response.ok) {
          return;
        }

        const payload = (await response.json()) as {
          jurisdictions?: Array<{ name: string }>;
        };

        if (isMounted) {
          setJurisdictionCount(payload.jurisdictions?.length ?? 0);
        }
      } catch {
        if (isMounted) {
          setJurisdictionCount(null);
        }
      }
    }

    void loadJurisdictionCount();

    return () => {
      isMounted = false;
    };
  }, []);

  async function handlePromptStart(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const normalizedPrompt = promptDraft.trim();
    if (!normalizedPrompt) {
      setPromptStatus("Enter a municipal code question first so we can carry it into chat.");
      setPromptGateVisible(false);
      return;
    }

    savePendingChatPrompt(normalizedPrompt);
    setPromptStatus("");

    if (isAuthenticated) {
      setIsStartingPrompt(true);
      router.push("/chat");
      return;
    }

    setPromptGateVisible(true);
  }

  function handleAuthRoute(pathname: "/login" | "/register") {
    const normalizedPrompt = promptDraft.trim();
    if (normalizedPrompt) {
      savePendingChatPrompt(normalizedPrompt);
    }
    router.push(`${pathname}?next=${encodeURIComponent("/chat")}`);
  }

  async function handleGuestStart() {
    const normalizedPrompt = promptDraft.trim();
    if (normalizedPrompt) {
      savePendingChatPrompt(normalizedPrompt);
    }

    setIsStartingPrompt(true);
    try {
      await continueAsGuest();
      router.push("/chat");
    } finally {
      setIsStartingPrompt(false);
    }
  }

  if (isLoading) {
    return (
      <WorkspaceScaffold mainClassName="home-main">
        <div className="loading-shell">
          <p className="eyebrow">Booting workspace</p>
          <h1 className="hero-title">Preparing your CivilAI session.</h1>
          <p className="body-copy">
            We’re syncing the account state and the ordinance workspace now.
          </p>
        </div>
      </WorkspaceScaffold>
    );
  }

  return (
    <WorkspaceScaffold mainClassName="home-main">
      <Reveal className="hero-flow">
        <section className="hero-lead">
          <div className="hero-column">
            <p className="eyebrow">CivilAI · municipal code assistant</p>
            <h1 className="hero-title hero-title-rows">
              <span>
                Find the <span className="heading-accent">Rule</span>
              </span>
              <span>
                Cite the <span className="heading-accent heading-accent-field">Source</span>
              </span>
            </h1>
            <p className="body-copy hero-copy">
              CivilAI helps engineers, planners, and municipal teams turn dense ordinance PDFs into
              usable answers. Ask a project question, narrow by jurisdiction, and get a response
              tied back to the sections that support it.
            </p>
          </div>

          <div className="hero-ledger">
            <div className="desk-board" aria-hidden="true">
              <div className="desk-board-header">
                <span>AI review sheet</span>
                <span>Scale: code evidence</span>
              </div>
              <div className="desk-board-lines">
                <span className="desk-line" />
                <span className="desk-line" />
                <span className="desk-line" />
              </div>
              <div className="desk-stamp">
                CivilAI<br />
                Ordinance RAG<br />
                Source checked
              </div>
              <div className="desk-board-footer">
                <span>Structured DB</span>
                <span>Chroma</span>
              </div>
            </div>
            <div className="metric-line">
              <span className="metric-label">Indexed codes</span>
              <strong>{jurisdictionCount ?? "--"}</strong>
            </div>
            <div className="metric-line">
              <span className="metric-label">Retrieval model</span>
              <strong>Structured DB + Chroma</strong>
            </div>
            <div className="metric-line">
              <span className="metric-label">Current session</span>
              <strong>
                {isAuthenticated
                  ? user?.is_guest
                    ? user?.jurisdiction || "Guest workspace"
                    : user?.jurisdiction || user?.full_name || user?.username || "Signed in"
                  : "Preview mode"}
              </strong>
            </div>
          </div>
        </section>
      </Reveal>

      <Reveal className="sheet-band" delay={0.08}>
        <div className="section-grid">
          <div>
            <p className="eyebrow">Start from here</p>
            <h2 className="section-title">
              Ask the <span className="heading-accent">question</span> before the code slows you
              down.
            </h2>
          </div>
          <p className="section-copy">
            Start with the thing you need to decide: a setback, a permit threshold, a noise rule,
            a penalty, or a section summary. CivilAI carries that prompt into the chat workspace so
            the research starts where your work actually begins.
          </p>
        </div>

        <form className="composer-band" onSubmit={handlePromptStart}>
          <label className="field-label" htmlFor="homePrompt">
            First ordinance question
          </label>
          <textarea
            id="homePrompt"
            className="field-textarea zen-field zen-composer"
            value={promptDraft}
            onChange={(event) => setPromptDraft(event.target.value)}
            placeholder="What does Broward County say about noise after 9 p.m. near residential property?"
          />

          <div className="composer-actions">
            <button
              type="submit"
              className="button button-primary"
              disabled={isStartingPrompt}
            >
              {isAuthenticated
                ? isStartingPrompt
                  ? "Opening workspace..."
                  : "Start new chat"
                : "Continue with this prompt"}
            </button>
            <span className="support-copy">
              {isAuthenticated
                ? "Signed-in users get saved threads and account-level code focus."
                : "Try it as a guest first. Create an account when you want saved research history."}
            </span>
          </div>

          {promptStatus ? <div className="status-banner status-error">{promptStatus}</div> : null}
        </form>

        {promptGateVisible ? (
          <div className="inline-choice-row">
            <p className="section-copy">
              Your prompt is ready. Use guest mode for a quick check, or create an account if you
              want saved chats, preferred jurisdictions, and a record of the code trail.
            </p>
            <div className="inline-actions">
              <button
                type="button"
                className="button button-primary"
                onClick={() => handleAuthRoute("/register")}
              >
                Create account
              </button>
              <button
                type="button"
                className="button button-secondary"
                onClick={() => handleAuthRoute("/login")}
              >
                Sign in
              </button>
              <button
                type="button"
                className="button button-subtle"
                onClick={() => void handleGuestStart()}
                disabled={isStartingPrompt}
              >
                {isStartingPrompt ? "Opening guest workspace..." : "Continue as guest"}
              </button>
            </div>
          </div>
        ) : null}
      </Reveal>

      <Reveal className="sheet-band" delay={0.16}>
        <div className="three-streams">
          <div className="stream">
            <p className="eyebrow">Save the trail</p>
            <p className="section-copy">
              Ordinance research rarely ends with one question. Saved chats keep the reasoning,
              citations, and follow-up prompts together so you can return to the same project later.
            </p>
          </div>
          <div className="stream">
            <p className="eyebrow">Work in context</p>
            <p className="section-copy">
              Pick the city or county you care about and keep retrieval narrowed to the relevant
              municipal code instead of searching every indexed document at once.
            </p>
          </div>
          <div className="stream">
            <p className="eyebrow">Answer with evidence</p>
            <p className="section-copy">
              CivilAI is built for traceable answers, not loose summaries. Sources, confidence
              signals, and navigation details help you verify what the system used.
            </p>
          </div>
        </div>
      </Reveal>

      <Reveal className="sheet-band" delay={0.24}>
        <div className="section-grid">
          <div>
            <p className="eyebrow">What it actually does</p>
            <h2 className="section-title">CivilAI is structured for ordinance work, not general chat.</h2>
          </div>
          <div className="process-flow">
            <div className="process-step">
              <span className="process-mark">01</span>
              <p className="section-copy">
                It parses uploaded code PDFs into chapters, sections, and subsections.
              </p>
            </div>
            <div className="process-step">
              <span className="process-mark">02</span>
              <p className="section-copy">
                It uses a structured database and vector search to locate the right ordinance
                evidence before the answer is written.
              </p>
            </div>
            <div className="process-step">
              <span className="process-mark">03</span>
              <p className="section-copy">
                It returns grounded responses with source sections so engineers and municipal staff
                can trace where the answer came from.
              </p>
            </div>
          </div>
        </div>
      </Reveal>
    </WorkspaceScaffold>
  );
}
