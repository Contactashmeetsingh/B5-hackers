"""PoC 3: does the genomic language model (GLM) agree with the Keenable literature?

Compares, per candidate gene:
  GLM       model_score from data/cache/genomic_context.json (all 7 Genomic Intelligence tasks)
  Keenable  (a) papers in data/cache/papers.json that mention the gene (reviews included)
            (b) lab-evidence papers in keenable/her2_interactors_experimental.md
            (c) evidence tier from that file: 2 = physical binding to HER2, 1 = functional only

Writes data/output/glm_vs_keenable.json and data/output/glm_vs_keenable.md.
Offline: reads committed files only.

    .venv/bin/python poc/compare_glm_vs_keenable.py

PoC shortcuts (fine for a demo, fix before relying on it):
- (b) and (c) are parsed from the markdown table, because that set is not in a
  data file yet. If the table's layout changes, update parse_experimental().
- The biomarker gene (ERBB2) is left out: every paper mentions it.
- 29 genes is small: |rho| needs to be above about 0.37 to mean anything (p < 0.05).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import config  # noqa: E402
from backend.pipeline.biomarker import load_biomarker  # noqa: E402

EXPERIMENTAL_MD = ROOT / "keenable" / "her2_interactors_experimental.md"
OUT_JSON = config.OUTPUT_DIR / "glm_vs_keenable.json"
OUT_MD = config.OUTPUT_DIR / "glm_vs_keenable.md"
TASKS = ["expression", "composite", "promoter", "chromatin", "enhancer", "splice", "annotation"]
LIT_HIGH_MIN_PAPERS = 2  # "well supported" = at least this many lab-evidence papers


def ranks(v: list[float]) -> list[float]:
    """1-based ranks, ties get the average rank."""
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(a: list[float], b: list[float]) -> float | None:
    ra, rb = ranks(a), ranks(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va, vb = sum((x - ma) ** 2 for x in ra), sum((y - mb) ** 2 for y in rb)
    return round(cov / (va * vb) ** 0.5, 3) if va and vb else None


def parse_experimental(genes: set[str]) -> tuple[dict[str, int], set[str]]:
    """(lab-evidence paper count per gene, genes with physical-binding evidence)."""
    md = EXPERIMENTAL_MD.read_text(encoding="utf-8")
    table = md.split("## Papers")[1].split("★ =")[0]
    count = {g: 0 for g in genes}
    for line in table.splitlines():
        if line.startswith("| `"):
            for g in set(re.findall(r"`([A-Z0-9]+)`", line.split("|")[1])):
                if g in count:
                    count[g] += 1
    tiers = md.split("## Strongest evidence per gene")[1]
    physical = set(re.findall(r"`([A-Z0-9]+)`", tiers.split("**Functional only**")[0]))
    return count, physical


def main() -> None:
    bm = load_biomarker()
    ctx = {r["gene"]: r for r in json.loads(config.GENOMIC_CONTEXT_PATH.read_text())}
    papers = json.loads(config.PAPERS_PATH.read_text())
    genes = sorted(g for g, r in ctx.items() if g != bm.gene and r.get("model_score") is not None)

    all_papers = {g: sum(g in p["genes_mentioned"] for p in papers) for g in genes}
    lab, physical = parse_experimental(set(genes))
    tier = {g: 2 if g in physical else 1 if lab[g] else 0 for g in genes}
    glm = {g: ctx[g]["model_score"] for g in genes}
    median = sorted(glm.values())[len(genes) // 2]

    def quadrant(g: str) -> str:
        lit = "literature-high" if lab[g] >= LIT_HIGH_MIN_PAPERS else "literature-low"
        return f"{lit} / {'GLM-high' if glm[g] >= median else 'GLM-low'}"

    rows = [{
        "gene": g,
        "glm_score": glm[g],
        "glm_task_scores": ctx[g]["model_output"].get("task_scores"),
        "keenable_papers": all_papers[g],
        "keenable_lab_papers": lab[g],
        "keenable_evidence_tier": tier[g],
        "agreement": quadrant(g),
    } for g in genes]
    rows.sort(key=lambda r: -r["glm_score"])

    def task_rho(t: str) -> dict:
        gs = [g for g in genes if (ctx[g]["model_output"].get("task_scores") or {}).get(t) is not None]
        return {"n": len(gs), "rho": spearman([ctx[g]["model_output"]["task_scores"][t] for g in gs], [lab[g] for g in gs])}

    summary = {
        "n_genes": len(genes),
        "excluded": [bm.gene],
        "spearman_glm_vs_keenable_papers": spearman(list(glm.values()), [all_papers[g] for g in glm]),
        "spearman_glm_vs_keenable_lab_papers": spearman(list(glm.values()), [lab[g] for g in glm]),
        "spearman_glm_vs_evidence_tier": spearman(list(glm.values()), [tier[g] for g in glm]),
        "spearman_per_task_vs_lab_papers": {t: task_rho(t) for t in TASKS},
        "mean_glm_physical_binding": round(sum(glm[g] for g in genes if tier[g] == 2) / max(1, sum(tier[g] == 2 for g in genes)), 3),
        "mean_glm_functional_only": round(sum(glm[g] for g in genes if tier[g] == 1) / max(1, sum(tier[g] == 1 for g in genes)), 3),
        "significance_note": "n=29: |rho| must exceed ~0.37 for p < 0.05",
        "quadrants": {q: [r["gene"] for r in rows if r["agreement"] == q] for q in sorted({r["agreement"] for r in rows})},
    }
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({"summary": summary, "genes": rows}, indent=2) + "\n")

    s = summary
    md = [
        "# PoC 3: GLM vs Keenable",
        "",
        "Generated by `poc/compare_glm_vs_keenable.py` from committed data. Research prototype, not medical advice.",
        "",
        f"{s['n_genes']} genes ({', '.join(s['excluded'])} excluded). Spearman rank correlation of the GLM `model_score` with:",
        "",
        "| Keenable signal | rho |",
        "|---|---|",
        f"| all papers (incl. reviews) | {s['spearman_glm_vs_keenable_papers']} |",
        f"| lab-evidence papers | {s['spearman_glm_vs_keenable_lab_papers']} |",
        f"| evidence tier (physical > functional) | {s['spearman_glm_vs_evidence_tier']} |",
        "",
        f"Mean GLM score: physical-binding genes {s['mean_glm_physical_binding']}, functional-only {s['mean_glm_functional_only']}. {s['significance_note']}.",
        "",
        "**Reading:** the two signals barely agree. The GLM measures whether a gene looks active in breast tissue at the "
        "DNA level; Keenable measures how well its link to HER2 is documented. They are complementary, which is why "
        "the gene score blends them.",
        "",
        "| Agreement | Genes |",
        "|---|---|",
        *[f"| {q} | {', '.join(g)} |" for q, g in s["quadrants"].items()],
        "",
        "| Gene | GLM score | Keenable papers | lab papers | tier |",
        "|---|---|---|---|---|",
        *[f"| {r['gene']} | {r['glm_score']} | {r['keenable_papers']} | {r['keenable_lab_papers']} | {r['keenable_evidence_tier']} |" for r in rows],
        "",
    ]
    OUT_MD.write_text("\n".join(md))
    print("\n".join(md[4:12]))
    print(f"\nwrote {OUT_JSON.relative_to(ROOT)} and {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
