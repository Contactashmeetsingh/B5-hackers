> **Parked (2026-11-14):** the proof-of-concept phase does not build this page. This folder keeps the spec, types and fetch helpers in case we come back to it.

# frontend (lane D, stage 7 UI)

The dashboard: one page that shows the biomarker and the ranked trials, with the evidence behind each rank. Spec: AGENTS.md section 8. Lane notes: [`lanes/D-dashboard/README.md`](../lanes/D-dashboard/README.md).

The Next.js app is **not scaffolded yet**. So far this folder holds only what the app will import:

| File | What it is |
|---|---|
| `lib/types.ts` | TypeScript mirror of `backend/schemas.py` plus the API-only views (`GeneDetail`, `Meta`, `Health`) |
| `lib/api.ts` | Typed fetch helpers, one per endpoint. Base URL from `NEXT_PUBLIC_API_BASE` (default `http://localhost:8000`) |

## Scaffold (lane D owner, once)

`create-next-app` refuses a folder that already has files in it, so move these files aside first. Run from the repo root:

```bash
mv frontend frontend-seed
npx create-next-app@latest frontend --ts --tailwind --eslint --app --no-src-dir --import-alias "@/*" --use-npm
mkdir -p frontend/lib && cp frontend-seed/lib/*.ts frontend/lib/
cp frontend-seed/README.md frontend/README.md   # keep this file instead of the generated one
rm -rf frontend-seed

cd frontend
npx shadcn@latest init                          # pick a neutral base color
npx shadcn@latest add card badge progress collapsible separator skeleton alert
echo "NEXT_PUBLIC_API_BASE=http://localhost:8000" > .env.local
npm run dev                                     # http://localhost:3000
```

Accept the defaults for any other prompt. These commands have not been run in this repo yet. If a flag has changed, check `npx create-next-app@latest --help`. The root `.gitignore` already ignores `node_modules/`, `.next/` and `.env.local`.

The API must be running for the page to show anything: `uvicorn backend.app.main:app --reload` from the repo root (CORS allows `http://localhost:3000`).

## The page

One route, `app/page.tsx`. Suggested split:

```
app/page.tsx                  server component: getBiomarker(), getRankings(), getMeta()
components/biomarker-card.tsx header card
components/trial-row.tsx      client component: one ranked row, expands on click
components/evidence-drawer.tsx client component: getGene(g) for each matched gene, on first expand
components/mock-tag.tsx       the "mock data" badge
```

### 1. Header: biomarker card

From `GET /api/biomarker`: tissue, biomarker, gene, measurement (Breast · HER2 · ERBB2 · IHC ± ISH), plus coverage. Never hard-code "HER2" or "ERBB2" anywhere in the UI. Read them from this record.

If `meta.has_mock_data` is true, show a banner under the header: "Some inputs are mock data: <meta.mock_inputs>".

### 2. Ranked trial list

From `GET /api/rankings` (already sorted by `rank`). One card row per trial:

- **rank**, **title**, **phase**, **status**
- **score bar**: `trial_score` in [0, 1] as a bar (shadcn `Progress`, value `trial_score * 100`) with the number beside it
- **matched gene chips**: one `Badge` per `matched_genes[].gene`. Style the biomarker's own gene (`biomarker.gene`) differently, because it is left out of `genomic_match` on purpose (AGENTS.md section 5)
- **link** to `url` (opens ClinicalTrials.gov in a new tab), but only when `url` is non-empty. Mock trials from stage 5 have `url: ""`, and `<a href="">` would reopen the dashboard itself, so for those show `nct_id` as plain text next to the mock tag. `trialHref(row)` in `lib/api.ts` returns the URL or `null`
- **mock tag** when `isMockRanking(row)`, i.e. `source === "mock"` or `mock_inputs` is non-empty. Mock trial IDs look like `MOCK-NCT-0001`; show them as they are

### 3. Evidence drawer (row click)

Expands under the row (shadcn `Collapsible`). Contents:

1. **Why this score.** One line each, with weights taken from `meta.weights` (never typed into the UI):
   `trial_score = W_DIRECT × biomarker_directness + W_GENOMIC × genomic_match`, showing both inputs.
2. **Per matched gene**, from `GET /api/genes/{gene}` (`GeneDetail`):
   - literature, model and combined scores (`score.literature_score`, `score.model_score`, `score.combined_score`) as three small bars
   - **Genomic Intelligence components** from `genomic_context.model_output`, plus `region`, `assembly` and `model_task`. Lane B owns the shape of `model_output` and documents it in [`lanes/B-genomic/README.md`](../lanes/B-genomic/README.md). The scaffold-time shape is typed loosely as `GenomicModelOutput` in `lib/types.ts`. Show `summary` as one line, and `components` (expression, specificity, regulatory, each in [0, 1]) as small bars, with `raw` values in a tooltip. If those keys are absent, fall back to listing the scalar keys you find. Treat every field as optional.
   - a mock tag if `mock_inputs` is non-empty (or `genomic_context.source === "mock"`)
3. **Supporting papers** (`papers`): title linked to `url` (plain text when `url` is empty, the same rule as trial links), year, and the one-sentence `relation`. Rows only carry our own paraphrase; never show or fetch abstracts.

### 4. Footer

`meta.disclaimer` ("Research prototype. Not medical advice."). Keep the same text as a fallback constant so the footer shows even when the API is down.

### Errors and empty states

A stage that has not run yet makes its endpoint return **503**. `lib/api.ts` throws `ApiError` with `status` and `detail.run` (the command to run). Show that message in an `Alert` and do not crash the page. `GET /api/health` lists which contract files exist.

## Layout references (pattern only)

biomarkershealth.com and clintrialfinder.com: a clean ranked list, card rows, score chips. Borrow the **layout pattern only**. Do not copy their code, CSS, logos, icons, text, colors or any brand asset. Use our own wording and shadcn defaults.
