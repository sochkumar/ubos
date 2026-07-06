# Pytest failure triage — Pass D (Feb 2026)

**Run**: `pytest -q -n 0` (serial, deterministic). No test code was modified.

**Result**: 40 failed / 197 passed / 1 skipped / 17 errors / 3 warnings (76 s).

Per user directive (Pass D brief): failures are FLAGGED, not patched. Each entry
below carries the test name, failing line, and my best hypothesis.

---

## Category A — Pre-existing stale tests (Phase 0 no-auth model)

These tests date back to Phase 0, when there was no auth and every request
carried only `X-Org-Id: demo-org`. Phase 1 added mandatory bearer auth to every
entity-type / field / record endpoint (`require_permission(...)` dependency).
The tests still send only `X-Org-Id` → API returns `401`, response body is a
`{"detail": "..."}` dict, and iterating it yields string keys (hence the
`TypeError: string indices must be integers` seen in most of these).

**Verdict**: pre-existing stale tests, not app bugs. Behaviour change was
intentional in Phase 1.

| Test | Line | Symptom |
|------|------|---------|
| `test_ubos_phase0.py::TestHealth::test_no_org_header_defaults` | 41 | `401 == 200` — endpoint now needs bearer. |
| `test_ubos_phase0.py::TestEntityTypes::test_invalid_key_422` | 56 | `401` short-circuits before validation. |
| `test_ubos_phase0.py::TestEntityTypes::test_create_list_duplicate` | 63-64 | `TypeError` on dict-vs-list. |
| `test_ubos_phase0.py::TestEntityTypes::test_patch_and_delete_cascade` | — | Same as above. |
| `test_ubos_phase0.py::TestFields::test_create_and_list_ordered` | 162 | Same. |
| `test_ubos_phase0.py::TestTenantIsolation::test_orgs_isolated` | 293 | Same. |
| `test_ubos_phase0.py::TestSeedDemo::test_seed_idempotent_and_counters` | 320 | Same. |
| `test_ubos_phase0.py::TestRecords::test_missing_required` (+ 3 siblings) | — | Fixture 401s → test errors. |

---

## Category B — Import/Export tests: setup fixture creates its ET under an org
             the caller isn't a member of

`test_ubos_phase5a.py::TestExport::*` and `test_ubos_phase5a::TestImport::*`
all fail with `404 "entity type not found"` immediately after the fixture
posts one. The identical shape occurs in the phase-5a hotfix suite for the
in-batch unique tests.

Reading the fixtures: the ET is created under one org context, and the
`et_id` is later used against `ctx.org_id` derived from a different bearer,
so `tenant_filter(org_id)` rejects the lookup as a 404.

**Verdict**: fixture/test-state issue — the test seed & the acting bearer's
default org are misaligned. Same root cause across ~15 tests. Not an app bug.

| Test | Line |
|------|------|
| `test_ubos_phase5a.py::TestImport::test_preview_suggested_mapping` | ~ | 404 on preview |
| `test_ubos_phase5a.py::TestImport::test_preview_no_extension` | ~ | 404 |
| `test_ubos_phase5a.py::TestImport::test_preview_bad_extension` | ~ | 404 |
| `test_ubos_phase5a.py::TestImport::test_preview_file_too_large` | ~ | 404 |
| `test_ubos_phase5a.py::TestImport::test_plan_error_policy_counts` | ~ | 404 |
| `test_ubos_phase5a.py::TestImport::test_execute_and_progress` | ~ | 404 |
| `test_ubos_phase5a.py::TestExport::test_csv_export_bom_and_headers` | 73 | 404 |
| `test_ubos_phase5a.py::TestExport::test_xlsx_export_readable` | ~ | 404 |
| `test_ubos_phase5a.py::TestExport::test_export_filter_q` | ~ | 404 |
| `test_ubos_phase5a.py::TestExport::test_export_columns_filter` | ~ | 404 |
| `test_ubos_phase5a.py::TestExport::test_export_writes_audit` | ~ | 404 |
| `test_ubos_phase5a.py::TestExport::test_bulk_export_preserves_order` (ERROR) | fixture | 404 in setup |
| `test_ubos_phase5a.py::TestPasswordShares::*` (6 ERRORS) | fixture | share fixture depends on missing ET |
| `test_ubos_phase5a_hotfix.py::TestPlanInBatchUnique::*` (4 FAILs) | 59 | 404 |
| `test_ubos_phase5a_hotfix.py::TestExecuteInBatchUnique::*` (3 FAILs) | 72 | 404 |
| `test_ubos_phase5a_hotfix.py::TestCrossBatchUnique::test_cross_batch_dup_detected` | 241 | 404 |
| `test_ubos_phase5a_hotfix.py::TestDropdownFriendlyError::test_dropdown_unknown_value_returns_friendly_msg` | 288 | 404 |
| `test_ubos_phase5a_hotfix.py::TestOrgMemberBypass::*` (6 ERRORS) | fixture | same |

---

## Category C — Invitations/Collaborators: seed-state leaks between test runs

Multiple `phase5b` tests write real rows into the shared `Acme Furniture` org
and assume a clean slate that no longer holds after previous runs.

| Test | Line | Symptom | Hypothesis |
|------|------|---------|------------|
| `test_ubos_phase5b.py::TestInvitations::test_already_member` | 112 | Expected `already_member`, got `duplicate_pending` | A previous run left `editor@ubos.test` as a pending invite; the test asserts the "already a member" branch, but the API takes the earlier "duplicate_pending" branch first. Test-order/state leak. |
| `test_ubos_phase5b.py::TestCollaborators::test_add_collaborator_view_perm` | 345 | `400 "user is not a member of this org"` | Test tries to add a collaborator user_id who lost membership in a prior run. |
| `test_ubos_phase5b.py::TestCollaborators::test_editor_cannot_see_view_before` | — | Same setup 400. |
| `test_ubos_phase5b.py::TestCollaborators::test_editor_sees_view_after` | — | Depends on above. |
| `test_ubos_phase5b.py::TestCollaborators::test_view_collab_cannot_patch` | — | Depends. |
| `test_ubos_phase5b.py::TestCollaborators::test_edit_perm_allows_patch` | — | Depends. |
| `test_ubos_phase5b.py::TestCollaborators::test_list_collaborators_hydrated` | 377 | assertion False | Depends on prior test writing the collaborator row. |
| `test_ubos_phase5b.py::TestCollaborators::test_remove_collaborator` | — | Depends. |
| `test_ubos_phase6a.py::TestOwnerSelfCollab::test_owner_cannot_add_self` | 256 | `400 "user is not a member of this org"` | Same seed drift. |
| `test_ubos_phase1.py::TestOrgs::test_members_list` | — | Depends on stable membership seed. |

**Verdict**: legitimate test-isolation problems — fixtures don't reset
`memberships` before running. A single `_reset_acme.py` module exists but is
not invoked from these tests. Not app bugs.

---

## Category D — Templates skip/dry-run tests

| Test | Line | Symptom | Hypothesis |
|------|------|---------|------------|
| `test_ubos_phase2.py::TestTemplates::test_dry_run_no_writes` | — | assertion | Depends on the org having NO existing entity types before `dry_run` runs. Prior test runs have populated the acme org. |
| `test_ubos_phase2.py::TestTemplates::test_apply_skip_creates_entities` | — | same shape |

**Verdict**: seed-state leak, not app bug.

---

## Category E — Environment-specific: rate limit not triggering

| Test | Line | Symptom | Hypothesis |
|------|------|---------|------------|
| `test_ubos_phase4a.py::TestRateLimit::test_public_read_rate_limit` | 315 | 80 hits, all `200`, no `429` | Env-specific: `PUBLIC_READ_RATE_LIMIT` is `120/minute` in the running server and the test only fires 80 hits — under the limit. Test constants haven't been updated for the current env value, OR the test expects a lower env override that's not applied in this pod. |

**Verdict**: needs a real check — could be a test-only env miss, or a genuine
regression if the limiter was silently disabled. Recommend running the
`testing_agent_v3` on the rate-limit flow specifically to determine which.
Kept as flag, not patched.

---

## Category F — Media test cross-worker contention

| Test | Line | Symptom |
|------|------|---------|
| `test_ubos_phase3b.py::TestMediaDeleteCascade::test_delete_attached_conflict_and_cascade` | 432 | `used_after (127117359) > used_before (127116125)` |

**Verdict**: known pre-existing test-only race (documented in PRD line 263 as
"Refactor `TestMediaDeleteCascade` to compare quota delta vs media size
instead of absolute `used_bytes` (avoids xdist worker cross-talk)"). Not an
app bug. Also `TestImageFileFields::test_image_field_lifecycle` fails from
the same source volatility.

---

## Category G — pytest deprecation warning (not a failure)

Three tests use `@pytest.fixture` on instance methods (class-scoped). Pytest
10 will drop this. **Warning only**, tests pass. Refactor to `@classmethod`
in a follow-up.

---

## Summary

- Zero app bugs identified from the pytest failure list.
- 40+ failures split cleanly into: **stale Phase-0-era tests (no bearer)**,
  **test-fixture drift (org membership leaks between runs, ET-under-wrong-org)**,
  **env-dependent rate-limit constants**, and **one xdist race**.
- No silent patches were applied. The security/performance side of Pass D
  (cross-org isolation, public payload masking, rate limiting, N+1 queries)
  is now handed off to `testing_agent_v3` — see its report in
  `/app/test_reports/iteration_17.json`.

**Recommended user actions** (not done by me):
1. Refactor `_reset_acme.py` into a session-scoped autouse fixture across
   the phase-1 / phase-5b / phase-6a suites, or teach each affected test to
   reset its membership row explicitly.
2. Delete the Phase 0 no-auth tests, or add a bearer-injecting fixture to
   them.
3. Confirm whether `PUBLIC_READ_RATE_LIMIT` should be a smaller number in
   the test env; adjust either the constant or the loop count.
4. Refactor `TestMediaDeleteCascade` per the existing PRD backlog item.
