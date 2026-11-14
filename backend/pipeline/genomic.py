"""Stage 3: genomic context and model score per candidate gene (lane B).

Reads  data/cache/gene_candidates.json  (stage 2)
Writes data/cache/genomic_context.json  (contract: AGENTS.md section 4)
Keeps  data/cache/genomic_raw/<GENE>.json  one digest of the raw model calls per gene

Every Genomic Intelligence (GI) task is run on each candidate gene, anchored on
its canonical transcription start site (TSS), and reduced to one readout:

| task        | input (gene-sense unless noted)    | readout                                              |
|-------------|------------------------------------|------------------------------------------------------|
| expression  | GI's TSS-centred 81,920 bp window  | log(TPM+1) in the target context, and specificity    |
|             |                                    | (target minus reference context)                     |
| composite   | TSS +/- 40 kb, plus strand         | expression of the transcript the gene finder places  |
|             |                                    | at the canonical TSS (find genes + expression)       |
| promoter    | TSS +/- 1 kb                       | max promoter probability                             |
| chromatin   | TSS +/- 1 kb                       | DeepSEA features called in on-tissue cell types      |
| enhancer    | TSS +/- 1 kb                       | peak dev/hk enhancer activity (Drosophila-trained)   |
| splice      | TSS .. TSS + 15 kb                 | share of canonical splice junctions recovered        |
| annotation  | TSS +/- 40 kb, plus strand         | confidence of the transcript found at the TSS (0 if  |
|             |                                    | the gene finder misses the gene)                     |

Each readout becomes a task score in [0, 1]: probabilities and fractions
(promoter, splice, annotation) are used as-is; unbounded readouts (expression,
composite, chromatin, enhancer) are min-max normalised across the candidate set.
    model_score = weighted mean of the task scores the gene has   (W_GI_TASK in config)
Higher means "the genome model sees this gene as a well-formed, active,
tissue-relevant gene at its promoter", which stage 4 blends with the literature.

Caveat for judges: the models read the reference genome, so they score a gene's
baseline regulatory potential in a context. They do not see a patient's copy
number, so they cannot "see" HER2 amplification itself.

Cache rules: each gene's digest in genomic_raw/ is reused task by task; only
tasks missing from it are sent to GI (so adding a task costs only that task).
--refresh re-queries everything; --offline never touches the network (genes
without a digest become mock rows). A gene GI cannot score becomes a row with
source "mock", model_score null and the error in model_output; no number is
ever invented.

Run alone:  python -m backend.pipeline.genomic [--refresh] [--offline] [--amplicon]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

from backend import config
from backend.clients.ensembl import EnsemblGene, genes_in_region, lookup_genes
from backend.clients.genomic_intelligence import GIClient, GIError
from backend.pipeline.biomarker import load_biomarker
from backend.schemas import MOCK, Biomarker, GeneCandidate, GenomicContext, ModelContext
from backend.store import read_json, read_rows, write_json, write_rows

SOURCE_REAL = "genomic_intelligence"
TASKS = ("expression", "composite", "promoter", "chromatin", "enhancer", "splice", "annotation")
# GI model-list task names whose default model we pin per run ("composite" uses
# the annotation and expression defaults server-side).
MODEL_TASKS = ("expression", "promoter", "chromatin", "enhancer", "splice", "annotation")


# ====================================================================== coordinates
def tss_window(chrom: str, tss: int, strand: int, half: int) -> tuple[str, int]:
    """Region string and strand for a gene-sense window with the TSS at offset `half`.

    Coordinates are 1-based inclusive (Ensembl style); `tss` is the first
    transcribed base. Plus strand: [tss-half, tss+half-1]. Minus strand: the
    reverse complement of [tss-half+1, tss+half], which puts the TSS at the
    same offset `half` in gene-sense orientation.
    """
    if strand == 1:
        return f"{chrom}:{tss - half}-{tss + half - 1}", 1
    return f"{chrom}:{tss - half + 1}-{tss + half}", -1


def downstream_window(chrom: str, tss: int, strand: int, length: int) -> tuple[str, int]:
    """Gene-sense window of `length` bp starting at the TSS (offset 0 = TSS)."""
    if strand == 1:
        return f"{chrom}:{tss}-{tss + length - 1}", 1
    return f"{chrom}:{tss - length + 1}-{tss}", -1


def splice_junctions(exons: list[list[int]], strand: int, tss: int, length: int) -> list[dict]:
    """Canonical-transcript splice junctions inside the downstream window, as offsets.

    exons are [start, end] (1-based) in transcription order. A donor is the last
    base of an exon (in transcript direction), an acceptor the first base of the
    next one. Offsets are into the gene-sense window from downstream_window().
    """
    def offset(pos: int) -> int:
        return pos - tss if strand == 1 else tss - pos

    out = []
    for i, (start, end) in enumerate(exons):
        three_prime, five_prime = (end, start) if strand == 1 else (start, end)
        if i < len(exons) - 1:
            out.append({"type": "donor", "offset": offset(three_prime)})
        if i > 0:
            out.append({"type": "acceptor", "offset": offset(five_prime)})
    return [j for j in out if 0 <= j["offset"] < length]


# ====================================================================== response digests
def _rid(env: dict) -> Optional[str]:
    return env.get("meta", {}).get("request_id")


def _digest_expression(env: dict, description: str) -> dict:
    pred = env["data"]["prediction"]
    return {
        "description": description,
        "log_tpm": round(pred["expression_log_tpm"], 4),
        "tpm": round(pred["expression_tpm"], 4),
        "scored_window": env.get("meta", {}).get("task_specific_counts", {}).get("scored_window"),
        "request_id": _rid(env),
    }


def _digest_promoter(env: dict, tss_offset: int) -> dict:
    windows = env["data"].get("window_details", [])
    probs = [w["probability"] for w in windows]
    # The core promoter sits just upstream of the TSS, i.e. at offset tss_offset - 1.
    upstream = next(
        (w["probability"] for w in windows if w["prediction_start"] <= tss_offset - 1 < w["prediction_end"]),
        None,
    )
    return {
        "max_probability": round(max(probs), 4) if probs else None,
        "upstream_window_probability": round(upstream, 4) if upstream is not None else None,
        "windows": [
            {"start": w["prediction_start"], "end": w["prediction_end"], "probability": round(w["probability"], 4)}
            for w in windows
        ],
        "request_id": _rid(env),
    }


def _digest_chromatin(env: dict, cell_types: list[str]) -> dict:
    """Shrink a DeepSEA response (~1 MB) to the evidence we score and show."""
    data = env["data"]
    on_tissue = set(cell_types)
    labels: dict[int, dict] = {}  # label_index -> best call across windows
    for w in data.get("windows", []):
        for a in w.get("annotations", []):
            best = labels.get(a["label_index"])
            if best is None or a["score"] > best["score"]:
                labels[a["label_index"]] = {
                    "cell_type": a["cell_type"], "feature_type": a["feature_type"],
                    "treatment": a.get("treatment"), "score": round(a["score"], 4),
                }
    tissue_calls = sorted(
        (dict(label_index=i, **v) for i, v in labels.items() if v["cell_type"] in on_tissue),
        key=lambda c: -c["score"],
    )
    by_feature: dict[str, int] = {}
    for c in tissue_calls:
        by_feature[c["feature_type"]] = by_feature.get(c["feature_type"], 0) + 1
    return {
        "threshold": data.get("summary", {}).get("threshold_used"),
        "windows": data.get("summary", {}).get("total_windows"),
        "labels_called_all_cell_types": len(labels),
        "on_tissue_cell_types": cell_types,
        "on_tissue_labels_called": len(tissue_calls),
        "on_tissue_by_feature": dict(sorted(by_feature.items())),
        "on_tissue_calls": tissue_calls,
        "request_id": _rid(env),
    }


def _digest_enhancer(env: dict) -> dict:
    s = env["data"].get("summary", {})
    return {
        "dev_score_max": round(s.get("dev_score_max"), 4) if s.get("dev_score_max") is not None else None,
        "hk_score_max": round(s.get("hk_score_max"), 4) if s.get("hk_score_max") is not None else None,
        "dev_score_mean": round(s.get("dev_score_mean"), 4) if s.get("dev_score_mean") is not None else None,
        "hk_score_mean": round(s.get("hk_score_mean"), 4) if s.get("hk_score_mean") is not None else None,
        "windows": s.get("total_windows"),
        "request_id": _rid(env),
    }


def _digest_splice(env: dict, junctions: list[dict], tolerance: int) -> dict:
    sites = env["data"].get("sites", [])
    hit_sites: set[int] = set()
    recovered = []
    for j in junctions:
        match = next(
            (k for k, s in enumerate(sites)
             if s["site_type"] == j["type"] and s["start"] - tolerance <= j["offset"] <= s["end"] + tolerance),
            None,
        )
        if match is not None:
            hit_sites.add(match)
            recovered.append({**j, "score": round(sites[match]["score"], 4)})
    n = len(junctions)
    return {
        "junctions_in_window": n,
        "junctions_recovered": len(recovered),
        "recall": round(len(recovered) / n, 4) if n else None,  # None: no junction in window (e.g. single exon)
        "sites_called": len(sites),
        "precision": round(len(hit_sites) / len(sites), 4) if sites else None,
        "recovered": recovered,
        "request_id": _rid(env),
    }


def _match_tss(items: list[dict], start: int, tss: int, strand: int) -> Optional[dict]:
    """The model item (transcript / prediction) whose TSS is nearest the canonical TSS,
    on the gene's strand and within GI_TSS_MATCH_TOLERANCE_BP. `start` is the 1-based
    genomic position of sequence offset 0 (plus-strand input)."""
    want = "+" if strand == 1 else "-"
    best, best_d = None, None
    for it in items:
        if it.get("strand") != want or not isinstance(it.get("tss_position"), int):
            continue
        d = start + it["tss_position"] - tss
        if abs(d) <= config.GI_TSS_MATCH_TOLERANCE_BP and (best_d is None or abs(d) < abs(best_d)):
            best, best_d = it, d
    return None if best is None else {**best, "distance_to_canonical_tss_bp": best_d}


def _digest_annotation(env: dict, start: int, tss: int, strand: int) -> dict:
    transcripts = env["data"].get("transcripts", [])
    hit = _match_tss(transcripts, start, tss, strand)
    return {
        "transcripts_found": len(transcripts),
        "found_at_tss": hit is not None,
        "confidence": round(hit["score"], 4) if hit else 0.0,  # the gene finder missed it: a real 0
        "transcript_type": hit.get("transcript_type") if hit else None,
        "transcript_type_score": round(hit["transcript_type_score"], 4) if hit and hit.get("transcript_type_score") is not None else None,
        "distance_to_canonical_tss_bp": hit["distance_to_canonical_tss_bp"] if hit else None,
        "request_id": _rid(env),
    }


def _digest_composite(env: dict, start: int, tss: int, strand: int, description: str) -> dict:
    preds = [p for p in env["data"].get("expression_predictions", []) if not p.get("skipped")]
    hit = _match_tss(preds, start, tss, strand)
    counts = env.get("meta", {}).get("task_specific_counts", {})
    return {
        "description": description,
        "genes_found": counts.get("genes_found"),
        "found_at_tss": hit is not None,
        "log_tpm": round(hit["expression"], 4) if hit else None,  # None: no transcript at the TSS
        "distance_to_canonical_tss_bp": hit["distance_to_canonical_tss_bp"] if hit else None,
        "request_id": _rid(env),
    }


# ====================================================================== model calls
def resolve_models(client: GIClient) -> dict[str, str]:
    """Pin one model id per task for the whole run (GI docs: never straddle a default change)."""
    return {task: client.list_models(task)["default_model"] for task in MODEL_TASKS}


def query_gene(
    client: GIClient,
    gene: str,
    ens: Optional[EnsemblGene],
    ctx: ModelContext,
    models: dict,
    prior: Optional[dict] = None,
) -> dict:
    """Run every GI task for one gene that `prior` (its cached digest) does not have yet.

    Returns the merged, JSON-able digest. Raises GIError if a call fails.
    """
    d: dict[str, Any] = dict(prior or {})
    d.setdefault("gene", gene)
    d["models"] = {**models, **d.get("models", {})}  # keep the ids the cached parts were made with
    m = d["models"]

    # Locus: GI resolves the canonical TSS and builds the gene-sense, TSS-centred
    # expression window server-side. Papers sometimes use an old symbol, so fall
    # back to the current HGNC symbol from Ensembl.
    handles: dict[str, str] = {}
    if "locus" not in d or "expression" not in d:
        names = [gene] + ([ens.approved_symbol] if ens and ens.approved_symbol not in ("", gene) else [])
        handle, last_err = None, None
        for name in names:
            try:
                handle = client.fetch_gene_for_expression(name)["data"]
                break
            except GIError as exc:
                last_err = exc
                if exc.code not in ("ensembl_error", "not_found", "invalid_input"):
                    raise
        if handle is None:
            raise last_err  # type: ignore[misc]
        handles["expression"] = handle["ref"]
        chrom, tss, strand = str(handle["region"]).split(":")[0], int(handle["tss"]), int(handle["strand"])
        d["queried_as"] = handle.get("gene", gene)
        d["locus"] = {
            "ensembl_id": handle.get("ensembl_id"),
            "chrom": chrom, "strand": strand, "tss": tss,
            "tss_source": handle.get("tss_source"),
            # GI's TSS should equal Ensembl's canonical-transcript TSS; record if not.
            "tss_matches_ensembl": (ens.tss == tss) if ens else None,
            "expression_window": handle.get("region"),
        }
    loc = d["locus"]
    chrom, tss, strand = loc["chrom"], int(loc["tss"]), int(loc["strand"])
    H = config.GI_TSS_HALF_WINDOW_BP

    if "expression" not in d:
        ref = handles["expression"]
        d["expression"] = {
            "target": _digest_expression(client.predict_expression(ref, ctx.expression_target, m["expression"]),
                                         ctx.expression_target),
            "reference": _digest_expression(client.predict_expression(ref, ctx.expression_reference, m["expression"]),
                                            ctx.expression_reference),
        }

    # Promoter, chromatin and enhancer share one TSS +/- 1 kb gene-sense handle.
    need_tss = [t for t in ("promoter", "chromatin", "enhancer") if t not in d]
    if need_tss:
        region, region_strand = tss_window(chrom, tss, strand, H)
        loc["tss_window"], loc["tss_window_strand"] = region, region_strand
        ref = client.fetch_region(region, region_strand)["data"]["ref"]
        if "promoter" not in d:
            d["promoter"] = _digest_promoter(client.predict_promoter(ref, m["promoter"]), H)
        if "chromatin" not in d:
            d["chromatin"] = _digest_chromatin(client.predict_chromatin(ref, m["chromatin"]), ctx.chromatin_cell_types)
        if "enhancer" not in d:
            d["enhancer"] = _digest_enhancer(client.call_tool("predict_enhancer", {"sequence_ref": ref, "model": m["enhancer"]}))

    if "splice" not in d:
        L = config.GI_SPLICE_WINDOW_BP
        region, region_strand = downstream_window(chrom, tss, strand, L)
        loc["splice_window"] = region
        junctions = splice_junctions((ens.canonical_exons or []) if ens else [], strand, tss, L)
        ref = client.fetch_region(region, region_strand)["data"]["ref"]
        env = client.call_tool("predict_splice", {"sequence_ref": ref, "model": m["splice"]})
        d["splice"] = _digest_splice(env, junctions, config.GI_SPLICE_TOLERANCE_BP)

    # Gene finder and composite share one TSS +/- 40 kb plus-strand handle.
    need_locus = [t for t in ("annotation", "composite") if t not in d]
    if need_locus:
        A = config.GI_ANNOTATION_HALF_BP
        start = tss - A  # 1-based position of sequence offset 0
        loc["annotation_window"] = f"{chrom}:{start}-{tss + A - 1}"
        ref = client.fetch_region(loc["annotation_window"], 1)["data"]["ref"]  # gene finder wants plus strand
        if "annotation" not in d:
            env = client.call_tool("find_genes", {"sequence_ref": ref, "model": m["annotation"], "wait": True})
            d["annotation"] = _digest_annotation(env, start, tss, strand)
        if "composite" not in d:
            env = client.find_genes_and_predict_expression(ref, ctx.expression_target)
            d["composite"] = _digest_composite(env, start, tss, strand, ctx.expression_target)

    d["retrieved"] = _dt.date.today().isoformat()
    d["server"] = client.server_info
    d["demo_key"] = client.uses_demo_key
    return d


# ====================================================================== scoring
def _minmax(values: dict[str, float]) -> dict[str, float]:
    """Min-max to [0, 1] over the genes that have a value. A constant vector carries no
    ranking signal, so it maps to 0.5."""
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi - lo < 1e-12:
        return {k: 0.5 for k in values}
    return {k: (v - lo) / (hi - lo) for k, v in values.items()}


def task_readouts(d: dict) -> dict[str, Optional[float]]:
    """One raw number per task (None when the task produced no readout for this gene)."""
    e = d.get("expression") or {}
    enh = d.get("enhancer") or {}
    peaks = [x for x in (enh.get("dev_score_max"), enh.get("hk_score_max")) if x is not None]
    t, r = (e.get("target") or {}).get("log_tpm"), (e.get("reference") or {}).get("log_tpm")
    return {
        "expression_level": t,
        "expression_specificity": (t - r) if t is not None and r is not None else None,
        "composite": (d.get("composite") or {}).get("log_tpm"),
        "promoter": (d.get("promoter") or {}).get("max_probability"),
        "chromatin": float(d["chromatin"]["on_tissue_labels_called"]) if d.get("chromatin") else None,
        "enhancer": max(peaks) if peaks else None,
        "splice": (d.get("splice") or {}).get("recall"),
        "annotation": (d.get("annotation") or {}).get("confidence"),
    }


def score_digests(digests: dict[str, dict]) -> dict[str, dict]:
    """Task scores in [0, 1] per gene, and model_score = their weighted mean."""
    raw = {g: task_readouts(d) for g, d in digests.items()}

    def norm(key: str) -> dict[str, float]:
        return _minmax({g: v[key] for g, v in raw.items() if v[key] is not None})

    level, spec = norm("expression_level"), norm("expression_specificity")
    composite, chromatin, enhancer = norm("composite"), norm("chromatin"), norm("enhancer")
    w_expr = config.W_EXPR_LEVEL + config.W_EXPR_SPECIFICITY
    out = {}
    for g, v in raw.items():
        tasks: dict[str, Optional[float]] = {
            "expression": (
                (config.W_EXPR_LEVEL * level[g] + config.W_EXPR_SPECIFICITY * spec[g]) / w_expr
                if g in level and g in spec else None
            ),
            "composite": composite.get(g),
            "promoter": v["promoter"],      # probability: used as-is
            "chromatin": chromatin.get(g),
            "enhancer": enhancer.get(g),
            "splice": v["splice"],          # fraction: used as-is
            "annotation": v["annotation"],  # probability: used as-is
        }
        have = {t: s for t, s in tasks.items() if s is not None and config.W_GI_TASK.get(t, 0) > 0}
        w = sum(config.W_GI_TASK[t] for t in have)
        score = sum(config.W_GI_TASK[t] * s for t, s in have.items()) / w if w else None
        out[g] = {
            "model_score": round(min(1.0, max(0.0, score)), 4) if score is not None else None,
            "task_scores": {t: (round(s, 4) if s is not None else None) for t, s in tasks.items()},
            "task_raw": {k: (round(x, 4) if x is not None else None) for k, x in v.items()},
            "tasks_used": sorted(have),
        }
    return out


# ====================================================================== stage entry point
def _raw_path(gene: str):
    return config.GI_RAW_DIR / f"{gene}.json"


def _model_task(models: dict) -> str:
    return " + ".join(f"{task} ({mid})" for task, mid in models.items()) + " + composite (annotation->expression)"


def _summary(d: dict, s: dict) -> str:
    e, r = d["expression"], s["task_raw"]
    ann = d["annotation"]
    spl = d["splice"]
    return (
        f"Expression {e['target']['log_tpm']} log(TPM+1) in '{e['target']['description']}' vs "
        f"{e['reference']['log_tpm']} in '{e['reference']['description']}'; promoter p={r['promoter']}; "
        f"{int(r['chromatin'] or 0)} breast-lineage chromatin calls; enhancer peak {r['enhancer']}; "
        f"splice junctions recovered {spl['junctions_recovered']}/{spl['junctions_in_window']}; "
        f"gene finder {'found' if ann['found_at_tss'] else 'missed'} the TSS"
        + (f" (confidence {ann['confidence']})" if ann["found_at_tss"] else "") + "."
    )


def _context_row(c: GeneCandidate, ens: Optional[EnsemblGene], d: dict, s: dict) -> GenomicContext:
    chromatin = d["chromatin"]
    return GenomicContext(
        gene=c.gene,
        assembly=config.GI_ASSEMBLY,
        region=ens.region if ens else f"chr{d['locus']['expression_window']}",
        model_task=_model_task(d["models"]),
        model_score=s["model_score"],
        source=SOURCE_REAL,
        model_output={
            "summary": _summary(d, s),
            "task_scores": s["task_scores"],
            "task_raw": s["task_raw"],
            "tasks_used": s["tasks_used"],
            "weights": {**{f"task.{t}": w for t, w in config.W_GI_TASK.items()},
                        "expression.level": config.W_EXPR_LEVEL, "expression.specificity": config.W_EXPR_SPECIFICITY},
            "locus": d["locus"],
            "expression": d["expression"],
            "composite": d["composite"],
            "promoter": {k: v for k, v in d["promoter"].items() if k != "windows"},
            "chromatin": {k: v for k, v in chromatin.items() if k != "on_tissue_calls"}
            | {"top_on_tissue_calls": chromatin["on_tissue_calls"][:10]},
            "enhancer": d["enhancer"],
            "splice": {k: v for k, v in d["splice"].items() if k != "recovered"},
            "annotation": d["annotation"],
            "models": d["models"],
            "retrieved": d["retrieved"],
            "demo_key": d["demo_key"],
        },
    )


def _mock_row(c: GeneCandidate, ens: Optional[EnsemblGene], reason: str) -> GenomicContext:
    return GenomicContext(
        gene=c.gene,
        assembly=config.GI_ASSEMBLY,
        region=ens.region if ens else "",
        model_task="not run",
        model_score=None,  # never invent a model number
        source=MOCK,
        model_output={"error": reason},
    )


def _complete(d: Optional[dict]) -> bool:
    return bool(d) and all(t in d for t in TASKS) and "locus" in d


def _query_all(genes: list[str], cached: dict[str, dict], ensembl: dict, ctx: ModelContext,
               verbose: bool) -> tuple[dict[str, dict], dict[str, str]]:
    """Query GI for `genes` with a small pool of sessions. Returns (digests, failures)."""
    digests: dict[str, dict] = {}
    failures: dict[str, str] = {}
    local = threading.local()
    clients: list[GIClient] = []
    lock = threading.Lock()

    def client() -> GIClient:
        if not hasattr(local, "c"):
            local.c = GIClient()
            with lock:
                clients.append(local.c)
        return local.c

    with GIClient() as probe:
        models = resolve_models(probe)
        if verbose:
            key = "shared demo key" if probe.uses_demo_key else "GI_API_KEY"
            print(f"[genomic] {len(genes)} genes to (re)score via GI MCP ({key}); models {models}")

    def work(g: str) -> dict:
        try:
            return query_gene(client(), g, ensembl.get(g), ctx, models, cached.get(g))
        except GIError as exc:
            if exc.code != "unknown_ref":  # handles die with their session; retry once
                raise
            return query_gene(client(), g, ensembl.get(g), ctx, models, cached.get(g))

    try:
        with ThreadPoolExecutor(max_workers=config.GI_WORKERS) as pool:
            futures = {pool.submit(work, g): g for g in genes}
            for n, fut in enumerate(as_completed(futures), 1):
                g = futures[fut]
                try:
                    d = fut.result()
                    write_json(_raw_path(g), d)  # checkpoint per gene: a crash loses one gene at most
                    digests[g] = d
                    if verbose:
                        r = task_readouts(d)
                        print(f"[genomic] {n:2d}/{len(genes)} {g:9s} " + " ".join(
                            f"{k}={'-' if v is None else round(v, 3)}" for k, v in r.items()))
                except GIError as exc:
                    failures[g] = str(exc)
                    if verbose:
                        print(f"[genomic] {n:2d}/{len(genes)} {g:9s} FAILED {exc}")
    finally:
        for c in clients:
            c.close()
    return digests, failures


def run(refresh: bool = False, offline: bool = False, verbose: bool = True) -> list[GenomicContext]:
    biomarker: Biomarker = load_biomarker()
    candidates = read_rows(config.GENE_CANDIDATES_PATH, GeneCandidate)
    genes = [c.gene for c in candidates]

    cached = {} if refresh else {g: read_json(_raw_path(g)) for g in genes if _raw_path(g).exists()}

    # Whole-file cache: reuse when it covers exactly the current candidate set and
    # every gene's digest already has every task.
    if config.GENOMIC_CONTEXT_PATH.exists() and not refresh and all(_complete(cached.get(g)) for g in genes):
        rows = read_rows(config.GENOMIC_CONTEXT_PATH, GenomicContext)
        if sorted(r.gene for r in rows) == sorted(genes) and all("task_scores" in r.model_output for r in rows if not r.is_mock):
            return rows

    ensembl = lookup_genes(genes, need_exons=True)  # cached; exons are needed for the splice readout
    digests = {g: d for g, d in cached.items() if _complete(d)}
    todo = [g for g in genes if g not in digests]
    failures: dict[str, str] = {}
    if todo and offline:
        failures = {g: "offline run and no complete cached model output" for g in todo}
    elif todo:
        fresh, failures = _query_all(todo, cached, ensembl, biomarker.model_context, verbose)
        digests.update(fresh)

    scored = score_digests({g: d for g, d in digests.items() if _complete(d)})
    rows = [
        _context_row(c, ensembl.get(c.gene), digests[c.gene], scored[c.gene]) if c.gene in scored
        else _mock_row(c, ensembl.get(c.gene), failures.get(c.gene, "not scored (incomplete model output)"))
        for c in candidates
    ]
    rows.sort(key=lambda r: (r.model_score is None, -(r.model_score or 0.0), r.gene))
    write_rows(config.GENOMIC_CONTEXT_PATH, rows)
    if verbose:
        n_mock = sum(r.is_mock for r in rows)
        print(f"[genomic] wrote {len(rows)} rows ({len(rows) - n_mock} real, {n_mock} mock) -> {config.GENOMIC_CONTEXT_PATH}")
    return rows


# ====================================================================== optional: amplicon scan
def run_amplicon(refresh: bool = False, verbose: bool = True) -> dict:
    """Genes the GI gene-finder detects around the biomarker gene, each with predicted
    expression in the target context. Context for the dashboard only; not scored.

    For HER2 this is the 17q12 amplicon neighbourhood (ERBB2, GRB7, STARD3, PGAP3, ...).
    """
    if config.AMPLICON_CONTEXT_PATH.exists() and not refresh:
        return read_json(config.AMPLICON_CONTEXT_PATH)
    biomarker = load_biomarker()
    ens = lookup_genes([biomarker.gene]).get(biomarker.gene)
    if ens is None:
        raise RuntimeError(f"Ensembl could not resolve {biomarker.gene}")
    half = config.GI_AMPLICON_HALF_WIDTH_BP
    region = f"{ens.chrom}:{ens.tss - half}-{ens.tss + half - 1}"
    with GIClient() as client:
        ref = client.fetch_region(region, 1)["data"]["ref"]  # gene finder wants plus strand
        env = client.find_genes_and_predict_expression(ref, biomarker.model_context.expression_target)
    data, meta = env.get("data", {}), env.get("meta", {})
    start = ens.tss - half  # 1-based genomic coordinate of sequence offset 0
    # GI's gene finder reports unnamed transcripts; label each with the known
    # protein-coding gene whose canonical TSS (same strand) is nearest its predicted TSS.
    known = [g for g in genes_in_region(ens.chrom, start, ens.tss + half - 1) if g["biotype"] == "protein_coding"]
    canonical = lookup_genes([g["symbol"] for g in known])  # canonical-transcript TSS beats gene-body 5' end
    for g in known:
        c = canonical.get(g["symbol"])
        g["tss"] = c.tss if c else g["five_prime"]
    genes: list[dict[str, Any]] = []
    for p in data.get("expression_predictions", []):
        row = {k: v for k, v in p.items() if not isinstance(v, (dict, list))}
        if isinstance(p.get("tss_position"), int):
            tss_g = start + p["tss_position"]  # 0-based offset -> 1-based genomic
            row["tss_genomic"] = tss_g
            same_strand = [g for g in known if (g["strand"] == 1) == (p.get("strand") == "+")]
            if same_strand:
                near = min(same_strand, key=lambda g: abs(g["tss"] - tss_g))
                row["nearest_known_gene"] = near["symbol"]
                row["distance_to_known_tss_bp"] = tss_g - near["tss"]  # vs Ensembl canonical TSS
        genes.append(row)
    out = {
        "biomarker_gene": biomarker.gene,
        "region": f"chr{region}",
        "assembly": config.GI_ASSEMBLY,
        "description": biomarker.model_context.expression_target,
        "source": SOURCE_REAL,
        "retrieved": _dt.date.today().isoformat(),
        "counts": meta.get("task_specific_counts"),
        "models": {"annotation": meta.get("annotation_model"), "expression": meta.get("expression_model") or meta.get("model")},
        "request_id": meta.get("request_id"),
        "known_protein_coding_genes_in_region": [g["symbol"] for g in sorted(known, key=lambda g: g["start"])],
        "genes": genes,
    }
    write_json(config.AMPLICON_CONTEXT_PATH, out)
    if verbose:
        print(f"[genomic] amplicon scan {out['region']}: {len(genes)} genes -> {config.AMPLICON_CONTEXT_PATH}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 3: Genomic Intelligence context + model score per gene")
    ap.add_argument("--refresh", action="store_true", help="re-query GI for every gene, ignoring caches")
    ap.add_argument("--offline", action="store_true", help="never call the network; uncached genes become mock rows")
    ap.add_argument("--amplicon", action="store_true", help="also scan the biomarker gene's amplicon region")
    args = ap.parse_args()
    rows = run(refresh=args.refresh, offline=args.offline)
    for r in rows[:10]:
        print(f"  {r.gene:9s} model_score={r.model_score}  source={r.source}")
    if args.amplicon:
        run_amplicon(refresh=args.refresh)


if __name__ == "__main__":
    main()
