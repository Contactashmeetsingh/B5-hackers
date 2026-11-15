"""Prepare the fixed Plan B demo from a specific main commit. No service calls.
Run manually after fetching main; the resulting JSON is committed and used directly.
"""
import csv
import io
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REF = subprocess.check_output(['git', 'rev-parse', 'origin/main'], cwd=ROOT, text=True).strip()
BASE = f'https://github.com/Contactashmeetsingh/B5-hackers/blob/{REF}/'

def source(path):
    return subprocess.check_output(['git', 'show', f'{REF}:{path}'], cwd=ROOT, text=True)

trial_path = 'clinical_trials/trial_ops.csv'
genomic_path = 'genomic_intelligence/her2_genes_dna_context_ranking.csv'
rows = list(csv.DictReader(io.StringIO(source(trial_path))))
genomic = list(csv.DictReader(io.StringIO(source(genomic_path))))
positive = re.compile(r'her[- ]?2(?:/neu)?[ -]*(?:positive|\+)', re.I)
negative = re.compile(r'her[- ]?2[ -]*(?:negative|low|ultralow|ultra-low)|her[- ]?2\s*-(?![a-z])|triple[- ]negative', re.I)

def trial(row):
    text = row['title'] + ' ' + row['therapeutic_area']
    pos, neg = bool(positive.search(text)), bool(negative.search(text))
    return {
        **row,
        'markers': [s.strip() for s in row['biomarker_requirements'].split(';') if s.strip()],
        'her2_context': 'mixed' if pos and neg else 'positive' if pos else 'negative' if neg else 'unspecified',
        'locations': int(row['n_locations']),
        'phase_label': row['phase'].replace('PHASE', 'Phase ').replace(';', ' /').replace('NA', 'Not specified'),
        'status_label': row['recruitment_status'].replace('_', ' ').capitalize(),
    }

trials = [trial(row) for row in rows]
baseline = [row for row in trials if row['her2_context'] in ('positive', 'mixed')]
both = [row for row in trials if {'HER2', 'PIK3CA'}.issubset(row['markers'])]
# A combined marker tag is insufficient: feature only titles explicitly naming both statuses.
matched = [row for row in both if positive.search(row['title']) and re.search(r'PIK3CA[- ]mutat', row['title'], re.I) and row['her2_context'] == 'positive']
review = [row for row in both if row not in matched and row['her2_context'] != 'negative']
excluded = [row for row in both if row['her2_context'] == 'negative']

papers = []
for line in source('keenable/her2_interactors_experimental.md').splitlines():
    if not line.startswith('| `PIK3CA`'): continue
    cells = [s.strip() for s in line.strip('|').split('|')]
    match = re.search(r'\[(\d+)\]\(([^)]+)\)', cells[4])
    papers.append({'id': match[1], 'url': match[2], 'title': cells[6], 'year': cells[5], 'kind': cells[1], 'context': cells[3], 'summary': cells[2], 'primary': True})
for line in source('keenable/her2_interactors_literature.md').splitlines():
    if not line.startswith('| [') or '`PIK3CA`' not in line: continue
    cells = [s.strip() for s in line.strip('|').split('|')]
    match = re.search(r'\[(\d+)\]\(([^)]+)\)', cells[0])
    if any(p['id'] == match[1] for p in papers): continue
    papers.append({'id': match[1], 'url': match[2], 'title': cells[5], 'year': cells[1], 'kind': 'Commentary' if 'commentary' in cells[4] else 'Review' if 'review' in cells[4] else 'Pathway study', 'context': cells[4], 'summary': cells[3], 'primary': False})

payload = {
    'source_commit': REF, 'source_date': '2026-11-14',
    'profile': {'tissue': 'Breast', 'biomarker': 'HER2', 'status': 'positive', 'gene': 'ERBB2', 'mutation': 'PIK3CA'},
    'counts': {'screened': len(trials), 'her2_tagged': sum('HER2' in r['markers'] for r in trials), 'baseline': len(baseline), 'both_tagged': len(both), 'matched': len(matched), 'review': len(review), 'excluded': len(excluded)},
    'baseline': baseline, 'personalized': matched, 'review': review, 'excluded': excluded,
    'papers': papers,
    'genomic': {r['gene']: r for r in genomic if r['gene'] in ('PIK3CA', 'ERBB2')},
    'sources': {'trials': BASE + trial_path, 'experimental': BASE + 'keenable/her2_interactors_experimental.md', 'literature': BASE + 'keenable/her2_interactors_literature.md', 'genomic': BASE + genomic_path, 'genomic_notes': BASE + 'genomic_intelligence/her2_genes_dna_context_ranking.md'},
}
assert len({r['nct_id'] for r in trials}) == len(trials), 'Duplicate trial IDs'
assert matched and papers and 'PIK3CA' in payload['genomic']
assert not any(r['nct_id'] in {e['nct_id'] for e in excluded} for r in matched)
(ROOT / 'frontend/data/plan-b.json').write_text(json.dumps(payload, indent=2) + '\n')
print(json.dumps({'source': REF[:7], **payload['counts']}, indent=2))
