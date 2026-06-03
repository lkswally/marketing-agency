"""N8nPayloadPlanner tests — end-to-end against the full pipeline."""

from __future__ import annotations

import json
from pathlib import Path

from core.execution import TaskFactory
from core.memory import JsonFileMemory
from core.n8n_sync import (
    N8N_EXECUTION_PAYLOAD_KIND,
    SINGLETON_ID,
    N8nActionStatus,
    N8nActionType,
    N8nPayloadPlanner,
)
from core.notion_sync import (
    NotionSyncExecutor,
    NotionSyncPlanner,
    ScriptedNotionWriter,
    SyncMode,
)
from core.pipeline import PipelineOrchestrator

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_INTAKE = REPO_ROOT / "examples" / "intake" / "demo-business.json"


def _run_full_chain(tmp_path: Path, *, risky: bool = False, with_notion: bool = True):
    """Run intake → strategy → approval → creative → visual →
    summary → tasks → notion-plan → (optional) notion-sync, so the
    n8n planner has every upstream artifact to work with."""
    data = json.loads(DEMO_INTAKE.read_text(encoding="utf-8"))
    if risky:
        data["product_or_service"] = (
            "Demo Pro - te aseguramos resultados garantizados sin riesgo"
        )
    intake_path = tmp_path / "intake.json"
    intake_path.write_text(json.dumps(data), encoding="utf-8")
    mem = JsonFileMemory(tmp_path / "mem")
    orch = PipelineOrchestrator(memory=mem, outputs_root=tmp_path / "out")
    summary = orch.run_from_file(intake_path)

    # Build the execution task pack (orchestrator doesn't auto-run it).
    from core.approval import APPROVAL_PACK_KIND, ApprovalPack
    from core.approval import SINGLETON_ID as APPROVAL_SINGLETON
    from core.creative import CREATIVE_PACK_KIND, CreativeAssetPack
    from core.creative import SINGLETON_ID as CREATIVE_SINGLETON
    from core.strategy import REPORT_KIND, CampaignStrategyReport
    from core.strategy import SINGLETON_ID as STRATEGY_SINGLETON
    from core.visual import SINGLETON_ID as VISUAL_SINGLETON
    from core.visual import VISUAL_PACK_KIND, VisualDirectionPack

    report = CampaignStrategyReport.model_validate(
        mem.get(summary.client_slug, REPORT_KIND, STRATEGY_SINGLETON)
    )
    approval = ApprovalPack.model_validate(
        mem.get(summary.client_slug, APPROVAL_PACK_KIND, APPROVAL_SINGLETON)
    )
    creative = CreativeAssetPack.model_validate(
        mem.get(summary.client_slug, CREATIVE_PACK_KIND, CREATIVE_SINGLETON)
    )
    visual = VisualDirectionPack.model_validate(
        mem.get(summary.client_slug, VISUAL_PACK_KIND, VISUAL_SINGLETON)
    )
    tf = TaskFactory(memory=mem)
    pack = tf.build(report, approval, creative, visual)
    tf.persist(pack)
    plan = NotionSyncPlanner(memory=mem).plan(pack)
    NotionSyncPlanner(memory=mem).persist(plan)

    if with_notion:
        writer = ScriptedNotionWriter()
        executor = NotionSyncExecutor(memory=mem, writer=writer, database_id="db1")
        sync_report = executor.run(
            summary.client_slug, mode=SyncMode.WRITE, confirmed=True
        )
        executor.persist_report(sync_report)

    return mem, summary, creative, visual


# ---------- happy path ----------

def test_plan_emits_all_action_types(tmp_path: Path) -> None:
    mem, summary, _, _ = _run_full_chain(tmp_path)
    payload = N8nPayloadPlanner(memory=mem).plan(summary.client_slug)
    by_type = payload.stats.by_type
    # Six types expected; some (drive_asset_folder) may be 0 if the
    # visual pack has no directions, so we assert the most-likely
    # ones explicitly.
    assert by_type.get("campaign_report_notification", 0) >= 1
    assert by_type.get("telegram_notification", 0) >= 1
    assert by_type.get("email_draft", 0) >= 1
    assert by_type.get("social_post_draft", 0) >= 1


def test_plan_links_to_source_artifacts(tmp_path: Path) -> None:
    mem, summary, creative, visual = _run_full_chain(tmp_path)
    payload = N8nPayloadPlanner(memory=mem).plan(summary.client_slug)
    assert payload.client_slug == summary.client_slug
    assert payload.run_summary_id == summary.run_id
    assert payload.creative_pack_id == creative.pack_id
    assert payload.visual_pack_id == visual.pack_id


def test_email_drafts_include_subject_and_body(tmp_path: Path) -> None:
    mem, summary, creative, _ = _run_full_chain(tmp_path)
    payload = N8nPayloadPlanner(memory=mem).plan(summary.client_slug)
    emails = payload.actions_of_type(N8nActionType.EMAIL_DRAFT)
    assert emails
    for a in emails:
        assert "subject" in a.payload
        assert "body" in a.payload
        assert a.payload.get("draft_only") is True
        assert a.target_webhook == "email_drafts"


def test_social_drafts_include_channel(tmp_path: Path) -> None:
    mem, summary, _, _ = _run_full_chain(tmp_path)
    payload = N8nPayloadPlanner(memory=mem).plan(summary.client_slug)
    posts = payload.actions_of_type(N8nActionType.SOCIAL_POST_DRAFT)
    assert posts
    for a in posts:
        assert "channel" in a.payload
        assert "hook" in a.payload
        assert a.payload.get("draft_only") is True
        assert a.target_webhook == "social_drafts"


def test_telegram_notification_says_pipeline_complete(tmp_path: Path) -> None:
    mem, summary, _, _ = _run_full_chain(tmp_path)
    payload = N8nPayloadPlanner(memory=mem).plan(summary.client_slug)
    tg = payload.actions_of_type(N8nActionType.TELEGRAM_NOTIFICATION)
    assert len(tg) == 1
    assert "✅" in tg[0].payload["text"]
    assert tg[0].payload["blocks_publish"] is False


def test_campaign_report_carries_stats(tmp_path: Path) -> None:
    mem, summary, _, _ = _run_full_chain(tmp_path)
    payload = N8nPayloadPlanner(memory=mem).plan(summary.client_slug)
    rep = payload.actions_of_type(N8nActionType.CAMPAIGN_REPORT_NOTIFICATION)
    assert len(rep) == 1
    p = rep[0].payload
    assert p["run_id"] == summary.run_id
    assert "stage_counts" in p


def test_notion_status_updates_per_created_record(tmp_path: Path) -> None:
    mem, summary, _, _ = _run_full_chain(tmp_path, with_notion=True)
    payload = N8nPayloadPlanner(memory=mem).plan(summary.client_slug)
    updates = payload.actions_of_type(N8nActionType.NOTION_STATUS_UPDATE)
    assert updates
    for a in updates:
        assert a.payload.get("advance_status") is False  # NEVER advance
        assert a.payload.get("page_id")


# ---------- blocking ----------

def test_risky_pack_blocks_email_and_social_drafts(tmp_path: Path) -> None:
    mem, summary, _, _ = _run_full_chain(tmp_path, risky=True, with_notion=False)
    payload = N8nPayloadPlanner(memory=mem).plan(summary.client_slug)
    assert payload.blocks_publish is True
    for kind in (N8nActionType.EMAIL_DRAFT, N8nActionType.SOCIAL_POST_DRAFT):
        items = payload.actions_of_type(kind)
        assert items
        assert all(i.status is N8nActionStatus.BLOCKED for i in items)
        for i in items:
            assert i.blocked_reason


def test_notifications_remain_planned_when_blocked(tmp_path: Path) -> None:
    mem, summary, _, _ = _run_full_chain(tmp_path, risky=True, with_notion=False)
    payload = N8nPayloadPlanner(memory=mem).plan(summary.client_slug)
    tg = payload.actions_of_type(N8nActionType.TELEGRAM_NOTIFICATION)
    assert tg
    # The telegram alert is still PLANNED (the team must know).
    assert tg[0].status is N8nActionStatus.PLANNED
    assert "🛑" in tg[0].payload["text"]
    rep = payload.actions_of_type(N8nActionType.CAMPAIGN_REPORT_NOTIFICATION)
    assert all(a.status is N8nActionStatus.PLANNED for a in rep)


def test_drive_folder_still_planned_when_blocked(tmp_path: Path) -> None:
    mem, summary, _, _ = _run_full_chain(tmp_path, risky=True, with_notion=False)
    payload = N8nPayloadPlanner(memory=mem).plan(summary.client_slug)
    folders = payload.actions_of_type(N8nActionType.DRIVE_ASSET_FOLDER)
    if folders:  # depends on whether the visual pack has directions
        assert all(a.status is N8nActionStatus.PLANNED for a in folders)


# ---------- partial inputs ----------

def test_missing_creative_pack_skips_email_actions(tmp_path: Path) -> None:
    """If the creative pack is missing, the planner emits zero email
    + social actions but still emits campaign + telegram notifications."""
    mem = JsonFileMemory(tmp_path / "mem")
    # Build only the run summary by hand (minimal upstream).
    from core.creative.models import CreativeAssetState
    from core.pipeline import (
        PIPELINE_RUN_KIND,
        PIPELINE_RUN_SINGLETON,
        CampaignRunSummary,
        StageId,
        StageOutcome,
        StageResult,
    )
    now = __import__("datetime").datetime.now(__import__("datetime").UTC)
    summary = CampaignRunSummary(
        client_slug="acme-saas",
        started_at=now,
        finished_at=now,
        overall_state=CreativeAssetState.DRAFT,
        blocks_publish=False,
        intake_critical_count=0,
        intake_warning_count=0,
        intake_info_count=0,
        stages=[
            StageResult(
                stage_id=StageId.INTAKE,
                outcome=StageOutcome.SUCCEEDED,
                started_at=now,
                finished_at=now,
            )
        ],
    )
    mem.put(
        "acme-saas", PIPELINE_RUN_KIND, PIPELINE_RUN_SINGLETON,
        summary.model_dump(mode="json"),
    )
    payload = N8nPayloadPlanner(memory=mem).plan("acme-saas")
    assert payload.stats.by_type.get("email_draft", 0) == 0
    assert payload.stats.by_type.get("social_post_draft", 0) == 0
    assert payload.stats.by_type.get("campaign_report_notification", 0) == 1
    assert payload.stats.by_type.get("telegram_notification", 0) == 1


def test_missing_every_artifact_emits_empty_payload(tmp_path: Path) -> None:
    """If nothing is persisted, the planner returns a clean empty
    payload (0 actions) without crashing."""
    mem = JsonFileMemory(tmp_path / "mem")
    payload = N8nPayloadPlanner(memory=mem).plan("acme-saas")
    assert payload.stats.total_actions == 0


# ---------- persistence + audit ----------

def test_persist_writes_to_memory(tmp_path: Path) -> None:
    mem, summary, _, _ = _run_full_chain(tmp_path)
    planner = N8nPayloadPlanner(memory=mem)
    payload = planner.plan(summary.client_slug)
    planner.persist(payload)
    assert mem.exists(summary.client_slug, N8N_EXECUTION_PAYLOAD_KIND, SINGLETON_ID)
    loaded = planner.load_latest(summary.client_slug)
    assert loaded.payload_id == payload.payload_id


def test_persist_emits_audit_event(tmp_path: Path) -> None:
    mem, summary, _, _ = _run_full_chain(tmp_path)
    planner = N8nPayloadPlanner(memory=mem)
    planner.persist(planner.plan(summary.client_slug))
    events = mem.read_audit_events(summary.client_slug)
    actions = [
        e.payload.get("n8n_execution_payload", {}).get("action")
        for e in events
        if "n8n_execution_payload" in e.payload
    ]
    assert "planned" in actions
    from core.contracts import verify_chain
    assert verify_chain(events) == []


# ---------- safety ----------

def test_planner_does_not_import_requests_or_httpx() -> None:
    """Belt-and-suspenders: the planner module must not pull any
    HTTP client."""
    import inspect

    import core.n8n_sync.planner as mod
    src = inspect.getsource(mod)
    assert "import requests" not in src
    assert "import httpx" not in src
    assert "urllib.request" not in src


def test_planner_does_not_read_webhook_envs(tmp_path: Path, monkeypatch) -> None:
    """Verify the planner never reads any obvious n8n env var name."""
    import inspect

    import core.n8n_sync.planner as mod
    src = inspect.getsource(mod)
    for forbidden in ("N8N_WEBHOOK", "N8N_TELEGRAM", "N8N_EMAIL", "os.environ"):
        assert forbidden not in src


def test_payload_models_have_no_url_or_secret_fields() -> None:
    """The payload + action models must not declare any field
    whose name could leak a URL or credential."""
    from core.n8n_sync import N8nAction, N8nExecutionPayload
    for cls in (N8nAction, N8nExecutionPayload):
        fields = set(cls.model_fields.keys())
        for forbidden in ("url", "webhook_url", "secret", "token", "api_key"):
            assert forbidden not in fields, (
                f"{cls.__name__}.{forbidden} would be a leak vector"
            )
