# B5 Research — Plan B

A self-contained, two-stage research demo. Core research is prepared from `main` commit `3f9c5be`, bundled in `data/plan-b.json`, and rendered immediately. A separate curated PSMD3 drug follow-up adds linked primary literature and official labels. No backend, Python virtualenv, API key, or live sponsor service is required to run it.

```bash
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:3000. `npm run build` builds the production version; `npm start` serves it. `npm run typecheck` checks TypeScript.

## The two stages

1. **HER2 positive:** show potential matches from `clinical_trials/trial_ops.csv`. Of 528 records, 47 explicitly list HER2-positive disease in the title or therapeutic area, including mixed-cohort studies with a visible caveat. Search, phase filters, pagination, and registry details are interactive.
2. **HER2 positive + PIK3CA mutation:** show the saved Keenable interaction evidence and the Genomic Intelligence promoter/chromatin readouts, followed by the more specific trial shortlist. INAVO122 / NCT05894239 explicitly names both statuses in its title. Twelve other dual-tagged studies need further review; 15 listing a different HER2 status are kept out of the shortlist.

Trial relevance comes from the saved trial record, not from a model readout. The literature identifies functional evidence in mouse models; commentary/review/pathway papers are labelled separately. No blended scores are displayed.

**Source limitation:** `genomic_intelligence/her2_genes_dna_context_ranking.md` explicitly excludes expression predictions. The UI therefore shows PIK3CA promoter probability (0.9889), chromatin calls (41), and provenance, and says **overexpression is not established**. It does not relabel these as expression or mutation-specific predictions.

## Data provenance

Both profile views show PSMD3 promoter/chromatin readouts, HER2 interaction evidence, and immediately visible bortezomib and carfilzomib cards. Use **PSMD3 + drugs** in navigation or open `/#psmd3`. The **five-minute review timer** unlocks extended literature only. The timer persists across reloads in browser local storage; it is a presentation gate, not a security boundary or a ChatGPT lock. No live computation is implied. If storage is unavailable, the timer works while the component remains open.

`data/psmd3-followup.json` separately records sources for the requested drugs, 2017 and 2019 breast cell-line studies and a 2025 ASH preclinical myeloma abstract. The newer `keenable/psmd3_keenable_evidence.csv` supplies the 2019 PSMD3–HER2 interaction paper (PMID 31013812) and the 2017 study of both drugs (PMID 29069787). These are proteasome inhibitors, not established direct PSMD3 inhibitors; cell-line activity does not establish patient benefit. The saved trial snapshot has no PSMD3 mentions in the inspected fields; no global absence of trials is claimed. The genomic model did not predict drug response. `refresh:plan-b` preserves this separate curated file.

The expression card records the user-supplied team estimates (about 50% overall, 90% in HER2+ tumors, mean about 10 SD above normal, rare underexpression). It visibly labels them **team-reported, source verification pending**. The committed atlas CSV does not contain these exact measures. Cohort size, thresholds, HER2 definition and normal reference are not yet supplied; do not relabel these estimates as verified dataset associations or model predictions.

Source retrieval note: the ASH page at https://doi.org/10.1182/blood-2025-3926 blocked direct crawling (HTTP 403); its publisher-indexed abstract and DOI were checked. Crawl4AI also encountered anti-bot protection at https://pmc.ncbi.nlm.nih.gov/articles/PMC6801459/ (status 203); the article text was available through the web reader. Supporting sources are linked directly on each result.

Verified: production build and browser smoke checks covering the exact 300-second unlock with a virtual clock, persistence before/after reload, invalid stored values, both drug cards, existing trial interactions, no research API requests, and no horizontal overflow at 320/390/768px.

`data/plan-b.json` records the exact source commit and links to the frozen source files:

- `clinical_trials/trial_ops.csv`
- `keenable/her2_interactors_experimental.md`
- `keenable/her2_interactors_literature.md`
- `genomic_intelligence/her2_genes_dna_context_ranking.csv` and `.md`

To intentionally refresh the prepared data, fetch `origin/main` and run `npm run refresh:plan-b` (Python 3 standard library only). Review the output and resulting JSON before committing. This is a preparation helper; it never runs during `dev` or `build`.

The earlier platform API helpers and snapshot exporter remain available for the main platform work, but Plan B does not import them. `NEXT_PUBLIC_API_BASE` has no effect on Plan B.

## Visuals and verification

Ivory, plum, and coral styling; original animated DNA-inspired canvas art; responsive profile controls; instant stage transitions; expandable source evidence; keyboard-operable controls; reduced-motion support. Manrope is self-hosted under the included SIL OFL license. The helix is conceptual artwork, not a model output.

Browser smoke checks cover both profiles, pagination, search and phase filters, evidence expansion, provenance, exclusions, 320/390/768px layouts, and operation without research API calls. Research prototype. Not medical advice.
