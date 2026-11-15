"use client";

import { useId, useState } from "react";
import { Helix } from "@/components/helix";
import { Psmd3Followup } from "@/components/psmd3-followup";
import data from "@/data/plan-b.json";
import "./plan-b.css";

type Trial = (typeof data.baseline)[number];
const disclaimer =
  "Research prototype. Not medical advice. Matches do not establish eligibility or recommend treatment.";
function Arrow({ up = false }: { up?: boolean }) {
  return (
    <svg
      width="19"
      height="19"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <path
        d={up ? "M5 19 19 5M5 5h14v14" : "M4 12h15m-6-6 6 6-6 6"}
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
function Link({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a className="external-link" href={href} target="_blank" rel="noreferrer">
      {children}
      <Arrow up />
    </a>
  );
}
function TrialCard({
  trial,
  personalized = false,
}: {
  trial: Trial;
  personalized?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <article className={`pb-trial ${personalized ? "pb-featured" : ""}`}>
      {personalized && (
        <div className="pb-match-ribbon">
          <span>✳</span> BOTH BIOMARKERS EXPLICITLY NAMED{" "}
          <span className="pb-match-type">Trial-record evidence</span>
        </div>
      )}
      <button
        className="pb-trial-button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls={id}
      >
        <span className="pb-trial-top">
          <span className="eyebrow">{trial.nct_id}</span>
          <span>{trial.phase_label}</span>
          <span className="pb-status">
            <i />
            {trial.status_label}
          </span>
        </span>
        {personalized && <span className="pb-trial-nickname">INAVO122</span>}
        <span className="pb-trial-title">{trial.title}</span>
        <span className="pb-trial-bottom">
          <span className="pb-chip-list">
            <span className="badge sage">
              HER2-positive{" "}
              {trial.her2_context === "mixed" ? "cohort" : "listed"}
            </span>
            {trial.markers.includes("PIK3CA") && (
              <span className={`badge ${personalized ? "rose" : "neutral"}`}>
                PIK3CA {personalized ? "mutation named" : "mentioned"}
              </span>
            )}
            {trial.her2_context === "mixed" && (
              <span className="badge amber">
                Multiple cohorts · check criteria
              </span>
            )}
          </span>
          <span className="pb-expand">
            {open ? "Close details −" : "Explore trial +"}
          </span>
        </span>
      </button>
      {personalized && (
        <div className="pb-match-reason">
          <span className="eyebrow">WHY THIS IS A CLOSER MATCH</span>
          <p>
            The trial title names both <strong>PIK3CA-mutated</strong> and{" "}
            <strong>HER2-positive</strong> disease, and evaluates inavolisib
            with Phesgo. This is a direct match to the two selected biomarker
            descriptions.
          </p>
          <span>
            The literature and model results add research context; the trial
            record determines the match.
          </span>
        </div>
      )}
      {open && (
        <div className="pb-trial-details" id={id}>
          <div className="pb-detail-grid">
            <div>
              <span className="eyebrow">THERAPEUTIC AREA</span>
              <p>{trial.therapeutic_area}</p>
            </div>
            <div>
              <span className="eyebrow">RECORD DETAILS</span>
              <p>
                {trial.locations} locations · {trial.countries}
                <br />
                Minimum age: {trial.age_min || "Not specified"}
                {trial.age_max && ` · Maximum: ${trial.age_max}`}
                <br />
                {trial.sex === "ALL" ? "All sexes" : trial.sex.toLowerCase()}
              </p>
            </div>
            <div>
              <span className="eyebrow">BIOMARKER TAGS</span>
              <p>{trial.markers.join(" · ") || "None recorded"}</p>
            </div>
            <div>
              <span className="eyebrow">SPECIMENS</span>
              <p>
                {trial.specimen_requirements
                  .replaceAll("_", " ")
                  .replaceAll(";", " ·") || "Not specified in this record"}
              </p>
            </div>
          </div>
          <div className="pb-detail-foot">
            <p>
              Saved registry record. Full eligibility and current recruiting
              status require confirmation.
            </p>
            <Link href={trial.url}>Open trial registry</Link>
          </div>
        </div>
      )}
    </article>
  );
}
function Evidence() {
  const gene = data.genomic.PIK3CA;
  const reference = data.genomic.ERBB2;
  return (
    <section className="pb-evidence" aria-label="PIK3CA molecular evidence">
      <div className="pb-section-label">
        <span className="eyebrow">THE CONTEXT BEHIND THE MATCH</span>
        <span>Two independent sources. One clearer picture.</span>
      </div>
      <div className="pb-evidence-grid">
        <article className="pb-evidence-card pb-literature">
          <div className="pb-card-top">
            <span className="eyebrow">01 / KEENABLE</span>
            <span className="badge rose">Research-paper evidence</span>
          </div>
          <div
            className="pb-gene-connection"
            aria-label="HER2 and PIK3CA functional relationship"
          >
            <span>HER2</span>
            <span className="pb-connection-line">↔</span>
            <span>PIK3CA</span>
          </div>
          <h3>
            A functional interaction.
            <br />A reason to look closer.
          </h3>
          <p>
            The saved experimental literature reports that mutant PIK3CA
            accelerated HER2-driven tumors and resistance to anti-HER2 drug
            combinations in mouse models.
          </p>
          <div className="pb-evidence-conclusion">
            <span className="pb-tick">✓</span>
            <div>
              <strong>Functional interaction reported</strong>
              <span>Preclinical evidence · not direct physical binding</span>
            </div>
          </div>
          <details className="pb-source-details">
            <summary>
              Read the supporting research{" "}
              <span>{data.papers.length} sources +</span>
            </summary>
            <div>
              {data.papers.map((paper) => (
                <article className="pb-paper" key={paper.id}>
                  <div>
                    <span
                      className={`badge ${paper.primary ? "sage" : "neutral"}`}
                    >
                      {paper.primary ? "Primary experiment" : paper.kind}
                    </span>
                    <span>
                      {paper.year} · PMID {paper.id}
                    </span>
                  </div>
                  <h4>
                    <Link href={paper.url}>{paper.title}</Link>
                  </h4>
                  <p>{paper.summary}</p>
                  <small>{paper.context}</small>
                </article>
              ))}
              <Link href={data.sources.experimental}>
                Saved Keenable evidence
              </Link>
            </div>
          </details>
        </article>
        <article className="pb-evidence-card">
          <div className="pb-card-top">
            <span className="eyebrow">02 / GENOMIC INTELLIGENCE</span>
            <span className="badge rose">Model prediction</span>
          </div>
          <div className="pb-model-head">
            <span>PIK3CA</span>
            <span className="pb-regulatory-tag">Regulatory context</span>
          </div>
          <h3>
            Signals in the DNA.
            <br />
            Context for the question.
          </h3>
          <div className="pb-readout-pair">
            <div>
              <strong>{gene.promoter_probability}</strong>
              <span>Promoter probability</span>
            </div>
            <div>
              <strong>{gene.chromatin_calls}</strong>
              <span>Chromatin feature calls</span>
            </div>
          </div>
          <div className="pb-compare">
            <div>
              <span>PIK3CA</span>
              <i style={{ width: "100%" }} />
              <strong>{gene.chromatin_calls}</strong>
            </div>
            <div>
              <span>ERBB2</span>
              <i
                style={{
                  width: `${(Number(reference.chromatin_calls) / Number(gene.chromatin_calls)) * 100}%`,
                }}
              />
              <strong>{reference.chromatin_calls}</strong>
            </div>
            <span>Called chromatin features · breast-lineage cells</span>
          </div>
          <div className="pb-expression-note">
            <strong>Overexpression is not established.</strong>
            <p>
              This saved file excludes expression predictions. Promoter
              probability and chromatin calls describe regulatory context, not
              mutation-specific or patient-specific overexpression.
            </p>
          </div>
          <details className="pb-source-details">
            <summary>
              Inspect model provenance <span>+</span>
            </summary>
            <dl>
              <dt>Promoter model</dt>
              <dd>{gene.promoter_model}</dd>
              <dt>Chromatin model</dt>
              <dd>{gene.chromatin_model}</dd>
              <dt>H3K27ac / Pol2</dt>
              <dd>
                {gene.H3K27ac} / {gene.Pol2} calls
              </dd>
              <dt>Retrieved</dt>
              <dd>{gene.retrieved}</dd>
              <dt>Promoter request</dt>
              <dd>{gene.promoter_request_id}</dd>
              <dt>Chromatin request</dt>
              <dd>{gene.chromatin_request_id}</dd>
            </dl>
            <p>
              Reference DNA around the canonical start site. The models do not
              read a patient’s mutation or amplification.
            </p>
            <Link href={data.sources.genomic_notes}>
              Read the saved model notes
            </Link>
          </details>
        </article>
      </div>
    </section>
  );
}

function Psmd3Lead() {
  const model = data.genomic.PSMD3;
  return (
    <section
      className="pb-evidence"
      aria-label="PSMD3 exploratory research lead"
    >
      <div className="pb-section-label">
        <span className="eyebrow">FOLLOWING THE GENOMIC RESULTS</span>
        <span>Exploratory research lead</span>
      </div>
      <article className="pb-evidence-card">
        <div className="pb-card-top">
          <span className="eyebrow">PSMD3 / A QUESTION TO FOLLOW</span>
          <span className="badge rose">
            Model prediction + research-paper evidence
          </span>
        </div>
        <h3 style={{ marginTop: 24 }}>A new connection worth investigating.</h3>
        <p>
          The saved genomic analysis highlighted PSMD3’s promoter and chromatin
          activity. The saved literature also places PSMD3 in the HER2
          co-amplified region and reports a functional contribution to
          HER2-positive cell survival.
        </p>
        <div className="pb-readout-pair">
          <div>
            <strong>{model.promoter_probability}</strong>
            <span>Promoter probability</span>
          </div>
          <div>
            <strong>{model.chromatin_calls}</strong>
            <span>Chromatin feature calls</span>
          </div>
        </div>
        <div className="pb-expression-note">
          <strong>A research lead, not an established drug match.</strong>
          <p>
            These findings motivate further investigation. They do not establish
            direct PSMD3–HER2 binding, mutation-specific overexpression, or
            sensitivity to a myeloma drug. Broad regulatory activity is not
            evidence of HER2 specificity.
          </p>
        </div>
        <p>
          {data.psmd3_lead.trial_mentions === 0
            ? "No PSMD3 mention was found in the titles, biomarker tags, or therapeutic areas of this saved trial snapshot. This is not a claim that no trial exists elsewhere."
            : `${data.psmd3_lead.trial_mentions} saved trial records mention PSMD3; full criteria need review.`}
        </p>
        <details className="pb-source-details">
          <summary>
            Trace this research lead <span>Sources +</span>
          </summary>
          {data.psmd3_lead.papers.map((paper) => (
            <article className="pb-paper" key={paper.id}>
              <div>
                <span className="badge sage">Functional evidence</span>
                <span>
                  {paper.year} · PMID {paper.id}
                </span>
              </div>
              <h4>
                <Link href={paper.url}>{paper.title}</Link>
              </h4>
              <p>{paper.summary}</p>
              <small>{paper.context}</small>
            </article>
          ))}
          <p>
            Models: {model.promoter_model} and {model.chromatin_model}. Saved{" "}
            {model.retrieved}.
          </p>
          <Link href={data.sources.genomic_notes}>Saved genomic analysis</Link>
        </details>
        <Psmd3Followup />
      </article>
    </section>
  );
}

export default function PlanB() {
  const [mutation, setMutation] = useState(false);
  const [draftMutation, setDraftMutation] = useState("none");
  const [query, setQuery] = useState("");
  const [phase, setPhase] = useState("all");
  const [limit, setLimit] = useState(8);
  const [menu, setMenu] = useState(false);
  const [viewId, setViewId] = useState(0);
  const apply = (next: boolean) => {
    setMutation(next);
    setDraftMutation(next ? "PIK3CA" : "none");
    setQuery("");
    setPhase("all");
    setLimit(8);
    setViewId((id) => id + 1);
  };
  const rows = (mutation ? data.personalized : data.baseline).filter(
    (row) =>
      (phase === "all" || row.phase.includes(phase)) &&
      `${row.title} ${row.nct_id} ${row.markers.join(" ")}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const scrollToResearch = () => {
    setMenu(false);
    document.getElementById("research")?.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth",
    });
  };
  return (
    <div className="plan-b">
      <a className="skip-link" href="#research">
        Skip to trial matching
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
          aria-expanded={menu}
          onClick={() => setMenu(!menu)}
        >
          {menu ? "Close" : "Menu"}
        </button>
        <nav className={menu ? "nav-open" : ""} aria-label="Main navigation">
          <a
            href="#research"
            onClick={() => {
              apply(false);
              setMenu(false);
            }}
          >
            Find trials
          </a>
          <a
            href="#research"
            onClick={() => {
              apply(true);
              setMenu(false);
            }}
          >
            Personalize
          </a>
          <a href="#sources" onClick={() => setMenu(false)}>
            Our evidence
          </a>
          <a
            className="nav-cta"
            href="#research"
            onClick={() => setMenu(false)}
          >
            Explore your profile <Arrow up />
          </a>
        </nav>
      </header>
      <main>
        <section className="hero pb-hero">
          <div className="hero-copy">
            <div className="eyebrow hero-eyebrow">
              <span className="small-cross">✳</span> EVERY PROFILE TELLS A
              DIFFERENT STORY
            </div>
            <h1>
              More context.
              <br />
              <em>Closer matches.</em>
            </h1>
            <p>
              Start with HER2. Add a gene mutation. Connect the research and
              genomic signals to a more focused view of clinical trials.
            </p>
            <a className="button button-dark" href="#research">
              Find your starting point <Arrow up />
            </a>
            <div className="hero-note">
              <span className="status-dot" />A personalized medicine research
              experience.
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
              DNA-inspired study · conceptual visualization
            </div>
          </div>
          <div className="hero-footer">
            <span>ONE PROFILE. A MORE INFORMED PERSPECTIVE.</span>
            <a href="#research">
              Explore the connections <span>↓</span>
            </a>
          </div>
        </section>
        <section id="research" className="pb-workspace section-pad">
          <div className="section-topline">
            <span className="eyebrow">YOUR RESEARCH WORKSPACE</span>
            <span className="pb-saved">
              <span className="status-dot" />
              Curated research · 14 Nov 2026
            </span>
          </div>
          <div className="pb-workspace-title">
            <h2>
              Start with what
              <br />
              <em>makes it personal.</em>
            </h2>
            <p>
              From a broad biomarker match
              <br />
              to a more specific research question.
            </p>
          </div>
          <div className="pb-stage-switch" aria-label="Research stage">
            <button
              className={!mutation ? "active" : ""}
              aria-pressed={!mutation}
              onClick={() => apply(false)}
            >
              <span>01</span>
              <div>
                <strong>Find HER2 trials</strong>
                <small>Your starting point</small>
              </div>
              <Arrow />
            </button>
            <button
              className={mutation ? "active" : ""}
              aria-pressed={mutation}
              onClick={() => apply(true)}
            >
              <span>02</span>
              <div>
                <strong>Add molecular context</strong>
                <small>HER2 + PIK3CA</small>
              </div>
              <Arrow />
            </button>
          </div>
          <form
            className="pb-profile-form"
            onSubmit={(event) => {
              event.preventDefault();
              apply(draftMutation === "PIK3CA");
            }}
          >
            <div className="pb-tissue">
              <span className="eyebrow">RESEARCH PROFILE</span>
              <strong>Breast cancer</strong>
              <small>Two supported demo profiles</small>
            </div>
            <label>
              <span>Primary biomarker</span>
              <select aria-label="Primary biomarker" defaultValue="HER2">
                <option value="HER2">HER2 positive</option>
              </select>
            </label>
            <span className="pb-form-plus">+</span>
            <label>
              <span>Gene mutation</span>
              <select
                aria-label="Gene mutation"
                value={draftMutation}
                onChange={(event) => setDraftMutation(event.target.value)}
              >
                <option value="none">No mutation selected</option>
                <option value="PIK3CA">PIK3CA mutation</option>
              </select>
            </label>
            <button className="button button-dark" type="submit">
              Find matched trials <Arrow />
            </button>
          </form>
          <div key={viewId} className="pb-results">
            <div className="pb-result-intro">
              <div>
                <span className="eyebrow">
                  {mutation
                    ? "STAGE 02 / PERSONALIZED RESEARCH"
                    : "STAGE 01 / BIOMARKER MATCHING"}
                </span>
                <h3>
                  {mutation ? (
                    <>
                      HER2 <span>+</span> PIK3CA
                      <span className="pb-result-period">.</span>
                    </>
                  ) : (
                    <>
                      A starting point for <em>HER2.</em>
                    </>
                  )}
                </h3>
                <p>
                  {mutation
                    ? "A functional link in the literature. Regulatory context from DNA models. A trial that explicitly names both biomarkers."
                    : "Potential matches with HER2-positive disease listed in the saved trial title or therapeutic area. Full criteria still need review."}
                </p>
              </div>
              <div className="pb-result-count" aria-live="polite">
                <strong>
                  {mutation ? data.counts.matched : data.counts.baseline}
                </strong>
                <span>
                  {mutation
                    ? "explicit combined match"
                    : "HER2-positive cohorts listed"}
                </span>
              </div>
            </div>
            <div className="pb-funnel">
              <span>
                <strong>{data.counts.screened}</strong> trial records
              </span>
              <Arrow />
              <span className={!mutation ? "current" : ""}>
                <strong>{data.counts.baseline}</strong> HER2-positive listings
              </span>
              {mutation && (
                <>
                  <Arrow />
                  <span className="current">
                    <strong>{data.counts.matched}</strong> names both biomarkers
                  </span>
                </>
              )}
            </div>
            {mutation && <Evidence />}
            <div className="pb-list-heading">
              <div>
                <span className="eyebrow">
                  {mutation ? "YOUR FOCUSED SHORTLIST" : "EXPLORE THE TRIALS"}
                </span>
                <h3>
                  {mutation
                    ? "A more specific connection."
                    : "The next question starts here."}
                </h3>
              </div>
              <Link href={data.sources.trials}>Trial data source</Link>
            </div>
            <div className="toolbar pb-toolbar">
              <label className="search-field">
                <span aria-hidden="true">⌕</span>
                <input
                  aria-label="Search matched trials"
                  placeholder="Search by trial name, ID, or biomarker"
                  value={query}
                  onChange={(event) => {
                    setQuery(event.target.value);
                    setLimit(8);
                  }}
                />
                {query && (
                  <button
                    type="button"
                    aria-label="Clear search"
                    onClick={() => setQuery("")}
                  >
                    ×
                  </button>
                )}
              </label>
              <select
                aria-label="Filter trial phase"
                value={phase}
                onChange={(event) => {
                  setPhase(event.target.value);
                  setLimit(8);
                }}
              >
                <option value="all">All phases</option>
                <option value="PHASE1">Phase 1</option>
                <option value="PHASE2">Phase 2</option>
                <option value="PHASE3">Phase 3</option>
              </select>
              <span className="pb-shown-count">
                {rows.length} {rows.length === 1 ? "trial" : "trials"}
              </span>
            </div>
            <div className={`pb-trial-list ${mutation ? "personalized" : ""}`}>
              {rows.slice(0, limit).map((trial) => (
                <TrialCard
                  trial={trial}
                  key={trial.nct_id}
                  personalized={mutation}
                />
              ))}
              {rows.length === 0 && (
                <div className="empty-state">
                  <h3>No trials in this view.</h3>
                  <p>Try a different name or phase.</p>
                  <button
                    className="button button-dark"
                    onClick={() => {
                      setQuery("");
                      setPhase("all");
                    }}
                  >
                    Reset filters <Arrow />
                  </button>
                </div>
              )}
            </div>
            {rows.length > limit && (
              <button
                className="pb-load-more"
                onClick={() => setLimit(limit + 8)}
              >
                Explore more trials{" "}
                <span>
                  {Math.min(limit, rows.length)} of {rows.length}
                </span>
                <Arrow />
              </button>
            )}
            {!mutation ? (
              <div className="pb-refine">
                <span className="pb-refine-symbol">✳</span>
                <div>
                  <span className="eyebrow">ONE MORE PIECE OF THE PICTURE</span>
                  <h3>What changes with a PIK3CA mutation?</h3>
                  <p>
                    Bring the literature and genomic context into view, then
                    narrow the trial list.
                  </p>
                </div>
                <button
                  className="button button-dark"
                  onClick={() => {
                    apply(true);
                    scrollToResearch();
                  }}
                >
                  Add PIK3CA <Arrow />
                </button>
              </div>
            ) : (
              <div className="pb-review-groups">
                <details className="pb-review">
                  <summary>
                    <span>
                      Additional studies to review
                      <small>
                        Both biomarkers tagged; the combined eligibility
                        requirement is not established.
                      </small>
                    </span>
                    <span>{data.counts.review} studies +</span>
                  </summary>
                  <div>
                    {data.review.map((row) => (
                      <div className="pb-review-row" key={row.nct_id}>
                        <div>
                          <span className="eyebrow">{row.nct_id}</span>
                          <h4>
                            <Link href={row.url}>{row.title}</Link>
                          </h4>
                        </div>
                        <span className="badge amber">
                          {row.her2_context === "mixed"
                            ? "Mixed cohorts"
                            : "HER2 status not explicit"}
                        </span>
                      </div>
                    ))}
                  </div>
                </details>
                <details className="pb-review">
                  <summary>
                    <span>
                      Different HER2 status
                      <small>
                        HER2-negative, HER2-low, or triple-negative disease is
                        listed. Kept out of the shortlist.
                      </small>
                    </span>
                    <span>{data.counts.excluded} studies +</span>
                  </summary>
                  <div>
                    {data.excluded.map((row) => (
                      <div className="pb-review-row" key={row.nct_id}>
                        <div>
                          <span className="eyebrow">{row.nct_id}</span>
                          <h4>
                            <Link href={row.url}>{row.title}</Link>
                          </h4>
                        </div>
                        <span className="badge neutral">Different status</span>
                      </div>
                    ))}
                  </div>
                </details>
              </div>
            )}
            {mutation && <Psmd3Lead />}
            <p className="pb-research-note">{disclaimer}</p>
          </div>
        </section>
        <section id="sources" className="pb-sources section-pad">
          <div>
            <span className="eyebrow">SCIENCE YOU CAN TRACE</span>
            <h2>
              Every connection.
              <br />
              <em>A source behind it.</em>
            </h2>
            <p>
              This experience brings together saved research and model results.
              Evidence stays attached to its source, so you can follow the
              reasoning.
            </p>
          </div>
          <div className="pb-source-list">
            <Link href={data.sources.trials}>
              <span>
                <small>01 / CLINICAL TRIALS</small>Trial registry snapshot
              </span>
            </Link>
            <Link href={data.sources.experimental}>
              <span>
                <small>02 / KEENABLE</small>Experimental interaction evidence
              </span>
            </Link>
            <Link href={data.sources.genomic_notes}>
              <span>
                <small>03 / GENOMIC INTELLIGENCE</small>Promoter & chromatin
                model results
              </span>
            </Link>
            <span className="pb-source-version">
              Saved dataset · main / {data.source_commit.slice(0, 7)} · No live
              searches or model runs
            </span>
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
            More context.
            <br />
            More informed questions.
          </p>
          <a href="#research">
            Explore your profile <Arrow up />
          </a>
        </div>
        <div className="footer-bottom">
          <span>© 2026 B5 Research</span>
          <span>Research prototype. Not medical advice.</span>
          <a href="#">Back to top ↑</a>
        </div>
      </footer>
    </div>
  );
}
