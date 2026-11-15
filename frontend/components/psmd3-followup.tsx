"use client";

import { useEffect, useState } from "react";
import evidence from "@/data/psmd3-followup.json";

const DURATION = 300_000;
const STORAGE_KEY = "b5-psmd3-review-deadline-v1";

export function Psmd3Followup() {
  const [deadline, setDeadline] = useState<number | null>(null);
  const [remaining, setRemaining] = useState(300);
  const [ready, setReady] = useState(false);
  const [persistent, setPersistent] = useState(true);

  useEffect(() => {
    try {
      const saved = Number(localStorage.getItem(STORAGE_KEY));
      if (
        Number.isFinite(saved) &&
        saved > 0 &&
        saved <= Date.now() + DURATION
      ) {
        setDeadline(saved);
        setRemaining(Math.max(0, Math.ceil((saved - Date.now()) / 1000)));
      }
    } catch {
      setPersistent(false);
    }
    setReady(true);
  }, []);

  useEffect(() => {
    if (deadline === null) return;
    const update = () =>
      setRemaining(Math.max(0, Math.ceil((deadline - Date.now()) / 1000)));
    update();
    const timer = window.setInterval(update, 1000);
    window.addEventListener("focus", update);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", update);
    };
  }, [deadline]);

  const start = () => {
    const end = Date.now() + DURATION;
    try {
      localStorage.setItem(STORAGE_KEY, String(end));
    } catch {
      setPersistent(false);
    }
    setRemaining(300);
    setDeadline(end);
  };
  const unlocked = ready && deadline !== null && remaining === 0;

  return (
    <div className="pb-followup">
      <div className="pb-card-top">
        <span className="eyebrow">FROM GENE SIGNAL TO DRUG RESEARCH</span>
        <span className="badge rose">Exploratory follow-up</span>
      </div>
      <h3>The proteasome connection.</h3>
      <p>
        Following the saved genomic PSMD3 signal, this prepared literature
        review connects the gene to proteasome research and two existing myeloma
        drugs.
      </p>
      <div className="pb-drug-grid">
        {evidence.drugs.map((drug) => (
          <article className="pb-drug-card" key={drug.name}>
            <span className="eyebrow">APPROVED MYELOMA DRUG</span>
            <h4>{drug.name}</h4>
            <span className="badge sage">Proteasome inhibitor</span>
            <p>{drug.mechanism}</p>
            <p>{drug.context}</p>
            <a href={drug.url} target="_blank" rel="noreferrer">
              Official prescribing information ↗
            </a>
          </article>
        ))}
      </div>
      <div className="pb-expression-note">
        <strong>
          Shared proteasome biology; direct PSMD3 targeting is not established.
        </strong>
        <p>
          Approved proteasome inhibitors such as bortezomib act on the wider
          proteasome. Bortezomib has shown activity in HER2-positive breast
          cancer cell lines in preclinical studies. These findings do not
          establish clinical benefit in HER2-positive breast cancer or a
          PSMD3-specific drug match.
        </p>
      </div>
      <p>
        <a
          href="https://pubmed.ncbi.nlm.nih.gov/29069787/"
          target="_blank"
          rel="noreferrer"
        >
          Research-paper evidence · 2017 HER2+/ER+ cell-line study ↗
        </a>
      </p>
      <p className="pb-research-note">
        Research prototype. Not medical advice or a treatment recommendation.
      </p>
      <div className="pb-review-clock">
        <div>
          <strong>
            {unlocked
              ? "Evidence ready to explore"
              : "Five-minute review timer"}
          </strong>
          <p>
            Prepared evidence · no live model run. The timer unlocks the
            extended literature review below.
          </p>
        </div>
        {!unlocked && (
          <span
            className="pb-clock-digits"
            role="timer"
            aria-label="Time until follow-up unlocks"
          >
            {String(Math.floor(remaining / 60)).padStart(2, "0")}:
            {String(remaining % 60).padStart(2, "0")}
          </span>
        )}
        {deadline === null && (
          <button
            className="button button-dark"
            disabled={!ready}
            onClick={start}
          >
            Start five-minute review
          </button>
        )}
        {deadline !== null && !unlocked && (
          <progress
            max={300}
            value={300 - remaining}
            aria-label="Review timer progress"
          />
        )}
      </div>
      {!persistent && (
        <p role="status">
          Browser storage is unavailable. Keep this page open to retain the
          timer.
        </p>
      )}
      <div role="status" className="pb-unlock-status">
        {unlocked
          ? "Review complete. Extended literature is now available below."
          : deadline !== null
            ? "Extended literature unlocks when the timer finishes. Drug summaries remain available above."
            : "Start the timer to unlock the extended literature review."}
      </div>
      {unlocked && (
        <div data-testid="psmd3-extended-evidence">
          {evidence.papers.map((paper) => (
            <article className="pb-paper" key={paper.url}>
              <div>
                <span className="badge sage">Research-paper evidence</span>
                <span>{paper.context}</span>
              </div>
              <h4>
                <a href={paper.url} target="_blank" rel="noreferrer">
                  {paper.title} ↗
                </a>
              </h4>
              <p>{paper.summary}</p>
            </article>
          ))}
          <p className="pb-research-note">
            Added literature follow-up · {evidence.reviewed}. This comparison
            follows the saved genomic result; the model did not predict a drug
            response. Research prototype. Not medical advice or a treatment
            recommendation.
          </p>
        </div>
      )}
    </div>
  );
}
