"""Lane B sanity checks: does the Genomic Intelligence signal behave like biology?

Run:  .venv/bin/python lanes/B-genomic/sanity_check.py

Writes lanes/B-genomic/sanity_check.json. Uses about 25 GI calls on the shared
demo key (or GI_API_KEY). These are checks for the demo narrative, not a
validation of the method:

1. Tissue control   - a liver gene (ALB) should score far higher in the
                      reference context than in the breast target context;
                      a housekeeping gene (GAPDH) should be high in both.
2. Determinism      - the same request twice returns the same number.
3. Strand check     - for minus-strand candidates, the gene-sense TSS window
                      should usually look more promoter-like than its
                      reverse complement (guards the strand handling in stage 3).
4. Amplicon         - from data/cache/amplicon_context.json: does the GI gene
                      finder put TSSs where Ensembl has the 17q12 genes?
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend import config  # noqa: E402
from backend.clients.ensembl import lookup_genes  # noqa: E402
from backend.clients.genomic_intelligence import GIClient  # noqa: E402
from backend.pipeline.biomarker import load_biomarker  # noqa: E402
from backend.pipeline.genomic import _digest_promoter, resolve_models, tss_window  # noqa: E402
from backend.store import read_json, write_json  # noqa: E402

CONTROL_GENES = ["ALB", "GAPDH", "HBB", "ERBB2", "ESR1"]
STRAND_GENES = ["STAT3", "HSP90AA1", "PGAP3", "SHC1", "EZR", "JUN"]
OUT = Path(__file__).with_name("sanity_check.json")


def main() -> None:
    ctx = load_biomarker().model_context
    contexts = [ctx.expression_target, ctx.expression_reference]
    report: dict = {"contexts": contexts}
    with GIClient() as gi:
        models = resolve_models(gi)
        report["models"] = models

        # 1 + 2: tissue control and determinism
        tissue = {}
        for gene in CONTROL_GENES:
            ref = gi.fetch_gene_for_expression(gene)["data"]["ref"]
            tissue[gene] = {
                c: gi.predict_expression(ref, c, models["expression"])["data"]["prediction"]["expression_log_tpm"]
                for c in contexts
            }
            if gene == "ERBB2":
                again = gi.predict_expression(ref, contexts[0], models["expression"])["data"]["prediction"]
                report["determinism"] = {
                    "gene": gene, "context": contexts[0],
                    "first": tissue[gene][contexts[0]], "second": again["expression_log_tpm"],
                    "identical": again["expression_log_tpm"] == tissue[gene][contexts[0]],
                }
            print(f"tissue  {gene:6s} " + "  ".join(f"{c!r}={v:.3f}" for c, v in tissue[gene].items()))
        report["tissue_control"] = tissue

        # 3: strand check on minus-strand genes
        ens = lookup_genes(STRAND_GENES)
        strand = {}
        for gene in STRAND_GENES:
            e = ens.get(gene)
            if e is None or e.strand != -1:
                continue
            region, s = tss_window(e.chrom, e.tss, e.strand, config.GI_TSS_HALF_WINDOW_BP)
            sense = _digest_promoter(gi.predict_promoter(gi.fetch_region(region, s)["data"]["ref"], models["promoter"]),
                                     config.GI_TSS_HALF_WINDOW_BP)
            anti = _digest_promoter(gi.predict_promoter(gi.fetch_region(region, -s)["data"]["ref"], models["promoter"]),
                                    config.GI_TSS_HALF_WINDOW_BP)
            strand[gene] = {"gene_sense_max": sense["max_probability"], "antisense_max": anti["max_probability"]}
            print(f"strand  {gene:9s} gene-sense={sense['max_probability']}  antisense={anti['max_probability']}")
        report["strand_check"] = strand
        report["strand_check_gene_sense_wins"] = sum(v["gene_sense_max"] >= v["antisense_max"] for v in strand.values())

    # 4: amplicon rediscovery (from the cached stage 3 extra, no extra calls)
    if config.AMPLICON_CONTEXT_PATH.exists():
        amp = read_json(config.AMPLICON_CONTEXT_PATH)
        report["amplicon"] = [
            {k: g.get(k) for k in ("gene_name", "strand", "tss_genomic", "nearest_known_gene", "distance_to_known_tss_bp", "expression")}
            for g in amp["genes"]
        ]
    write_json(OUT, report)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
