"use client";

import Link from "next/link";

import { Reveal } from "../components/Reveal";
import { WorkspaceScaffold } from "../components/WorkspaceScaffold";

export default function AboutPage() {
  return (
    <WorkspaceScaffold mainClassName="about-main">
      <Reveal className="page-heading">
        <div>
          <p className="eyebrow">About CivilAI</p>
          <h1 className="hero-title">
            Municipal <span className="heading-accent">code research</span> built like an
            engineering desk.
          </h1>
        </div>
        <p className="section-copy page-heading-copy">
          CivilAI is a focused research workspace for people who need to interpret local code
          without losing the evidence trail. It combines PDF parsing, structured storage, semantic
          retrieval, and saved chat history so ordinance questions become easier to check, revisit,
          and explain.
        </p>
      </Reveal>

      <Reveal className="sheet-band" delay={0.08}>
        <div className="section-grid">
          <div>
            <p className="eyebrow">Why it exists</p>
            <h2 className="section-title">
              Because <span className="heading-accent">project decisions</span> should not depend
              on PDF scavenger hunts.
            </h2>
          </div>
          <p className="section-copy">
            Civil engineers, planners, consultants, attorneys, and municipal staff often need fast
            answers from long ordinance documents. Standard search can miss context, and general AI
            can drift. CivilAI is designed to keep the model close to the actual code sections and
            make the answer easier to inspect.
          </p>
        </div>
      </Reveal>

      <Reveal className="sheet-band" delay={0.16}>
        <div className="three-streams">
          <div className="stream">
            <p className="eyebrow">1 · Upload</p>
            <h3 className="feature-title">Add ordinance PDFs.</h3>
            <p className="section-copy">
              Uploaded codes are stored by the backend and immediately sent through the parsing
              pipeline so they can become searchable workspace material.
            </p>
          </div>
          <div className="stream">
            <p className="eyebrow">2 · Structure</p>
            <h3 className="feature-title">Turn pages into code hierarchy.</h3>
            <p className="section-copy">
              The parser extracts chapters, sections, subsections, summaries, source filenames, and
              navigation metadata. That structure is saved in SQLite and mirrored into Chroma.
            </p>
          </div>
          <div className="stream">
            <p className="eyebrow">3 · Ask</p>
            <h3 className="feature-title">Query the code like a workspace.</h3>
            <p className="section-copy">
              The chat retrieves exact references, keyword matches, and semantic matches before the
              model drafts an answer from the narrowed evidence.
            </p>
          </div>
        </div>
      </Reveal>

      <Reveal className="sheet-band" delay={0.24}>
        <div className="section-grid">
          <div>
            <p className="eyebrow">What happens behind the scenes</p>
            <h2 className="section-title">
              A <span className="heading-accent">structured retrieval</span> stack, not a generic
              chatbot wrapper.
            </h2>
          </div>
          <div className="process-flow">
            <div className="process-step">
              <span className="process-mark">01</span>
              <p className="section-copy">
                The backend saves PDFs in the data folder and parses them into normalized document,
                chapter, section, and subsection records.
              </p>
            </div>
            <div className="process-step">
              <span className="process-mark">02</span>
              <p className="section-copy">
                The retrieval toolkit builds a navigation map, resolves jurisdiction aliases, and
                checks for exact section or subsection references in the user question.
              </p>
            </div>
            <div className="process-step">
              <span className="process-mark">03</span>
              <p className="section-copy">
                Chroma and keyword search find supporting evidence. The system merges, reranks, and
                returns a compact context package to the language model.
              </p>
            </div>
            <div className="process-step">
              <span className="process-mark">04</span>
              <p className="section-copy">
                The frontend displays the answer with source sections, jurisdiction focus, accuracy
                estimate, and saved chat continuity when the user is signed in.
              </p>
            </div>
          </div>
        </div>
      </Reveal>

      <Reveal className="sheet-band" delay={0.32}>
        <div className="section-grid">
          <div>
            <p className="eyebrow">Who it helps</p>
            <h2 className="section-title">
              For teams that need <span className="heading-accent">code answers</span> they can
              defend.
            </h2>
          </div>
          <div className="rail-stack">
            <div className="rail-block">
              <p className="eyebrow">Engineering teams</p>
              <p className="section-copy">
                Quickly check requirements, summarize sections, and keep a citation trail attached
                to recurring project questions.
              </p>
            </div>
            <div className="rail-block">
              <p className="eyebrow">Municipal staff</p>
              <p className="section-copy">
                Make local code easier to navigate for repeat questions, internal reviews, and
                resident-facing explanations.
              </p>
            </div>
            <div className="rail-block">
              <p className="eyebrow">Consultants and reviewers</p>
              <p className="section-copy">
                Move faster through unfamiliar jurisdictions while keeping the final answer tied to
                the source document.
              </p>
            </div>
          </div>
        </div>
      </Reveal>

      <Reveal className="sheet-band" delay={0.4}>
        <div className="section-grid">
          <div>
            <p className="eyebrow">Start working</p>
            <h2 className="section-title">
              Bring a real <span className="heading-accent">ordinance question</span> and test the
              trail.
            </h2>
          </div>
          <div className="rail-stack">
            <p className="section-copy">
              The fastest way to understand CivilAI is to ask the kind of question that usually
              slows your review down. Try a section summary, a requirement lookup, or a jurisdiction
              specific code question.
            </p>
            <div className="inline-actions">
              <Link href="/chat" className="button button-primary">
                Open chat
              </Link>
              <Link href="/" className="button button-secondary">
                Start from home
              </Link>
            </div>
          </div>
        </div>
      </Reveal>
    </WorkspaceScaffold>
  );
}
