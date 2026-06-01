"""MKT-4C: short product/audience label derivation in the normalizer.

Real intake data often has a long `product_or_service` and an
`audience_description` of several paragraphs. The downstream creative
factories cap titles at 200 / 300 chars, so the normalizer must derive
a short, human-friendly label and keep the prose available in
``description``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.intake import ClientIntake, IntakeValidator, normalize_intake
from core.intake.normalizer import _SHORT_NAME_MAX, _short_product_name

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"
REAL_INTAKE = REPO_ROOT / "examples" / "intake" / "marketing-agency-os.json"


# ---------- _short_product_name unit tests ----------

@pytest.mark.parametrize(
    "prose,expected",
    [
        ("Acme Pro — suite de automatización", "Acme Pro"),
        ("Acme Pro: la suite", "Acme Pro"),
        ("Acme Pro (la suite)", "Acme Pro"),
        ("Acme Pro | suite", "Acme Pro"),
        ("Acme Pro - suite", "Acme Pro"),
        ("Acme Pro – suite", "Acme Pro"),
        ("Acme", "Acme"),
        ("", ""),
    ],
)
def test_splits_on_natural_separator(prose: str, expected: str) -> None:
    assert _short_product_name(prose) == expected


def test_long_string_without_separator_hard_truncates_with_ellipsis() -> None:
    long = "Pipeline determinístico, auditable y multi-tenant que genera estrategia, copies, emails."
    out = _short_product_name(long)
    assert len(out) <= _SHORT_NAME_MAX + 3  # "..."
    assert out.endswith("...")


def test_separator_far_into_string_is_ignored() -> None:
    # Separator beyond _SHORT_NAME_MAX → ignore, hard-truncate instead.
    text = "x" * 100 + " — tail"
    out = _short_product_name(text)
    assert "tail" not in out
    assert out.endswith("...")


def test_short_text_passes_through_unchanged() -> None:
    assert _short_product_name("MARKETING-AGENCY-OS") == "MARKETING-AGENCY-OS"


# ---------- normalizer integration ----------

def _intake(path: Path) -> ClientIntake:
    return ClientIntake.model_validate(json.loads(path.read_text(encoding="utf-8")))


def test_demo_intake_keeps_clean_product_name() -> None:
    intake = _intake(DEMO_INTAKE)
    validation = IntakeValidator().validate(intake)
    brief = normalize_intake(intake, validation)
    assert brief.product.name == "Acme Pro"
    # When the product_or_service was shortened, BOTH the original full
    # prose and additional_context are preserved in description so prompts
    # can use either.
    assert brief.product.description is not None
    assert intake.product_or_service in brief.product.description
    assert (intake.additional_context or "") in brief.product.description


def test_real_intake_falls_back_to_client_name_when_no_separator() -> None:
    intake = _intake(REAL_INTAKE)
    validation = IntakeValidator().validate(intake)
    brief = normalize_intake(intake, validation)
    # The product_or_service is a long descriptive sentence with no separator
    # in the first 80 chars. The normalizer should fall back to client_name.
    assert brief.product.name == "MARKETING-AGENCY-OS"
    # Full prose preserved in description.
    assert brief.product.description is not None
    assert "Pipeline determinístico" in brief.product.description


def test_real_intake_audience_label_within_cap() -> None:
    intake = _intake(REAL_INTAKE)
    validation = IntakeValidator().validate(intake)
    brief = normalize_intake(intake, validation)
    # The full audience_description is ~340 chars. The label must be capped.
    assert len(brief.audience_hints[0].label) <= _SHORT_NAME_MAX + 3
    # And the full prose stays in description.
    assert brief.audience_hints[0].description == intake.audience_description
