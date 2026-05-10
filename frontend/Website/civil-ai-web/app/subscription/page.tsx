"use client";

import Link from "next/link";

import { Reveal } from "../components/Reveal";
import { WorkspaceScaffold } from "../components/WorkspaceScaffold";
import { useAuth } from "../context/AuthContext";

export default function SubscriptionPage() {
  const { isAuthenticated, isGuest, user } = useAuth();

  return (
    <WorkspaceScaffold mainClassName="subscription-main">
      <Reveal className="page-heading">
        <div>
          <p className="eyebrow">Subscription + access</p>
          <h1 className="hero-title">
            Start the <span className="heading-accent">research</span> now. Upgrade when the work
            needs <span className="heading-accent heading-accent-field">memory</span>.
          </h1>
        </div>
        <p className="section-copy page-heading-copy">
          CivilAI is built for people who need answers before a review meeting, field call, or
          submittal deadline. Try the workflow as a guest, keep the useful threads with an account,
          and grow into paid tools only when project volume makes continuity worth it.
        </p>
      </Reveal>

      <Reveal className="sheet-band" delay={0.08}>
        <div className="three-streams">
          <div className="stream">
            <p className="eyebrow">Current access</p>
            <h3 className="feature-title">
              {isAuthenticated
                ? isGuest
                  ? "Guest workspace"
                  : user?.username || "Signed-in workspace"
                : "Preview mode"}
            </h3>
            <p className="section-copy">
              {isAuthenticated
                ? isGuest
                  ? "Use the ordinance chat immediately for quick checks and PDF trials. When a thread becomes worth keeping, create an account before the trail matters."
                  : "Your account keeps saved chats, default jurisdiction focus, and uploaded documents connected to your recurring code work."
                : "Look around first, then enter as a guest for a quick test or create an account when you want saved research history."}
            </p>
          </div>

          <div className="stream">
            <p className="eyebrow">What stays open</p>
            <h3 className="feature-title">No signup wall before the first answer.</h3>
            <p className="section-copy">
              A civil workflow has to prove itself against a real ordinance question. Guest access
              lets users test retrieval, citations, and PDF parsing before committing project data.
            </p>
          </div>

          <div className="stream">
            <p className="eyebrow">Where paid value belongs</p>
            <h3 className="feature-title">Pay for the desk that remembers.</h3>
            <p className="section-copy">
              Future plans should earn their place through shared libraries, larger document
              throughput, team review, and reusable code research across active projects.
            </p>
          </div>
        </div>
      </Reveal>

      <div className="subscription-stack">
        <Reveal className="sheet-band subscription-plan-band" delay={0.14}>
          <div className="section-grid">
            <div>
              <p className="eyebrow">Access tiers</p>
              <h2 className="section-title">
                Choose the <span className="heading-accent">level</span> that matches the job size.
              </h2>
            </div>
            <p className="section-copy">
              Billing is not live in this build. This page shows how CivilAI separates quick
              evaluation, personal continuity, and future team research instead of hiding the
              practical difference behind vague plan names.
            </p>
          </div>

          <div className="rail-stack access-tier-grid">
            <div className="rail-block">
              <p className="eyebrow">Guest</p>
              <div className="ledger-list">
                <div className="ledger-row">
                  <strong>Fast evaluation</strong>
                  <span className="field-hint">Active now</span>
                </div>
                <p className="section-copy">
                  Run a real code question, upload a PDF, and check whether the source trail is
                  useful before adding a permanent profile.
                </p>
              </div>
            </div>

            <div className="rail-block">
              <p className="eyebrow">Registered account</p>
              <div className="ledger-list">
                <div className="ledger-row">
                  <strong>Personal continuity</strong>
                  <span className="field-hint">Active now</span>
                </div>
                <p className="section-copy">
                  Keep recurring jurisdictions, saved threads, and uploaded ordinance documents
                  tied to the person doing the research.
                </p>
              </div>
            </div>

            <div className="rail-block">
              <p className="eyebrow">Future team layer</p>
              <div className="ledger-list">
                <div className="ledger-row">
                  <strong>Shared municipal research</strong>
                  <span className="field-hint">Planned direction</span>
                </div>
                <p className="section-copy">
                  Shared libraries, team seats, reusable research packets, and clearer handoff
                  between engineering, planning, legal, and municipal reviewers.
                </p>
              </div>
            </div>
          </div>
        </Reveal>

        <Reveal className="sheet-band subscription-notes-band" delay={0.2}>
          <div className="rail-stack">
            <div className="rail-block">
              <p className="eyebrow">Why accounts matter</p>
              <p className="section-copy">
                Code research rarely ends in one question. Accounts help CivilAI keep the
                jurisdiction, the source trail, and the prior reasoning close when a project comes
                back for another revision.
              </p>
            </div>

            <div className="rail-block">
              <p className="eyebrow">What to do next</p>
              <div className="inline-actions">
                {isAuthenticated ? (
                  <>
                    <Link href="/chat" className="button button-primary">
                      Open chat
                    </Link>
                    <Link href="/account" className="button button-secondary">
                      Review account
                    </Link>
                  </>
                ) : (
                  <>
                    <Link href="/register" className="button button-primary">
                      Create account
                    </Link>
                    <Link href="/login" className="button button-secondary">
                      Sign in
                    </Link>
                  </>
                )}
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </WorkspaceScaffold>
  );
}
