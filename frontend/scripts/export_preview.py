"""Export validated repository data for the offline frontend preview. No service calls."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.main import health, meta, profile
from backend import config
from backend.schemas import GeneCandidate, GenomicContext, Paper, TrialMatch
from backend.store import read_rows, write_json


def rows(path, model):
    return [row.model_dump(mode="json") for row in read_rows(path, model)] if path.exists() else []


payload = {
    "profile": profile().model_dump(mode="json"),
    "meta": meta().model_dump(mode="json"),
    "health": health(),
    "trials": sorted(rows(config.TRIAL_MATCHES_PATH, TrialMatch), key=lambda row: row["tier_rank"]),
    "papers": rows(config.PAPERS_PATH, Paper),
    "genes": rows(config.GENE_CANDIDATES_PATH, GeneCandidate),
    "contexts": rows(config.GENOMIC_CONTEXT_PATH, GenomicContext),
}
destination = ROOT / "frontend/public/research-data.json"
write_json(destination, payload)
print(f"Frontend snapshot: {len(payload['trials'])} trials, {len(payload['papers'])} papers, {len(payload['genes'])} genes.")
