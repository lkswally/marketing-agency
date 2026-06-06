"""MKT-9B regression test: the creative pack must not be empty.

Alpha Pilot 1 with LEXIA gave the operator the impression the
``creative_asset_pack`` was empty because the JSON has no
top-level ``assets`` field — the pack uses 5 typed lists
(``social_posts`` / ``emails`` / ``reels`` / ``flyers`` /
``image_prompts``). This test pins that ALL the typed lists are
populated end-to-end for a real intake, so a future regression
that empties them will fail loudly.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from cli.main import main

REPO_ROOT = Path(__file__).resolve().parents[2]
LEXIA_INTAKE = REPO_ROOT / "examples" / "intake" / "lexia.json"


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


def test_lexia_creative_pack_has_assets_across_all_typed_lists(
    tmp_path: Path,
) -> None:
    code, stdout = _run([
        "run-campaign",
        "--intake", str(LEXIA_INTAKE),
        "--root", str(tmp_path / "mem"),
        "--outputs-dir", str(tmp_path / "out"),
    ])
    assert code == 0, stdout

    pack_path = (
        tmp_path / "mem" / "lexia" / "creative_asset_pack" / "current.json"
    )
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    # Each typed list must have at least one entry — drafts from the
    # strategy stage must always be promoted into the pack.
    for field in ("social_posts", "emails", "reels", "flyers", "image_prompts"):
        assert pack.get(field), (
            f"creative_asset_pack.{field} is empty — drafts were not "
            "promoted from the strategy stage."
        )
    # Aggregate count must be visibly positive so the operator sees
    # SOMETHING in the portal even if they expect a single ``assets``
    # array.
    total = sum(
        len(pack.get(f, []))
        for f in ("social_posts", "emails", "reels", "flyers", "image_prompts")
    )
    assert total >= 10, (
        f"Expected >=10 creative pieces across typed lists, got {total}."
    )
