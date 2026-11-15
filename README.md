# B5 Hackers: a personalized medicine research platform (proof of concept)
Team ID: B5
Sponsor prizes: Genomic Intelligence, Keenable

Problem: 

A patient comes in with a breast cancer diagnosis, specifically with HER2 mutation. They want to be matched to clinical trials based on their genomic sequencing, which shows other biomarkers associated with HER2. This way the patient can be matched to the best possible clinical trial for them. 

Give the platform a biomarker profile, **HER2 positive + PIK3CA mutated** breast cancer, and it does two things side by side:

1. **Finds research and clinical trials.** It retrieves papers about those biomarkers and matches them to a fixed list of clinical trials, with a plain-language reason for each match.
2. **Finds related genes.** It runs the HER2 DNA sequence through a DNA model (Genomic Intelligence) and checks the predicted genes against TCGA Pan-Cancer Atlas patient data.
3. Can find alternative treatment regimens by cross-referencing existing research with genomic intelligence. 

> **Research prototype. Not medical advice.** It helps researchers explore; it does not recommend treatment. Following up on the genes it reports is the researcher's job.

## Run the app (branch `main_with_newapp`)

You need Python 3.11+ and Node.js 20.9+. Everything runs offline from the data in this repo; no API keys are needed.

```bash
git clone -b main_with_newapp https://github.com/Contactashmeetsingh/B5-hackers.git
cd B5-hackers
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd frontend && npm ci && npm run dev      # then open http://127.0.0.1:3000
```

This branch adds **PSMD3** as a HER2-associated gene: the Trial matches tab shows "Requires HER2 positive and PSMD3 amplified: 0 trials", and the Gene explorer's PSMD3 panel lists proteasome inhibitors (bortezomib, carfilzomib, ixazomib) as drug targets, with a note that they act on the proteasome rather than on PSMD3 itself.

**Where are we?** See [`HUMAN.md`](HUMAN.md), the live progress tracker. The detailed spec for coding agents is [`AGENTS.md`](AGENTS.md).

## How it works

<img width="1774" height="887" alt="image" src="https://github.com/user-attachments/assets/c6d19239-32f9-443d-9e29-85b84f0aa475" />

What each command shows today is listed in [`HUMAN.md`](HUMAN.md).

## What is in this repo

| Path | What it is |
|---|---|
| `README.md` | This page: the overview |
| `HUMAN.md` | Live progress tracker: what works, what is next, how to run it |
| `AGENTS.md` | The spec coding agents follow: file contracts, rules, services. `CLAUDE.md` points to it. |
| `data/input/` | The input profile (`profile.json`), model settings for ERBB2 (`biomarker.json`), drug → target table, clinical words for genes (`gene_terms.json`: ER → ESR1) |
| `data/cache/` | Saved stage outputs, so everything runs offline |
| `data/output/` | The two results: `trial_matches.json` (Approach 1, built) and `gene_associations.json` (Approach 2, being built) |
| `pancancer_atlas/` | TCGA Pan-Cancer Atlas table for 30 genes |
| `clinical_trials/` | Spreadsheet of 10 open HER2 trials (plus notes on excluded ones): the fixed trial list |
| `keenable/` | Literature notes found with Keenable |
| `backend/` | The pipeline (`pipeline/`), one wrapper per outside service (`clients/`), and the API (`app/`) |
| `frontend/` | Next.js visual prototype: trial matches, candidate-gene profiles, and paper library. Uses a validated local snapshot by default; optional FastAPI connection. |
| `tests/` | One offline smoke test per stage |
| `poc/`, `lanes/` | Earlier experiments and notes from the first design. Kept for reference. |

## Glossary

| Term | Meaning |
|---|---|
| Biomarker | A measurable feature of a tumor, such as HER2 status or a PIK3CA mutation |
| HER2 / ERBB2 | HER2 is the protein; ERBB2 is the gene that makes it |
| PIK3CA | A gene that is often mutated in breast cancer and is linked to resistance to anti-HER2 drugs |
| Keenable | Web search tool for AI agents, used to find the papers |
| GI | Genomic Intelligence, whose DNA models we call |
| Pan-Cancer Atlas | TCGA's dataset of tumor DNA, RNA and protein measurements from patients |
| Co-amplification | Two genes gaining extra copies together, usually because they sit side by side |
| TSS | Transcription start site, where a gene's RNA begins |
| FASTA | A plain text file format for DNA sequences |

## Ground rules

- **No invented data.** A result is real, or it is labeled `"mock"` in the file and wherever it is shown.
- **No scores.** Trials and genes are grouped and explained, not ranked by a blended number.
- **Keys go in `.env`, never in git.** None are needed to run anything here.
- **Small commits on a branch, then a pull request.**
- It is a research prototype, not medical advice.

## Frontend preview

The frontend uses an ivory, plum, and coral palette with an animated DNA-inspired illustration. Its trial, gene, and paper views use the repository data and preserve evidence and mock labels. Atlas mapping and FASTA upload remain pending.

After Python setup above, run:

```bash
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:3000. No running API is required for the saved-data preview. See [`frontend/README.md`](frontend/README.md) for API mode and production checks.
