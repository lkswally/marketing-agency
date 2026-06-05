# Real-Business Intake Template (MKT-8A)

How to fill the intake JSON for a real-client Alpha Pilot run.

The template ships at:

```
examples/intake/alpha-pilot-template.json
```

Copy it, rename it (`intake-<client-slug>.json`), and replace
every `<PLACEHOLDER>` with real data. The fields below explain
what each one means and how to think about it.

## Top-level fields

| Field                  | What to write                                                                 | Required |
|------------------------|--------------------------------------------------------------------------------|----------|
| `schema_version`       | Always `"client-intake.v1"` — do not edit.                                     | yes      |
| `client_name`          | Legal name of the business.                                                    | yes      |
| `industry`             | Free-form (e.g. `"specialty coffee"`, `"B2B SaaS"`, `"local dental practice"`).| yes      |
| `market`               | Primary market — region code or country (`"AR-CABA"`, `"LATAM"`, `"EMEA"`).    | yes      |
| `product_or_service`   | One-sentence description.                                                      | yes      |
| `product_type`         | One of: `subscription`, `one_off`, `service`, `physical_product`, `course`, `other`. | yes |
| `audience_description` | Who they sell to. Concrete. Avoid `"everyone"`.                                | yes      |
| `commercial_objective` | Measurable. `"50 demos / month for 90 days"`.                                  | yes      |
| `brand_tone`           | List of 3-5 adjectives (`"warm"`, `"direct"`, `"playful"`).                    | yes      |
| `preferred_words`      | Words the client wants to hear in the copy.                                    | optional |
| `forbidden_words`      | Words the client refuses to see.                                               | optional |
| `claim_style`          | How aggressive the claims should be.                                           | yes      |
| `possible_channels`    | List of channel slugs (`"newsletter"`, `"google_ads"`, ...).                   | yes      |
| `known_competitors`    | List of `{name, url, notes}` objects.                                          | optional |
| `budget_estimate`      | Number (currency below).                                                       | yes      |
| `budget_currency`      | `"USD"` / `"ARS"` / `"EUR"` / ...                                              | yes      |
| `deadline`             | `"YYYY-MM-DD"` — end of the campaign window.                                   | yes      |
| `duration_weeks`       | Integer.                                                                       | yes      |
| `primary_kpi`          | What success looks like (e.g. `"qualified_trials"`).                           | yes      |
| `locale`               | BCP-47 locale (`"es-AR"`, `"en-US"`, `"pt-BR"`).                               | yes      |
| `constraints`          | Hard constraints — no negotiation.                                             | optional |
| `claims_to_avoid`      | Statements the client must never make.                                         | optional |

## MKT-8A-specific block: `_alpha_pilot_notes`

The template carries a `_alpha_pilot_notes` object that does not
travel into the strategy pipeline — it is a checklist the operator
uses for safety review.

| Field                                          | Meaning                                                |
|------------------------------------------------|--------------------------------------------------------|
| `account_lead`                                 | Name of the agency account lead.                       |
| `approval_reviewer`                            | Name of the reviewer who signs off the approval pack.  |
| `atlas_handoff_expected_kinds`                 | Which of `landing` / `branding` / `page_design` are expected. |
| `atlas_handoff_target_pages`                   | Pages the operator anticipates needing.                |
| `real_publication_authorised`                  | MUST stay `false`. Pilot does not publish.             |
| `real_image_generation_authorised`             | MUST stay `false`. Pilot never generates images.        |
| `real_google_ads_writes_authorised`            | MUST stay `false`. Pilot never writes to Ads.           |
| `_safety_reminder`                             | Verbatim reminder text — do not edit.                  |

## Common mistakes

| Mistake                                              | Fix                                                                 |
|------------------------------------------------------|---------------------------------------------------------------------|
| `audience_description = "everyone"`                  | Be specific. The strategy engine needs to differentiate.            |
| `commercial_objective = "more sales"`                | Pick a number + horizon.                                            |
| `budget_estimate = 0` when paid ads are in scope     | Pick a number, even if approximate.                                 |
| `forbidden_words = []` when client has a "no" list   | Capture them — they save the campaign at the approval gate.         |
| Setting any `_alpha_pilot_notes` flag to `true`      | Stop. Pilot is read-only. File a `PENDING` first.                   |

## Validating the intake

```bash
mkt intake --file path/to/intake-<slug>.json
```

Exit 0 means the intake is well-formed. Errors tell the operator
which field is wrong.

## Privacy posture

- No credential is read from the intake — there is no field for
  one.
- The intake is persisted under `data/<slug>/client_intake/`
  in plaintext JSON. Treat the directory as confidential and
  store it outside the repo when the pilot ends.
- No tracking pixel or analytics identifier should appear in
  any field.

## Next step

Run the [Alpha Pilot Playbook](alpha-pilot-playbook.md).
