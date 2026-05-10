"use client";

import Link from "next/link";

import { Reveal } from "../components/Reveal";
import { WorkspaceScaffold } from "../components/WorkspaceScaffold";
import { useAuth } from "../context/AuthContext";

const launchAccess = [
  {
    name: "Free Launch Access",
    badge: "Open now",
    price: "$0",
    limit: "Unlimited while CivilAI builds its first userbase",
    description:
      "Ask municipal-code questions, review cited sources, save threads, and test PDF workflows without a paywall.",
    features: [
      "Cited ordinance answers",
      "Saved chats for registered users",
      "Jurisdiction filters",
      "PDF upload and indexing",
    ],
  },
  {
    name: "Future Pro",
    badge: "Coming later",
    price: "Not active",
    limit: "No paid upgrade required right now",
    description:
      "When payments are introduced, Pro should focus on heavier teams, shared libraries, higher reliability, and support.",
    features: [
      "Team workspaces",
      "Shared research packets",
      "Higher hosted capacity",
      "Priority support",
    ],
  },
];

export default function SubscriptionPage() {
  const { isAuthenticated, isGuest, user } = useAuth();

  return (
    <WorkspaceScaffold mainClassName="subscription-main">
      <Reveal className="page-heading">
        <div>
          <p className="eyebrow">Launch access</p>
          <h1 className="hero-title">
            CivilAI is <span className="heading-accent">free</span> while the platform earns trust
            with real users.
          </h1>
        </div>
        <p className="section-copy page-heading-copy">
          The goal right now is simple: let engineers, planners, students, and municipal reviewers
          try CivilAI on real ordinance questions before pricing gets in the way. Payments can come
          later, after the workflow proves useful.
        </p>
      </Reveal>

      <Reveal className="sheet-band" delay={0.08}>
        <div className="section-grid">
          <div>
            <p className="eyebrow">Current access</p>
            <h2 className="section-title">
              {isAuthenticated
                ? isGuest
                  ? "Guest mode is free."
                  : `${user?.username || "Your account"} has free access.`
                : "Create an account when you want saved research."}
            </h2>
          </div>
          <p className="section-copy">
            Free access keeps the feedback loop open: ask questions, check citations, upload
            documents, and see where CivilAI helps the review process move faster.
          </p>
        </div>
      </Reveal>

      <div className="subscription-stack">
        <Reveal className="sheet-band subscription-plan-band" delay={0.14}>
          <div className="section-grid">
            <div>
              <p className="eyebrow">Access tiers</p>
              <h2 className="section-title">
                No paywall during the <span className="heading-accent">launch</span> phase.
              </h2>
            </div>
            <p className="section-copy">
              The billing structure stays in the backend for later, but all current users can use
              the app for free while the userbase grows.
            </p>
          </div>

          <div className="rail-stack access-tier-grid">
            {launchAccess.map((plan) => (
              <div className="rail-block" key={plan.name}>
                <div className="ledger-list">
                  <div className="ledger-row">
                    <strong>{plan.name}</strong>
                    <span className="field-hint">{plan.badge}</span>
                  </div>
                  <div className="ledger-row">
                    <strong>{plan.price}</strong>
                    <span className="field-hint">{plan.limit}</span>
                  </div>
                  <p className="section-copy">{plan.description}</p>
                  <div className="chapter-list">
                    {plan.features.map((feature) => (
                      <span className="chapter-chip" key={feature}>
                        {feature}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Reveal>

        <Reveal className="sheet-band subscription-notes-band" delay={0.2}>
          <div className="rail-stack">
            <div className="rail-block">
              <p className="eyebrow">Why free first</p>
              <p className="section-copy">
                CivilAI needs usage, feedback, and real municipal-code edge cases before paid plans
                should shape the product. Free access helps discover what engineers actually need.
              </p>
            </div>

            <div className="rail-block">
              <p className="eyebrow">Start using it</p>
              <div className="inline-actions">
                {isAuthenticated ? (
                  <Link href="/chat" className="button button-primary">
                    Open chat
                  </Link>
                ) : (
                  <>
                    <Link href="/register" className="button button-primary">
                      Create free account
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
