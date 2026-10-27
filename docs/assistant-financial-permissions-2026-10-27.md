# Assistant financial permissions — 2026-10-27

Base: the verified production commit `c63efe74c21f36f9a25161438abda3db363186a9`
(schema 66), not the older `main` branch.

## Confirmed risks

An ordinary workspace member without the finance grant could:

- Ask the assistant's `get_record` tool for an expense by ID. The tool called
  `Service.get` directly; the normal expense-list permission and key-based
  redaction did not protect its generic `amount_kopecks` and category fields.
- Request a catalog-cost change. Its server-generated preview disclosed the
  previous cost under `field: cost_price`, `before`, and `after`.
  The same preview was readable after revoking a previously granted permission.
- Receive private quote-item costs inside proposal and confirmation/undo payloads.
  Non-GET assistant endpoints bypassed the shared response filter, and internal
  undo snapshots contained costs even when the visible quote itself was filtered.

The regression suite reproduced six failures before applying the fixes. The
successful authorized catalog edit/apply/undo case already passed on the base.

## Changes

- Expense reads enforce the section permission before a record lookup.
- Proposals discard unauthorized top-level cost inputs before preparing a diff;
  expense proposals require financial access.
- Proposal/tool results are filtered before they can leave the assistant.
  Full quote costs and undo snapshots remain in server-side action storage.
- The shared recursive response filter recognizes financial diff descriptors and
  complete expense actions, in addition to ordinary protected dictionary keys.
- POST assistant requests keep model/SSE work outside the normal write transaction
  and now pass through the same response-permission boundary as GET requests.
- Confirmation checks the current request's financial access before applying or
  replaying a stored expense or top-level cost proposal. It refuses a stale
  financial proposal instead of applying only some of its changes.
- Revoked cost access blocks cost-specific undo. Cached ordinary quote results and
  undo replays are redacted according to the current permission.

## Scope

The permission fixes require no schema migration and do not change deterministic
financial arithmetic. This branch also contains the separately requested mobile
registration fixes documented in `docs/mobile-registration-2026-10-27.md`.
Android native sources and the unfinished support-images branch are not included.

Tests use a disposable database and a fixture model; they do not query customer
records or send private data to a live model. These changes govern structured tool
results/actions. Previously authorized prose in a user's own chat history is not
retroactively rewritten.

## Verification

- Python 3.12.16: `python -m unittest discover -s tests -v` — 1007 tests passed
  in 108.158 seconds, no skips. Optional database tests ran against disposable
  PostgreSQL 17.11 with a limited runtime role and the existing CI core schema.
- 14 new finance regression tests cover denied and granted expense reads,
  catalog previews, direct tool results, pending/replayed confirmations, undo,
  revoked grants, SSE and exact cost preservation.
- Ruff, compileall, web build and `git diff --check` passed.
- The PostgreSQL fixture covers core runtime/RLS and the pre-existing stability
  tests. It does not reproduce every hosted Supabase service or the entire
  production schema.
