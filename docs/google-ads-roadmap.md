# Google Ads — Roadmap

> Status: **roadmap only** (MKT-2C). No Google Ads connection exists. No
> developer token is stored.
> Phasing follows [`mcp-roadmap.md`](mcp-roadmap.md) MKT-MCP-4.

Google Ads is the highest-value AND highest-risk source. Reads are pure
gold for optimization; writes are spend events. The default posture is
**read-only forever** unless a future ADR opens a tightly-scoped write
phase with double-approval.

---

## 1. Read value vs. write risk

| Reads | Why it matters |
|-------|----------------|
| Campaign performance (clicks, impressions, conversions, cost) | Core ROI signal. |
| Ad group / ad / keyword performance | Granular optimization. |
| Search terms report | Negative-keyword recommendations. |
| Audience and demographic breakdown | Audience refinement. |
| Quality Score, ad rank | Diagnostic. |

| Writes | Why it's dangerous |
|--------|---------------------|
| Pause / enable campaign | Stops or starts spend. |
| Budget change | Direct financial impact. |
| Bid / CPC change | Same. |
| Add / remove keyword | Affects targeting and (for adds) opens spend on new terms. |
| Anything else (account, billing, conversion settings) | **Forbidden forever** without dedicated ADR. |

The asymmetry: a wrong read is at worst a confusing report; a wrong
write is real money spent or real reach lost.

---

## 2. Domain mapping

### 2.1 Metrics

Reads land as `Metric` entities with:

| Field | Value |
|-------|-------|
| `source` | `MetricSource.SOCIAL` until / unless we add a `google_ads` enum value (open question — see §7). Adapters MAY treat `source=social, dimensions.provider=google_ads` as a coexistence strategy. |
| `category` | `acquisition` (clicks, impressions), `conversion` (conversions, cost-per-conversion), `engagement` (CTR, average position) |
| `subject_type` + `subject_id` | mapped to MKT-owned `Campaign` / `Channel` / `Asset` ids via the per-client mapping (§5) |
| `provider_ref` | `gads:customer/<id>;campaign/<id>;...` (canonical form §3) |
| `dimensions` | device, country, network, ad position, etc. |
| `measured_at` | the row's date (UTC) |
| `confidence` | `1.0` |
| `is_estimate` | `false` |

### 2.2 Campaign correlation

When the MKT-owned `Campaign` has a `provider_ref` pointing at a Google
Ads campaign id, fetched metrics for that campaign attach to it via
`subject_id=<MKT Campaign id>`. The provider id stays in the metric's
`provider_ref` for reconciliation but does NOT replace `subject_id`.

### 2.3 Channel correlation

A Google Ads `Channel` entity (kind `paid_search` or `paid_social`)
should exist per Google Ads account / customer id. The mapping is
configured per client (§5).

---

## 3. `provider_ref` canonical form

```
gads:customer/<customerId>;campaign/<campaignId>[;adGroup/<adGroupId>][;keyword/<criterionId>];metric/<name>;date/<YYYY-MM-DD>
```

Examples:

```
gads:customer/123-456-7890;campaign/45000001;metric/cost;date/2026-05-31
gads:customer/123-456-7890;campaign/45000001;adGroup/3300010;keyword/77001;metric/clicks;date/2026-05-31
```

---

## 4. Permission policy (R3 read-only)

Per `permissions-policy.md` §3.3:

| Operation | Status |
|-----------|--------|
| `customer.list` | ✅ allowed |
| `campaign.search`, `adGroup.search`, `ad.search`, `keyword.search`, `searchTerm.search` | ✅ allowed |
| `*.report` (the GoogleAdsService query interface for reports) | ✅ allowed |
| `*.mutate` (any) | ❌ forbidden in R3 |
| Account, billing, conversion settings touched at any phase | ❌ forbidden forever (would require its own ADR) |

The adapter enforces this with a **deny-first** filter on tool names:
any tool matching `mutate*` / `pause*` / `enable*` / `add*` / `remove*`
/ `set*Budget*` is rejected even if the underlying MCP exposes it.

---

## 5. Per-client mapping

Each MKT client maps one or more Google Ads accounts:

```yaml
# data/clients/<client_slug>/external/gads.yaml (FUTURE)
contract_version: external-data-source.v0
source_id: "gads-acme-mcc"
provider: "gads"
provider_ref: "customers/1234567890"
mode: "read_only"
credentials_ref: "env(GADS_DEVELOPER_TOKEN)"
scopes: ["adwords_read"]   # adapter's internal label
status: "spec_only"

# Mapping between MKT-owned Campaigns/Channels and Google Ads ids.
# Filled by humans during onboarding; adapter consults read-only.
mapping:
  channels:
    - mkt_channel_id: "ch_paid_search_us"
      provider_ref: "gads:customer/1234567890"
  campaigns:
    - mkt_campaign_id: "camp_q3_launch"
      provider_ref: "gads:customer/1234567890;campaign/45000001"
```

---

## 6. Credentials

Google Ads requires three things, none of which live in the repo:

- A developer token (`GADS_DEVELOPER_TOKEN`).
- An OAuth refresh token per accessing identity
  (`GADS_OAUTH_REFRESH_TOKEN`).
- A `login_customer_id` for MCC (manager) accounts
  (`GADS_LOGIN_CUSTOMER_ID`).

All referenced by env-var name only. No values in specs, configs,
audits, or envelopes.

---

## 7. Write phase (R4) — gated, not planned

If a future ADR opens R4 for Google Ads, it MUST:

1. **Enumerate** every allowed `mutate` tool (e.g.
   `campaign.mutate{PAUSE}`, `campaign.mutate{ENABLE}`,
   `campaignBudget.mutate`, `keyword.mutate{ADD,REMOVE}`). Nothing else.
2. **Require double approval** (account lead + client side) per
   `permissions-policy.md` §3.3 footnote.
3. **Cap money-moving actions** at policy-level:
   - Single-action budget delta ≤ X% of current budget.
   - Daily aggregate of approved budget changes ≤ Y%.
   - Above caps require client-side legal-style sign-off (out of scope
     for any MKT block today).
4. **Provide a one-click revert** for every executed action. The
   `ProposedAction` carries a `revert_action` that the Approval Center
   can fire on its own.
5. **Forbid forever**: `customer.mutate`, anything touching billing,
   conversion settings, audience definitions, attribution settings.

Until that ADR exists, the adapter treats EVERY mutate-flavored tool as
forbidden.

---

## 8. Open questions

- **`MetricSource.GOOGLE_ADS` as a new enum value** vs reusing
  `social` with `dimensions.provider=google_ads`. Same trade-off as
  GA4's situation but with a clearer case for first-classing (paid is
  conceptually distinct from organic social). Defer to the block that
  ships the first Google Ads adapter. The decision is reversible at the
  cost of a domain-model bump.
- **MCC (manager) accounts** with many child customer ids: how does
  MKT scope reads/writes across multiple children? Probably one
  `ExternalDataSource` per child customer id with a shared credential.
- **Conversion attribution**: Google Ads conversions overlap with GA4
  conversions. The reconciliation policy (which is canonical, how to
  cross-check) is out of scope here.

---

## 9. Out of scope for MKT-2C

- The adapter module.
- Any actual fetch.
- Any token / developer-token handling.
- The OAuth flow.
- The R4 write phase.
- Domain enum changes.
- Any caching.
