# Agent Backend Safety Boundaries

> Status: **policy** (MKT-2B). Applies the moment any non-mock backend is
> implemented. Today only `MockAgentBackend` exists; `ClaudeCodeBackend` is
> scaffolding that raises `NotImplementedError`.

This document defines the **non-negotiable boundaries** that any real
`AgentBackend` implementation MUST satisfy before being merged. It exists
because spawning an LLM with tools is the exact moment a hallucination can
become a write to disk, an outbound HTTP call, or an exfiltrated secret.

---

## 1. Threat model

Real agents can:

1. **Touch the filesystem.** A hallucinated path can overwrite, delete, or
   leak data outside the client folder.
2. **Hit the network.** A tool call can leak prompts, claims, or credentials
   to arbitrary URLs.
3. **Read secrets.** Environment variables, `.env` files, or shell history
   may end up in a prompt that the LLM echoes back into an artifact.
4. **Bypass compliance.** An agent that "approves" its own claim audit
   defeats the whole MKT-3 subsystem.
5. **Loop / spawn recursively.** Without budgets, a single invocation can
   consume unbounded tokens or spawn sibling agents.

The mock backend cannot do any of this. A real backend can. The
boundaries below are what stops it.

---

## 2. Required guarantees before `ClaudeCodeBackend` ships

### 2.1 Filesystem allowlist

A real backend MUST configure the spawned agent so that filesystem writes
are restricted to:

- `data/clients/<client_slug>/` (the tenant's state).
- `outputs/<client_slug>/` (the tenant's deliverables).
- `assets/clients/<client_slug>/` (the tenant's binaries).
- The OS temp directory (for staging only, must be cleaned up).

**Disallowed by default:** the repo root, sibling client folders, any path
matching `*.env*`, `.git/`, `.engram/`, `~/.claude/`, anything outside
`D:\ProyectosIA\MARKETING-AGENCY-OS\` (or platform equivalent).

The check is enforced by the backend BEFORE the agent runs, not by trust.

### 2.2 Network allowlist

Default: **no network**. A backend that needs network (e.g. to fetch
Evidence) MUST declare the allowlist explicitly per agent_id (e.g.
`audience-researcher`: `["*.gov", "*.statista.com"]`). The allowlist is
checked at the egress point, not at the prompt level.

`mkt-orchestrator`, `copywriter`, `creative-director`, `compliance-auditor`,
`approval-manager` MUST have **empty** allowlists in v1.

### 2.3 Tool restriction

Even if Claude Code provides a rich tool surface, real MKT agents start
with a minimal allowed-tools list per agent_id. For example:

| Agent | Allowed tools |
|-------|---------------|
| `copywriter` | Read (within tenant root), Write (within tenant outputs) |
| `audience-researcher` | Read (tenant root) |
| `compliance-auditor` | Read (tenant root); NO Write — verdicts return via envelope |

`Bash`, `WebFetch`, `WebSearch` are **opt-in per agent**, never enabled by
default.

### 2.4 No secrets in the prompt

The backend MUST:

- Strip every environment variable from the spawned subprocess EXCEPT a
  documented allowlist (`PATH`, `TZ`, `LANG`).
- Refuse to load `.env` into the prompt.
- Never include `client_slug`-derived credentials in the prompt body —
  credentials live in the operator's environment, not in agent context.

### 2.5 Spawn budgets

Each invocation MUST carry:

- A token cap (input + output).
- A wall-clock timeout.
- A subagent-spawn cap (a real agent cannot recursively spawn 50 children).

Hitting any cap returns a `ReturnEnvelope` with `status=fallido` and a
blocker explaining which cap fired. The dispatcher's audit trail records
the cap event.

### 2.6 Audit-on-spawn

Every `AgentBackend.run` invocation MUST emit an audit event BEFORE the
agent starts (`agent_spawned`) and AFTER it returns (`agent_returned` or
`agent_failed`). The pre-event includes the resolved allowlists and caps;
the post-event includes wall-clock, token usage, and exit reason. The
dispatcher then emits its own `envelope_received` on top of those.

These three event types must be defined as additions to `audit-trail.v1`
when the real backend lands (additive change within the contract).

### 2.7 No compliance self-approval

A real `compliance-auditor` spawn cannot be the same process / context as
the agent whose output it is auditing. A backend implementing
`compliance-auditor` MUST verify that the asset under audit was not
produced in the same invocation.

### 2.8 Reproducibility hook

Each spawn MUST log enough metadata (model, temperature, prompt hash,
input artifact hashes) so a later audit can reconstruct what was sent.
Storing the full prompt is encouraged but optional; storing its SHA-256
hash is required.

---

## 3. Promotion checklist

Before `ClaudeCodeBackend.run` stops raising `NotImplementedError`:

- [ ] §2.1 filesystem allowlist implemented + tested with a deliberately
      crafted path traversal in the prompt.
- [ ] §2.2 network allowlist implemented + tested with an in-prompt URL
      attempt against a non-allowed domain.
- [ ] §2.3 tool restriction map declared per agent and enforced at spawn.
- [ ] §2.4 environment scrubbing implemented + tested by injecting a
      sentinel env var.
- [ ] §2.5 token / time / spawn caps implemented + tests that hit each cap.
- [ ] §2.6 three new audit event types defined; events emitted on every
      invocation; integration test asserting the trio is present.
- [ ] §2.7 compliance-auditor isolation enforced + tested.
- [ ] §2.8 prompt hash logged per invocation + integration test.
- [ ] All 16 agent specs reviewed and labeled with their allowed tools and
      network allowlist (mostly empty).
- [ ] ADR amending this document with the implementation block's number.

Until every box is checked, `ClaudeCodeBackend.run` continues to raise
`NotImplementedError`.

---

## 4. Open questions

These are unresolved as of MKT-2B and must be answered in the implementing
block:

1. **Tool restriction at Claude Code subagent spawn level.** Today there
   is no documented API to restrict the tools a sub-spawn can use. The
   block that implements `ClaudeCodeBackend` MUST either find the official
   knob or wrap the spawn behind a layer that filters by tool name before
   forwarding.
2. **Network allowlist enforcement.** Claude Code subagents inherit
   network access. A practical enforcement may require running the spawn
   in a child process with `iptables` / OS firewall rules, or proxying via
   a guarded HTTP client. The decision is deferred to the implementing
   block.
3. **Spawn budget propagation.** Caps must be propagated to nested
   subagent spawns. The mechanism is not specified here.
4. **Anthropic SDK fallback.** A backend that does not go through Claude
   Code (e.g. a future `AnthropicSDKBackend`) needs its own equivalents of
   the boundaries above. The same checklist applies, with implementation
   notes per backend.

---

## 5. What `MockAgentBackend` already gives us for free

- No filesystem writes (envelopes are returned in memory).
- No network calls.
- No secret access.
- Deterministic output (no token usage).
- No recursive spawn.

This is why MKT-2A and MKT-2B can be merged without revisiting the
boundaries: the backend in use cannot violate them. The boundaries become
load-bearing the moment a real backend is wired in.
