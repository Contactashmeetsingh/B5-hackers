"""Stage 0: load the input biomarker record.

Every other stage takes the biomarker from here, never from a string literal,
so adding a second biomarker row later is a data change, not a code change.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend import config
from backend.schemas import Biomarker


def load_biomarker(path: Path = config.BIOMARKER_PATH) -> Biomarker:
    return Biomarker.model_validate(json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    print(load_biomarker().model_dump_json(indent=2))
