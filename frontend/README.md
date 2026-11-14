# B5 Research frontend

A responsive research workspace with an editorial landing page, an original animated DNA-inspired canvas illustration, and an ivory / deep plum / coral palette. The visual reference is [Isomorphic Labs](https://www.isomorphiclabs.com/); the implementation, assets, copy, and branding are original to this project. The helix is decorative, not a model prediction.

## Run locally

Requires Node 20.9+ and the repo's Python `.venv` with `requirements.txt` installed.

```bash
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:3000. `predev` exports the current saved research data through the backend's validated store into the ignored `public/research-data.json`. This does not call external services or rerun the research pipeline. The page identifies its source as **Repository snapshot**. Run `npm run snapshot` after pipeline changes, then reload the page.

## What works

- Shared biomarker profile, with all biomarker names and statuses read from data.
- Trial matching: backend tiers and dataset order, search by title/ID/drug/related gene, tier filter, expandable criteria, drugs and targets, unchecked criteria, supporting papers, registry links, and status dates.
- Gene explorer: searchable literature-derived candidates, model readouts, reference coordinates, linked papers, and mock provenance. Candidate genes are not presented as predicted related genes.
- Paper library: title/ID/gene search, reviewed-only filtering, source links, and visible unreviewed / opposite-status labels.
- Keyboard-operable tabs, responsive navigation, reduced-motion support, loading, no-results, failure, and retry states.
- Research disclaimer and mock provenance. No blended scores or ranking numbers.

**Pending backend work:** gene-association output, locus and similar-profile result groups, Atlas mapping, and FASTA upload. These are visibly marked as pending. There is no pretend upload or run-analysis button.

## Connect to FastAPI

Create `frontend/.env.local` (ignored):

```text
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000
```

Start `.venv/bin/uvicorn backend.app.main:app` from the repo root and restart the frontend. It uses `/api/profile`, `/api/trial-matches`, `/api/papers`, `/api/genes`, `/api/genes/{gene}`, `/api/meta`, and `/api/health`. Independent endpoint failures show notices while available result sets remain usable. API mode does not silently substitute saved data. Remove the variable to return to snapshot mode.

## Verify

```bash
npm run build
npm run typecheck
```

Production build also exports a fresh snapshot. `npm start` serves the completed build. Browser smoke verification covers trial expansion/search/tier filters, gene details, paper review filters, keyboard tabs, mobile navigation, 320/390/768px overflow, and data failure/retry.

## Files

- `app/page.tsx`: landing page and interactive workspace.
- `app/globals.css`: responsive styles and motion preferences.
- `components/helix.tsx`: procedural canvas art; animation pauses offscreen and respects reduced motion.
- `lib/types.ts`, `lib/api.ts`: v2 API types and data-loading helpers.
- `scripts/export_preview.py`: validated preview export; no research contract is changed.
- `public/fonts/`: self-hosted Manrope, licensed under SIL OFL (included).

No deployment or external hosting is configured. Research prototype. Not medical advice.
