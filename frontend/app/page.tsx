"use client";

import { useEffect, useId, useMemo, useState } from "react";
import { Helix } from "@/components/helix";
import { loadResearch } from "@/lib/api";
import type {
  GeneCandidate,
  Paper,
  ResearchData,
  TrialMatch,
} from "@/lib/types";

type Tab = "trials" | "genes" | "papers";
const DISCLAIMER =
  "Research prototype. Not medical advice. No treatment recommendations.";

function Arrow({
  diagonal = false,
  className = "",
}: {
  diagonal?: boolean;
  className?: string;
}) {
  return (
    <svg
      className={className}
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <path
        d={diagonal ? "M5 19 19 5M5 5h14v14" : "M4 12h15m-6-6 6 6-6 6"}
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
function Mark() {
  return (
    <svg
      viewBox="0 0 48 48"
      width="40"
      height="40"
      fill="none"
      aria-hidden="true"
    >
      <ellipse
        cx="24"
        cy="24"
        rx="20"
        ry="8"
        transform="rotate(-45 24 24)"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      <ellipse
        cx="24"
        cy="24"
        rx="20"
        ry="8"
        transform="rotate(45 24 24)"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      <circle cx="24" cy="24" r="3" fill="currentColor" />
    </svg>
  );
}
function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
function ExternalLink({
  href,
  children,
}: {
  href?: string;
  children: React.ReactNode;
}) {
  return href && /^https?:\/\//.test(href) ? (
    <a href={href} target="_blank" rel="noreferrer" className="external-link">
      {children}
      <Arrow diagonal />
    </a>
  ) : (
    <span>{children}</span>
  );
}
function PaperItem({ paper }: { paper: Paper }) {
  return (
    <article className="paper-item">
      <div className="paper-meta">
        <span>
          {paper.year ?? "Year unavailable"}{" "}
          <span className="dot-separator">·</span> {paper.paper_id}
        </span>
        <Badge tone={paper.reviewed ? "sage" : "amber"}>
          {paper.reviewed ? "Reviewed" : "Not yet reviewed"}
        </Badge>
        {paper.source === "mock" && <Badge tone="amber">Mock data</Badge>}
      </div>
      <h4>
        <ExternalLink href={paper.url}>{paper.title}</ExternalLink>
      </h4>
      <p>{paper.relation}</p>
      {paper.opposite_status && paper.opposite_status.length > 0 && (
        <p className="caution">
          Studies a different biomarker status:{" "}
          {paper.opposite_status.join(", ")}
        </p>
      )}
      {paper.why && paper.why.length > 0 && (
        <p className="paper-why">Included because: {paper.why.join("; ")}</p>
      )}
    </article>
  );
}
function TrialRow({ trial }: { trial: TrialMatch }) {
  const [expanded, setExpanded] = useState(false);
  const id = useId();
  return (
    <article className={`trial-row ${expanded ? "expanded" : ""}`}>
      <button
        className="trial-summary"
        aria-expanded={expanded}
        aria-controls={id}
        onClick={() => setExpanded(!expanded)}
      >
        <span className="trial-id">
          {trial.nct_id}
          <span>{trial.phase || "Phase not listed"}</span>
        </span>
        <span className="trial-main">
          <span className="trial-title">{trial.title}</span>
          <span className="trial-chips">
            {trial.biomarker_matches.map((match) => (
              <Badge
                key={match.gene}
                tone={
                  match.requirement === "required"
                    ? "sage"
                    : match.requirement === "conflicts"
                      ? "amber"
                      : "neutral"
                }
              >
                {match.biomarker}{" "}
                <span className="chip-status">{match.requirement}</span>
              </Badge>
            ))}
            {(trial.mock_inputs.length > 0 || trial.source === "mock") && (
              <Badge tone="amber">Mock inputs</Badge>
            )}
          </span>
        </span>
        <span className="trial-status">
          <span className="status-dot" />
          {trial.status || "Status unavailable"}
        </span>
        <span className="expand-icon">{expanded ? "−" : "+"}</span>
      </button>
      {expanded && (
        <div id={id} className="trial-detail">
          <div className="detail-intro">
            <span className="eyebrow">WHY THIS TRIAL APPEARS</span>
            <p>{trial.explanation}</p>
            <Badge tone="rose">Research-paper evidence + trial criteria</Badge>
          </div>
          <div className="criteria-grid">
            {trial.biomarker_matches.map((match) => (
              <div key={match.gene}>
                <span className="eyebrow">
                  {match.biomarker} · {match.requirement}
                </span>
                <p>
                  {match.evidence_text ||
                    "No requirement recorded for this biomarker."}
                </p>
              </div>
            ))}
          </div>
          {trial.unchecked_criteria.length > 0 && (
            <div className="notice">
              Still to check: {trial.unchecked_criteria.join(", ")} status is
              not recorded in this profile. A biomarker match does not establish
              full trial eligibility.
            </div>
          )}
          {trial.drugs.length > 0 && (
            <div className="drug-list">
              <span className="eyebrow">DRUGS & TARGETS</span>
              {trial.drugs.map((drug) => (
                <span key={drug.drug}>
                  {drug.matched_name}{" "}
                  <span className="muted">
                    → {drug.target_genes.join(", ")}
                  </span>
                </span>
              ))}
            </div>
          )}
          <div className="detail-paper-heading">
            <h4>Supporting research</h4>
            <span>
              {trial.supporting_papers.length} of{" "}
              {trial.supporting_papers_total} papers
            </span>
          </div>
          {trial.supporting_papers.map((paper) => (
            <PaperItem key={paper.paper_id} paper={paper} />
          ))}
          <div className="trial-foot">
            <span>
              Status from curated spreadsheet
              {trial.status_as_of ? ` · ${trial.status_as_of}` : ""}. Confirm
              current status and full eligibility.
            </span>
            <ExternalLink href={trial.url}>View trial registry</ExternalLink>
          </div>
          <p className="result-disclaimer">{DISCLAIMER}</p>
        </div>
      )}
    </article>
  );
}
function GenePanel({
  gene,
  data,
  onClose,
}: {
  gene: GeneCandidate;
  data: ResearchData;
  onClose: () => void;
}) {
  const context = data.contexts.find((row) => row.gene === gene.gene);
  const papers = data.papers.filter((paper) =>
    gene.paper_ids.includes(paper.paper_id),
  );
  return (
    <section className="gene-panel" aria-label={`${gene.gene} evidence`}>
      <div className="gene-panel-heading">
        <div>
          <span className="eyebrow">GENE EVIDENCE</span>
          <h3>{gene.gene}</h3>
        </div>
        <button
          className="round-button"
          onClick={onClose}
          aria-label="Close gene evidence"
        >
          ×
        </button>
      </div>
      <div className="gene-provenance">
        <Badge tone="rose">Model prediction</Badge>
        {gene.source === "mock" && (
          <Badge tone="amber">Candidate source: mock</Badge>
        )}
        {context?.source === "mock" && (
          <Badge tone="amber">Model data: mock</Badge>
        )}
        <span>
          {context?.assembly} {context?.region}
        </span>
      </div>
      {context ? (
        <>
          <p className="gene-summary">
            {context.model_output.summary ||
              "Seven-task genomic model profile from the saved pipeline output."}
          </p>
          <div className="readouts">
            {Object.entries(context.model_output.task_scores ?? {}).map(
              ([task, value]) => (
                <div key={task}>
                  <span>
                    {task === "composite" ? "Gene finder + expression" : task}
                  </span>
                  <strong>
                    {value === null ? "Unavailable" : value.toFixed(3)}
                  </strong>
                </div>
              ),
            )}
          </div>
          <p className="fine-print">
            Normalized model readouts, not relevance scores. These
            reference-sequence models do not establish a patient’s amplification
            or mutation status.
          </p>
        </>
      ) : (
        <p className="notice">Model output is not available for this gene.</p>
      )}
      <div className="notice">
        <strong>Atlas mapping is being built.</strong> Cohort associations and
        the two related-gene result groups are not available yet. These are
        literature-derived candidate genes, not a sequence-similarity search.
      </div>
      <div className="detail-paper-heading">
        <h4>Papers mentioning this candidate</h4>
        <span>{papers.length} papers</span>
      </div>
      {papers.slice(0, 4).map((paper) => (
        <PaperItem key={paper.paper_id} paper={paper} />
      ))}
      {papers.length > 4 && (
        <p className="fine-print">
          Showing the first 4 linked papers. Explore the full collection in the
          paper library.
        </p>
      )}
      <p className="result-disclaimer">{DISCLAIMER}</p>
    </section>
  );
}

export default function Home() {
  const [data, setData] = useState<ResearchData | null>(null);
  const [source, setSource] = useState("Loading research");
  const [notices, setNotices] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const [tab, setTab] = useState<Tab>("trials");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [gene, setGene] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => {
    let active = true;
    loadResearch()
      .then((result) => {
        if (active) {
          setData(result.data);
          setSource(result.source);
          setNotices(result.notices);
          setError(null);
        }
      })
      .catch((err) => {
        if (active)
          setError(
            err instanceof Error
              ? err.message
              : "Research data is unavailable.",
          );
      });
    return () => {
      active = false;
    };
  }, [reload]);
  const changeTab = (next: Tab) => {
    setTab(next);
    setQuery("");
    setFilter("all");
    setGene(null);
  };
  const term = query.trim().toLowerCase();
  const trials = useMemo(
    () =>
      (data?.trials ?? []).filter(
        (trial) =>
          (filter === "all" || trial.tier === filter) &&
          [
            trial.title,
            trial.nct_id,
            ...trial.drugs.map((drug) => drug.drug),
            ...trial.related_genes.map((row) => row.gene),
          ]
            .join(" ")
            .toLowerCase()
            .includes(term),
      ),
    [data, term, filter],
  );
  const genes = (data?.genes ?? []).filter((row) =>
    row.gene.toLowerCase().includes(term),
  );
  const papers = (data?.papers ?? []).filter(
    (paper) =>
      (filter !== "reviewed" || paper.reviewed) &&
      [paper.title, paper.paper_id, ...(paper.genes_mentioned ?? [])]
        .join(" ")
        .toLowerCase()
        .includes(term),
  );
  const tiers = [
    ...new Map(
      (data?.trials ?? []).map((trial) => [trial.tier, trial.tier_label]),
    ).entries(),
  ];
  const selectedGene = data?.genes.find((row) => row.gene === gene);
  const navigate = () => setMenuOpen(false);

  return (
    <>
      <a className="skip-link" href="#research">
        Skip to research workspace
      </a>
      <header className="site-header">
        <a className="wordmark" href="#" aria-label="B5 Research home">
          <Mark />
          <span>
            B5<span className="wordmark-sub">RESEARCH</span>
          </span>
        </a>
        <button
          className="menu-toggle"
          aria-label="Toggle navigation"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen(!menuOpen)}
        >
          {menuOpen ? "Close" : "Menu"}
        </button>
        <nav
          className={menuOpen ? "nav-open" : ""}
          aria-label="Main navigation"
        >
          <a onClick={navigate} href="#approach">
            Our approach
          </a>
          <a
            onClick={() => {
              navigate();
              changeTab("papers");
            }}
            href="#research"
          >
            The evidence
          </a>
          <a onClick={navigate} href="#principles">
            Our principles
          </a>
          <a
            onClick={() => {
              navigate();
              changeTab("trials");
            }}
            href="#research"
            className="nav-cta"
          >
            Explore the research <Arrow diagonal />
          </a>
        </nav>
      </header>
      <main>
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-copy">
            <div className="eyebrow hero-eyebrow">
              <span className="small-cross">✳</span> A CLOSER LOOK AT WHAT
              CONNECTS US
            </div>
            <h1 id="hero-title">
              Follow the
              <br />
              <em>evidence.</em>
              <br />
              Find new
              <br />
              possibilities.
            </h1>
            <p>
              From a single biomarker profile to a wider view of the science.
              Connecting research, clinical trials, and genomic intelligence.
            </p>
            <a className="button button-dark" href="#research">
              Explore the research <Arrow diagonal />
            </a>
            <div className="hero-note">
              <span className="status-dot" />
              Built for curiosity. Grounded in evidence.
            </div>
          </div>
          <div className="hero-art">
            <div className="art-grid" />
            <div className="orbit orbit-one" />
            <div className="orbit orbit-two" />
            <Helix />
            <div className="art-label label-top">
              <span className="crosshair">+</span> THE SCIENCE OF CONNECTION
            </div>
            <div className="art-label label-bottom">
              <span className="art-index">B5 / 001</span>
              <span>
                DNA-inspired study
                <br />
                Conceptual visualization
              </span>
            </div>
            <span className="art-coordinate">
              BIOLOGY × INFORMATION × POSSIBILITY
            </span>
          </div>
          <div className="hero-footer">
            <span>PERSONALIZED MEDICINE, THROUGH A RESEARCH LENS</span>
            <a href="#approach">
              A different perspective <span>↓</span>
            </a>
          </div>
        </section>
        <section
          className="profile-strip"
          aria-label="Current research profile"
        >
          <div>
            <span className="eyebrow">OUR STARTING POINT</span>
            <span className="profile-tissue">
              {data?.profile.tissue ?? "Loading profile"}
              {data && " cancer research"}
            </span>
          </div>
          <div className="profile-biomarkers">
            {data?.profile.biomarkers.map((row) => (
              <span key={row.gene}>
                <span className="profile-plus">+</span>
                <strong>{row.biomarker}</strong> {row.status}
              </span>
            ))}
          </div>
          <a href="#research" aria-label="Explore this profile">
            <Arrow diagonal />
          </a>
        </section>
        <section id="approach" className="approach section-pad">
          <div className="section-topline">
            <span className="eyebrow">01 / OUR APPROACH</span>
            <span className="section-note">
              One profile. Two paths of inquiry.
            </span>
          </div>
          <div className="approach-layout">
            <h2>
              Biology is connected.
              <br />
              <span className="muted">
                Our research
                <br />
                should be, too.
              </span>
            </h2>
            <div className="approach-paths">
              <p className="approach-intro">
                Look at the same question from two perspectives. Follow what the
                literature reports, then explore what DNA models can reveal.
              </p>
              <a
                href="#research"
                onClick={() => changeTab("trials")}
                className="path-link"
              >
                <span className="path-number">01</span>
                <div>
                  <span className="eyebrow">PAPERS → CLINICAL TRIALS</span>
                  <h3>Let the evidence lead.</h3>
                  <p>
                    Find potentially relevant trials and understand the research
                    and criteria behind every match.
                  </p>
                </div>
                <Arrow diagonal />
              </a>
              <a
                href="#research"
                onClick={() => changeTab("genes")}
                className="path-link"
              >
                <span className="path-number">02</span>
                <div>
                  <span className="eyebrow">DNA MODELS → PAN-CANCER ATLAS</span>
                  <h3>Explore another dimension.</h3>
                  <p>
                    Inspect candidate-gene model profiles. Sequence findings and
                    cohort mapping are the next step.
                  </p>
                </div>
                <Arrow diagonal />
              </a>
            </div>
          </div>
        </section>
        <section id="research" className="research-section section-pad">
          <div className="section-topline">
            <span className="eyebrow">02 / THE RESEARCH WORKSPACE</span>
            <span className="live-label">
              <span className="status-dot" />
              {source}
            </span>
          </div>
          <div className="workspace-title">
            <h2>
              A profile.
              <br />
              <em>A world to explore.</em>
            </h2>
            <p>
              Go beyond the result.
              <br />
              See the reasoning, inspect the sources,
              <br />
              and follow the questions that matter.
            </p>
          </div>
          <div className="workspace">
            <div className="workspace-profile">
              <div>
                <span className="eyebrow">CURRENT PROFILE</span>
                <h3>
                  {data?.profile.tissue ?? "Loading"}
                  <span className="profile-divider">/</span>
                  {data?.profile.biomarkers
                    .map((row) => `${row.biomarker} ${row.status}`)
                    .join(" + ") ?? "Loading biomarker profile"}
                </h3>
              </div>
              <Badge>Research use only</Badge>
            </div>
            <div className="tabs" role="tablist" aria-label="Research views">
              {(
                [
                  {
                    id: "trials",
                    label: "Trial matches",
                    count: data?.trials.length,
                  },
                  {
                    id: "genes",
                    label: "Gene explorer",
                    count: data?.genes.length,
                  },
                  {
                    id: "papers",
                    label: "Paper library",
                    count: data?.papers.length,
                  },
                ] as const
              ).map((item) => (
                <button
                  key={item.id}
                  role="tab"
                  id={`tab-${item.id}`}
                  aria-selected={tab === item.id}
                  aria-controls="research-panel"
                  tabIndex={tab === item.id ? 0 : -1}
                  onClick={() => changeTab(item.id)}
                  onKeyDown={(event) => {
                    const order: Tab[] = ["trials", "genes", "papers"];
                    const index = order.indexOf(tab);
                    let next: Tab | undefined;
                    if (event.key === "ArrowRight")
                      next = order[(index + 1) % 3];
                    if (event.key === "ArrowLeft")
                      next = order[(index + 2) % 3];
                    if (event.key === "Home") next = "trials";
                    if (event.key === "End") next = "papers";
                    if (next) {
                      event.preventDefault();
                      changeTab(next);
                      document.getElementById(`tab-${next}`)?.focus();
                    }
                  }}
                >
                  {item.label}
                  <span>{item.count ?? "—"}</span>
                </button>
              ))}
            </div>
            <div
              id="research-panel"
              role="tabpanel"
              aria-labelledby={`tab-${tab}`}
              tabIndex={0}
              className="research-panel"
            >
              {error ? (
                <div className="empty-state" role="alert">
                  <h3>Research is temporarily unavailable.</h3>
                  <p>{error}</p>
                  <button
                    className="button button-dark"
                    onClick={() => {
                      setError(null);
                      setReload(reload + 1);
                    }}
                  >
                    Try again <Arrow />
                  </button>
                </div>
              ) : !data ? (
                <div className="loading-state" role="status">
                  <span className="loading-orbit" />
                  <p>Bringing the evidence together…</p>
                </div>
              ) : (
                <>
                  {notices.map((notice) => (
                    <div className="notice" role="status" key={notice}>
                      {notice}
                    </div>
                  ))}
                  <div className="panel-heading">
                    <div>
                      <span className="eyebrow">
                        {tab === "trials"
                          ? "APPROACH 01 · RESEARCH-PAPER EVIDENCE + TRIAL CRITERIA"
                          : tab === "genes"
                            ? "APPROACH 02 · CANDIDATE GENE PROFILES"
                            : "THE SOURCES BEHIND THE SCIENCE"}
                      </span>
                      <h3>
                        {tab === "trials"
                          ? "Connections worth investigating."
                          : tab === "genes"
                            ? "A closer look at the candidates."
                            : "Research you can trace."}
                      </h3>
                      <p>
                        {tab === "trials"
                          ? "Grouped by biomarker criteria, with the reasoning behind each match."
                          : tab === "genes"
                            ? "Literature-derived candidates with exploratory model readouts. Atlas mapping is pending."
                            : "Published papers and search hits, with review status visible throughout."}
                      </p>
                    </div>
                  </div>
                  <div className="toolbar">
                    <label className="search-field">
                      <svg
                        width="18"
                        height="18"
                        viewBox="0 0 24 24"
                        fill="none"
                        aria-hidden="true"
                      >
                        <circle
                          cx="10"
                          cy="10"
                          r="6"
                          stroke="currentColor"
                          strokeWidth="1.5"
                        />
                        <path
                          d="m15 15 5 5"
                          stroke="currentColor"
                          strokeWidth="1.5"
                        />
                      </svg>
                      <input
                        aria-label={`Search ${tab}`}
                        placeholder={
                          tab === "trials"
                            ? "Search trials, drugs, or genes"
                            : tab === "genes"
                              ? "Find a gene"
                              : "Search papers, IDs, or genes"
                        }
                        value={query}
                        onChange={(event) => {
                          setQuery(event.target.value);
                          if (tab === "genes") setGene(null);
                        }}
                      />
                      {query && (
                        <button
                          aria-label="Clear search"
                          onClick={() => setQuery("")}
                        >
                          ×
                        </button>
                      )}
                    </label>
                    {tab !== "genes" && (
                      <select
                        aria-label={
                          tab === "trials"
                            ? "Filter by trial tier"
                            : "Filter by review status"
                        }
                        value={filter}
                        onChange={(event) => setFilter(event.target.value)}
                      >
                        <option value="all">
                          {tab === "trials"
                            ? "All match groups"
                            : "All review statuses"}
                        </option>
                        {tab === "trials" ? (
                          tiers.map(([key, label]) => (
                            <option key={key} value={key}>
                              {label}
                            </option>
                          ))
                        ) : (
                          <option value="reviewed">Reviewed papers only</option>
                        )}
                      </select>
                    )}
                  </div>
                  <div aria-live="polite" className="result-count">
                    {tab === "trials"
                      ? `${trials.length} trials`
                      : tab === "genes"
                        ? `${genes.length} candidate genes`
                        : `${papers.length} papers`}
                    {term && ` matching “${query}”`}
                  </div>
                  {tab === "trials" && (
                    <div className="trial-groups">
                      {tiers.map(([key, label]) => {
                        const group = trials.filter((row) => row.tier === key);
                        return (
                          group.length > 0 && (
                            <section key={key} className="trial-group">
                              <div className="group-heading">
                                <span className="group-icon">↗</span>
                                <h4>{label}</h4>
                                <span>{group.length} trials</span>
                              </div>
                              {group.map((trial) => (
                                <TrialRow key={trial.nct_id} trial={trial} />
                              ))}
                            </section>
                          )
                        );
                      })}
                      {trials.length === 0 && (
                        <div className="empty-state">
                          <h3>No trials to show.</h3>
                          <p>
                            {data.trials.length
                              ? "Try a different search or match group."
                              : "Trial matching results have not been generated yet."}
                          </p>
                        </div>
                      )}
                    </div>
                  )}
                  {tab === "genes" && (
                    <>
                      <div className="notice subtle">
                        <strong>In progress:</strong> genes found in the input
                        sequence, genes with similar model profiles, and
                        Pan-Cancer Atlas associations will appear when Approach
                        2 is complete. Genomic Intelligence does not perform
                        sequence-similarity search.
                      </div>
                      <div className="gene-grid">
                        {genes.map((row) => (
                          <button
                            key={row.gene}
                            className={`gene-tile ${gene === row.gene ? "selected" : ""}`}
                            aria-pressed={gene === row.gene}
                            onClick={() =>
                              setGene(gene === row.gene ? null : row.gene)
                            }
                          >
                            <span className="gene-tile-top">
                              {data.profile.biomarkers.some(
                                (b) => b.gene === row.gene,
                              )
                                ? "PROFILE GENE"
                                : "CANDIDATE"}
                              <Arrow diagonal />
                            </span>
                            <strong>{row.gene}</strong>
                            <span>
                              {row.paper_ids.length} linked papers
                              {row.source === "mock" ? " · Mock source" : ""}
                            </span>
                          </button>
                        ))}
                      </div>
                      {genes.length === 0 && (
                        <div className="empty-state">
                          <h3>No candidate genes found.</h3>
                          <p>Try another gene symbol.</p>
                        </div>
                      )}
                      {selectedGene && (
                        <GenePanel
                          key={selectedGene.gene}
                          gene={selectedGene}
                          data={data}
                          onClose={() => setGene(null)}
                        />
                      )}
                    </>
                  )}
                  {tab === "papers" && (
                    <div className="paper-library">
                      {papers.map((paper) => (
                        <PaperItem key={paper.paper_id} paper={paper} />
                      ))}
                      {papers.length === 0 && (
                        <div className="empty-state">
                          <h3>No papers found.</h3>
                          <p>Try another search or review status.</p>
                        </div>
                      )}
                    </div>
                  )}
                  {data.meta.has_mock_data && (
                    <div className="mock-notice">
                      <span className="small-cross">✳</span>
                      <p>
                        <strong>Transparent by design.</strong> Some inputs are
                        labelled mock: {data.meta.mock_inputs.join(", ")}.
                        Labels stay attached to the evidence.
                      </p>
                    </div>
                  )}
                </>
              )}
            </div>
            <div className="workspace-footer">
              <span className="shield-icon">◇</span>
              {data?.meta.disclaimer ?? DISCLAIMER} Results do not establish
              eligibility or recommend treatment.
            </div>
          </div>
        </section>
        <section id="principles" className="principles section-pad">
          <div className="section-topline">
            <span className="eyebrow">03 / OUR PRINCIPLES</span>
            <span className="section-note">
              Clarity is part of the science.
            </span>
          </div>
          <h2>
            Different evidence.
            <br />
            <em>Clearly distinguished.</em>
          </h2>
          <div className="principle-grid">
            <article>
              <span className="principle-symbol">↗</span>
              <span className="eyebrow">01 / RESEARCH-PAPER EVIDENCE</span>
              <h3>Follow the source.</h3>
              <p>
                Every paper has a link and a visible review status. Read what
                supports a connection and what still needs a closer look.
              </p>
            </article>
            <article>
              <span className="principle-symbol">✳</span>
              <span className="eyebrow">02 / MODEL PREDICTION</span>
              <h3>Question the prediction.</h3>
              <p>
                DNA models offer exploratory readouts. Reference-sequence
                results are not clinically validated and do not establish a
                patient’s alterations.
              </p>
            </article>
            <article>
              <span className="principle-symbol">⌘</span>
              <span className="eyebrow">
                03 / DATASET-SUPPORTED ASSOCIATION
              </span>
              <h3>Keep the context.</h3>
              <p>
                Pan-Cancer Atlas mapping is coming next. Cohort-level
                associations describe patterns across patients, not an
                individual outcome.
              </p>
            </article>
          </div>
        </section>
        <section className="closing">
          <span className="eyebrow">
            BETTER QUESTIONS. DEEPER UNDERSTANDING.
          </span>
          <h2>
            There’s more
            <br />
            to <em>discover.</em>
          </h2>
          <a className="button button-dark" href="#research">
            Follow your curiosity <Arrow diagonal />
          </a>
          <div className="closing-orbit" aria-hidden="true">
            <Mark />
          </div>
        </section>
      </main>
      <footer className="site-footer">
        <div className="footer-top">
          <a className="wordmark" href="#">
            <Mark />
            <span>
              B5<span className="wordmark-sub">RESEARCH</span>
            </span>
          </a>
          <p>
            Connecting the signals.
            <br />
            Opening new questions.
          </p>
          <a
            href="https://github.com/Contactashmeetsingh/B5-hackers"
            target="_blank"
            rel="noreferrer"
          >
            Explore the project <Arrow diagonal />
          </a>
        </div>
        <div className="footer-bottom">
          <span>© {new Date().getFullYear()} B5 Research</span>
          <span>{DISCLAIMER}</span>
          <a href="#">Back to top ↑</a>
        </div>
      </footer>
    </>
  );
}
