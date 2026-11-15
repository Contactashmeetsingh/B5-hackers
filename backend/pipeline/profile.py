"""Stage 0: load the input biomarker profile (HER2 + PIK3CA for the PoC).

The profile is the platform's input. Both approaches read their biomarkers from
here, never from a string literal, so adding a biomarker is a data change.
`biomarker.json` stays as the model conditioning for the profile's sequence gene.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from backend import config
from backend.schemas import Profile


def load_profile(path: Optional[Path] = None) -> Profile:
    # Look the path up at call time so tests can monkeypatch config.PROFILE_PATH.
    path = path or config.PROFILE_PATH
    return Profile.model_validate(json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    print(load_profile().model_dump_json(indent=2))
