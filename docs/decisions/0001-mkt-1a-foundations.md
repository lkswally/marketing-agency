# ADR 0001 — MKT-1A: Foundations

- **Status:** Accepted
- **Date:** 2026-05-22
- **Block:** MKT-1A
- **Supersedes:** —

## Context

Initial block of MARKETING-AGENCY-OS. No runtime code yet. The goal is to commit to a small, defensible set of architectural decisions before any code is written so subsequent blocks build on stable ground.

## Decision

Adopt the 12 decisions documented in [`ARCHITECTURE.md`](../../ARCHITECTURE.md) (D1 through D12):

1. D1 — Agent runtime: Markdown specs, primary via Claude Code subagent, secondary via Python CLI wrapper.
2. D2 — Memory backend: abstract interface + `JsonFileMemory` default + `EngramMemory` opt-in.
3. D3 — Multi-tenant from day 1 (`<client-slug>` scoping everywhere).
4. D4 — Compliance is a first-class subsystem, not a skill.
5. D5 — Workflows (executable DAGs, YAML) vs Playbooks (parameterized recipes, JSON).
6. D6 — ATLAS bridge is opt-in, one-way, versioned (`bridge.v1`).
7. D7 — Folder taxonomy: `data/` (state), `outputs/` (deliverables), `assets/` (binaries).
8. D8 — Secrets in `.env` (gitignored) + per-client `.env` overrides; no third-party secret lib in MVP.
9. D9 — Minimal CI from day 1 (ruff + pytest, <60s).
10. D10 — pytest with three marker categories: default unit, `contract`, `integration` (skipped in CI).
11. D11 — Structured JSON logging via stdlib; `print()` banned in core code paths.
12. D12 — Three independent version axes: repo, contracts, agent specs.

## Alternatives considered

See per-decision "Alternatives rejected" in `ARCHITECTURE.md`.

## Consequences

- The repo can be initialized and CI can run before any agent or dispatcher code exists.
- Later blocks have an unambiguous reference for cross-cutting concerns (multi-tenant scoping, envelope shape, memory interface).
- Any deviation requires a new ADR; this file is not edited in place.

## Out of scope for MKT-1A

- Domain entity schemas (deferred to MKT-1B).
- Envelope / Phase Gate / Audit Trail concrete specs (deferred to MKT-1C).
- Memory interface implementation (deferred to MKT-1D).
- Any agent, dispatcher, skill, workflow, playbook, or integration code (deferred to MKT-2+).
