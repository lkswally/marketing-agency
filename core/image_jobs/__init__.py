"""Image Generation Job Pack (MKT-7A).

Converts a :class:`VisualDirectionPack` into a structured set of
**image generation jobs** the agency can review before any
provider is ever invoked.

Contract: ``image-generation-job-pack.v1``.

**No image generation.** No HTTP call. No SDK import. No PIL /
Pillow usage. No file write of PNG/JPG/WebP. The block only
emits a Markdown + JSON deliverable so the operator can audit
prompts, dimensions, provider suggestions and review checklists
before any real provider integration ships.

The job state ``generated`` is reserved in the enum but the
factory NEVER emits it. A future provider-integration block
will fill it in (P-7A.6 / future MKT-7B).
"""

from __future__ import annotations

from .factory import (
    DEFAULT_IMAGE_JOB_FACTORY_RULE_SET_ID,
    ImageJobFactory,
    build_and_persist_image_jobs,
)
from .models import (
    IMAGE_GENERATION_JOB_PACK_KIND,
    IMAGE_GENERATION_JOB_PACK_VERSION,
    SINGLETON_ID,
    ImageGenerationJob,
    ImageGenerationJobPack,
    ImageJobReviewChecklistItem,
    ImageJobState,
    ImageJobStats,
    ImageProviderSuggestion,
)
from .renderer import render_markdown_image_jobs

__all__ = [
    "DEFAULT_IMAGE_JOB_FACTORY_RULE_SET_ID",
    "IMAGE_GENERATION_JOB_PACK_KIND",
    "IMAGE_GENERATION_JOB_PACK_VERSION",
    "ImageGenerationJob",
    "ImageGenerationJobPack",
    "ImageJobFactory",
    "ImageJobReviewChecklistItem",
    "ImageJobState",
    "ImageJobStats",
    "ImageProviderSuggestion",
    "SINGLETON_ID",
    "build_and_persist_image_jobs",
    "render_markdown_image_jobs",
]
