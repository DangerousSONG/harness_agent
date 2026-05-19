# SafeHarness Console UI Acceptance

## Current Issue

The UI could read dashboard, PROMO, evolution, review, and version state, but the operation layer was incomplete:

- PROMO detail `Evolve` had no visible POST feedback.
- Evolution `Continue Evolution` did not route by `next_action`.
- The right-side `Next Action` panel rendered plain text instead of an actionable button.
- Review actions did not consistently expose loading, POST visibility, refresh, and Chat result feedback.
- Version rollback did not have an explicit second confirmation in the UI.

## Backend Progression Interfaces

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
    "message": "Created regression coverage review REV-1234ABCD for PROMO-F2C53BB. No file was modified.",
    "version": ""
  },
  "message": "Created regression coverage review REV-1234ABCD for PROMO-F2C53BB. No file was modified.",
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
    "message": "Created skill promotion review REV-5678EFGH for PROMO-F2C53BB. No SKILL.md file was modified.",
    "version": ""
  },
  "message": "Created skill promotion review REV-5678EFGH for PROMO-F2C53BB. No SKILL.md file was modified.",
  "next_actions": ["/review REV-5678EFGH", "/approve REV-5678EFGH", "/apply REV-5678EFGH"],
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
    "message": "Applied skill promotion PROMO-F2C53BB to skills/markdown_writer/SKILL.md; recorded version v0.1.1.",
    "recorded_version": "v0.1.1"
  },
  "message": "Applied skill promotion PROMO-F2C53BB to skills/markdown_writer/SKILL.md; recorded version v0.1.1.",
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

## Acceptance Steps

1. Start the backend at `http://127.0.0.1:8000`.
2. Start the UI from `web/ui`.
3. Open the Evolution page and select `PROMO-F2C53BB`.
4. Click `Continue Evolution` or the right-side `Next Action` button.
5. Confirm Network shows `POST /api/promotions/PROMO-F2C53BB/evolve`.
6. Approve the created regression review.
7. Apply the approved regression review after confirmation.
8. Continue evolution to generate the skill patch review.
9. Approve the skill patch review.
10. Apply the skill patch after confirmation.
11. Open Versions and confirm a version record exists for `PROMO-F2C53BB`.

## Actual Result

- `npm.cmd --prefix web/ui run build` passed.
- The exact local PROMO acceptance run could not complete in this workspace because `PROMO-F2C53BB` is not present in the local `.skills_memory/PROMOTION_CANDIDATES.md`.
- API-level validation through FastAPI TestClient could not run in this shell because the available Python runtime does not include `fastapi`, the repository `.venv` points to a missing Python executable, and network access for installing temporary Python dependencies was blocked by the environment.

## Known Issues

- `POST /api/promotions/{promo_id}/evolve` is the single backend progression endpoint for both regression-review creation and skill-patch-review creation; the stage depends on existing review and coverage state.
- Applying regression coverage is required before the backend can generate a skill patch review, even when a shortened manual checklist omits that step.
- The UI currently polls state every five seconds; a future version can replace that with server-sent events from `/api/chat/events` if the backend exposes streaming semantics.
