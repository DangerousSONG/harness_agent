# SafeHarness Console UI Acceptance

## Current Issue

The UI could read dashboard, PROMO, evolution, review, and version state, but the operation layer was incomplete:

- PROMO detail `Evolve` had no visible POST feedback.
- Evolution `Continue Evolution` did not route by `next_action`.
- The right-side `Next Action` panel rendered plain text instead of an actionable button.
- Review actions did not consistently expose loading, POST visibility, refresh, and Chat result feedback.
- Version rollback did not have an explicit second confirmation in the UI.

## Backend Progression Interfaces

`/api/promotions` must read candidate IDs from the runtime promotion store (`.skills_memory/PROMOTION_CANDIDATES.md` in local mode). Documentation examples must not be used as a PROMO source.

### Generate regression coverage review

- Method: `POST`
- Path: `/api/promotions/{promo_id}/evolve`
- Request body: none
- Response example:

```json
{
  "ok": true,
  "data": {
    "stage": "regression_pending",
    "review_id": "REV-1234ABCD",
    "message": "Created regression coverage review REV-1234ABCD for PROMO-F2C535BB. No file was modified.",
    "version": ""
  },
  "message": "Created regression coverage review REV-1234ABCD for PROMO-F2C535BB. No file was modified.",
  "next_actions": ["/review REV-1234ABCD", "/approve REV-1234ABCD", "/apply REV-1234ABCD"],
  "errors": []
}
```

### Generate skill patch review

- Method: `POST`
- Path: `/api/promotions/{promo_id}/evolve`
- Request body: none
- Response example:

```json
{
  "ok": true,
  "data": {
    "stage": "skill_patch_pending",
    "review_id": "REV-5678EFGH",
    "message": "Created skill promotion review REV-5678EFGH for PROMO-F2C535BB. No SKILL.md file was modified.",
    "version": ""
  },
  "message": "Created skill promotion review REV-5678EFGH for PROMO-F2C535BB. No SKILL.md file was modified.",
  "next_actions": ["/review REV-5678EFGH", "/approve REV-5678EFGH", "/apply REV-5678EFGH"],
  "errors": []
}
```

### Regenerate legacy PROMO with Promotion Eligibility

- Method: `POST`
- Path: `/api/promotions/{promo_id}/regenerate`
- Request body: none
- Response example:

```json
{
  "ok": true,
  "data": {
    "old_promo_id": "PROMO-F2C535BB",
    "old_status": "legacy_rejected",
    "new_promo_id": "PROMO-NEW12345",
    "new_promo": {
      "promo_id": "PROMO-NEW12345",
      "promotion_decision": "promote",
      "promotion_score": 0.81,
      "eligible_target": "skill_rule",
      "schema_status": "eligible",
      "is_legacy": false,
      "missing_fields": []
    },
    "missing_fields": ["promotion_decision", "promotion_score", "eligible_target"]
  },
  "message": "Regenerated PROMO-F2C535BB with Promotion Eligibility as PROMO-NEW12345.",
  "next_actions": ["/api/promotions/PROMO-NEW12345", "/api/promotions/PROMO-NEW12345/evolve"],
  "errors": []
}
```

### Approve review

- Method: `POST`
- Path: `/api/reviews/{review_id}/approve`
- Request body: none
- Response example:

```json
{
  "ok": true,
  "data": {
    "status": "approved",
    "patch_path": ".reviews/patches/REV-1234ABCD.diff",
    "has_patch": true
  },
  "message": "Review approved. No target file was modified.",
  "next_actions": ["/api/reviews/REV-1234ABCD/patch", "/api/reviews/REV-1234ABCD/apply"],
  "errors": []
}
```

### Apply review

- Method: `POST`
- Path: `/api/reviews/{review_id}/apply`
- Request body: none
- Response example:

```json
{
  "ok": true,
  "data": {
    "status": "applied",
    "modified_files": ["skills/markdown_writer/SKILL.md"],
    "message": "Applied skill promotion PROMO-F2C535BB to skills/markdown_writer/SKILL.md; recorded version v0.1.1.",
    "recorded_version": "v0.1.1"
  },
  "message": "Applied skill promotion PROMO-F2C535BB to skills/markdown_writer/SKILL.md; recorded version v0.1.1.",
  "next_actions": [],
  "errors": []
}
```

### Reject review

- Method: `POST`
- Path: `/api/reviews/{review_id}/reject`
- Request body: none
- Response example:

```json
{
  "ok": true,
  "data": {
    "status": "rejected",
    "review_id": "REV-1234ABCD"
  },
  "message": "Review rejected.",
  "next_actions": [],
  "errors": []
}
```

### Rollback version

- Method: `POST`
- Path: `/api/skills/{skill}/rollback`
- Request body:

```json
{
  "version": "v0.1.1"
}
```

- Response example:

```json
{
  "ok": true,
  "data": {
    "review_id": "REV-ROLLBACK",
    "status": "pending"
  },
  "message": "Created rollback review REV-ROLLBACK. No skill file was modified.",
  "next_actions": ["/api/reviews/REV-ROLLBACK", "/api/reviews/REV-ROLLBACK/approve"],
  "errors": []
}
```

## Fix Summary

- Added status-aware operation routing for Evolution `Continue Evolution`:
  - `create_regression_review`, `create_skill_review`, and `waiting` call `POST /api/promotions/{promo_id}/evolve`.
  - `approve_regression_review` and `approve_skill_review` call `POST /api/reviews/{review_id}/approve`.
  - `apply_regression_review` and `apply_skill_review` open the apply confirmation, then call `POST /api/reviews/{review_id}/apply`.
  - `completed` opens Versions.
- Kept PROMO modal `Evolve` wired to `POST /api/promotions/{promo_id}/evolve`.
- Changed right-side `Next Action` into a real button using the same routing logic.
- Added loading labels for PROMO, Evolution, Review, and Version operations.
- Added Chat tool-call/result entries for every POST operation.
- Improved failed request feedback to include HTTP status and backend message.
- Added second confirmation before rollback review creation.
- Refreshed dashboard, reviews, promotions, evolution state, and versions after successful operations.
- Added legacy PROMO handling:
  - Eligible PROMOs have `promotion_decision`, `promotion_score`, and `eligible_target`.
  - Legacy PROMOs missing those fields are shown as requiring regeneration.
  - Legacy PROMOs use `POST /api/promotions/{promo_id}/regenerate`, not `evolve`.
  - `/evolve` continues to reject legacy PROMOs and does not create regression reviews for them.

## Acceptance Steps

To seed a healthy local demo candidate, run:

```powershell
python scripts/seed_self_evolution_demo.py --skill markdown_writer
```

The command creates a real `LRN-*` learning record, then creates a `PROMO-*` candidate from that record through Promotion Eligibility. The PROMO must reference the real LRN, and `/api/promotions` should return the same PROMO ID that the UI shows in Promotions and Evolution.

1. Start the backend at `http://127.0.0.1:8000`.
2. Start the UI from `web/ui`.
3. Open the Evolution page and select the PROMO ID returned by `/api/promotions` for the local workspace. In the current local fixture this is `PROMO-F2C535BB`.
4. Click `Continue Evolution` or the right-side `Next Action` button.
5. Confirm Network shows `POST /api/promotions/{actual_promo_id}/evolve`, for example `POST /api/promotions/PROMO-F2C535BB/evolve`.
6. Approve the created regression review.
7. Apply the approved regression review after confirmation.
8. Continue evolution to generate the skill patch review.
9. Approve the skill patch review.
10. Apply the skill patch after confirmation.
11. Open Versions and confirm a version record exists for the same actual PROMO ID.

## Legacy PROMO Acceptance Steps

1. Open a legacy PROMO missing `promotion_decision`, `promotion_score`, or `eligible_target`.
2. Confirm the PROMO modal shows:
   - `Missing promotion_decision`
   - `Missing promotion_score`
   - `Missing eligible_target`
   - `Requires regeneration`
3. Confirm PROMO modal `Evolve`, Evolution `Continue Evolution`, and right-side `Next Action` show `Regenerate with Promotion Eligibility`.
4. Click the regeneration button.
5. Confirm Network shows `POST /api/promotions/{promo_id}/regenerate`.
6. Confirm the old PROMO is marked `legacy_rejected` and a new PROMO appears with `promotion_decision`, `promotion_score`, and `eligible_target`.
7. Confirm `/api/promotions/{old_promo_id}/evolve` still returns HTTP 400 and does not create a review.
8. Select the new eligible PROMO and continue the normal evolution flow.

## Dangling PROMO Acceptance Steps

Dangling PROMOs are candidates whose source memory record is missing. They are neither healthy eligible candidates nor regeneratable legacy candidates.

1. Create or open a PROMO whose `Record ID` / source memory id does not exist in `.skills_memory`, `skills/*/memory`, runtime memory, or `.reviews`.
2. Confirm `/api/promotions` returns structured invalid state:
   - `error_code: SOURCE_MEMORY_NOT_FOUND`
   - `promo_id`
   - `source_memory_id`
   - `suggested_action: archive_stale_promo_or_generate_new_candidate`
3. Confirm the UI does not show `Evolve`, `Continue Evolution`, or `Regenerate with Promotion Eligibility` as the primary action.
4. Confirm the UI shows:
   - `Source memory missing: <LRN-id>`
   - `Archive stale PROMO`
   - `Generate new promotion candidate from current memories`
5. Confirm dangling PROMOs cannot call `/evolve` or `/regenerate`.
6. Use `python scripts/seed_self_evolution_demo.py --skill markdown_writer` to generate a fresh healthy PROMO from current real memories.

## Skill-aware Chat Acceptance Steps

1. In Chat, type "你好". Confirm the response is a direct Chinese greeting, with no `Used skill / Why / Output / Memory` template and no forced `self_improvement` attribution.
2. Ask "今天天气怎样？用中文回答". Confirm Chat asks for a city and says realtime weather lookup is needed instead of returning a generic capability template.
1. In Chat, ask for a book-note template. Confirm the response is a normal answer, uses `markdown_writer`, and does not contain `Only command-mode chat is implemented`.
2. In Chat, state a durable book-note preference such as "from now on, book notes should use title, core idea, three insights, and action checklist". Confirm Chat creates an `LRN-*` learning signal under `markdown_writer` memory and returns `type=memory_captured`.
3. Ask for current workspace skills. Confirm Chat returns the available skill list from `/api/skills`.
4. Ask where self-evolution is currently blocked. Confirm Chat returns the selected PROMO state when context has `current_promo_id`, or a workspace-level promotion summary when none is selected.
5. Ask Chat to generate a regression review. Confirm it returns a proposed `POST /api/promotions/{promo_id}/evolve` action, or creates the review through that same existing API, and does not modify files.
6. Ask Chat to apply a review. Confirm it returns `type=approval_required`, includes a diff preview in `data.patch`, and requires a confirmation action before calling `/api/reviews/{review_id}/apply`.
7. Ask a normal question. Confirm Chat gives a real answer and never falls back to `Only command-mode chat is implemented`.

## Actual Result

- `npm.cmd --prefix web/ui run build` passed.
- Direct runtime validation of legacy regeneration passed: a legacy PROMO was marked `legacy_rejected`, and a new PROMO was created with `promotion_decision=promote`, numeric `promotion_score`, and `eligible_target=skill_rule`.
- `python scripts/seed_self_evolution_demo.py --skill markdown_writer` is available for local UI acceptance seeding; unit coverage verifies it creates a real LRN and a PROMO that references that LRN.
- `PROMO-F2C53BB` was an invalid example ID and must not be used as a fixed test value. The local store contains `PROMO-F2C535BB`; acceptance should always use the ID returned by `/api/promotions`.
- API-level validation through FastAPI TestClient could not run in this shell because the available Python runtime does not include `fastapi`, the repository `.venv` points to a missing Python executable, and network access for installing temporary Python dependencies was blocked by the environment.

## Known Issues

- `POST /api/promotions/{promo_id}/evolve` is the single backend progression endpoint for both regression-review creation and skill-patch-review creation; the stage depends on existing review and coverage state.
- Applying regression coverage is required before the backend can generate a skill patch review, even when a shortened manual checklist omits that step.
- The UI currently polls state every five seconds; a future version can replace that with server-sent events from `/api/chat/events` if the backend exposes streaming semantics.
