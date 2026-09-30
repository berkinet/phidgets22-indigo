# RFID test review — 2026-09-30

## Scope and outcome

Reviewed RFID hardware callbacks, simulation, tag policies and management,
delayed presence, and the related configuration/startup/lifecycle tests after
the RFID feature releases through 2026.1.19. Unrelated device tests were not
audited. No production-code changes were needed for the scenarios reviewed.

## Pruning and consolidation

- Removed the separate lookup-error logging test. Its assertions for reader,
  tag, protocol, failure reason, and absence of a denial warning now live in the
  existing missing-variable test, alongside raw-event/history preservation and
  inactive presence. This avoids recreating the same failed-lookup scenario.
- Replaced action/event count assertions with checks for the required IDs,
  reader selectors, device scope, and device-action menu placement. A count
  could pass with a required entry missing and an unrelated entry added.
- Updated list-edit fixtures to use current menu operation IDs. Kept the
  dedicated migration test for previously saved operation values.

## Strengthened coverage

- Run two readers with overlapping countdowns, expire them independently,
  and verify both opening and closing state publications permit Indigo events.
- Change the presence delay through the actual device-config callback while
  a countdown runs; verify that countdown retains its deadline and the next
  loss uses the new delay without a reader restart.
- Exercise denied tags and missing-list errors through actual policy evaluation
  during a countdown, including subsequent detections after it expires.
- Exercise real RFID startup with a fake native handle and check every callback
  is registered before open. The previous test called registration directly
  and therefore could not establish startup ordering.
- Record the same tag ID under two protocols in history and retain both records
  through preferences serialization. The previous history test covered repeats,
  bounds and reader isolation, but never varied protocol for one tag ID.
- Replace the single variable-write failure scenario with a move where one list
  saves and the other fails. Verify the saved change, unchanged failed list,
  named failed destination, device error, and partial-save guidance.

## Retained coverage

Kept the policy truth table, exact IDs/leading zeroes, per-reader variables,
Indigo-safe menu IDs and placeholders, staged Save/Cancel semantics, live-list
merging, raw event ordering, physical/simulated reader distinctions, antenna and
reconnect behavior, stale timer callbacks, stop/reset, and publication retries.
These protect distinct behaviors even where setup looks similar. Shared
lifecycle tests continue to cover native connection recovery and cleanup;
RFID-specific tests cover the additional tag and presence behavior.

## Verification and limits

The full unittest suite passed. Focused RFID tests run in well under one second
locally, so elapsed runtime does not justify further pruning. Python compilation
and XML/plist/whitespace validation also passed.

In a temporary copy, six intentional regressions were each caught by the
corresponding test: merging history across protocols, dropping live config
updates, letting denied/error tags qualify, omitting callback registration,
suppressing closing state events, and renaming a required action while keeping
the action count unchanged. No mutated production files were retained.

These are automated tests with fake Indigo/native endpoints. They establish
state-publication intent, not live Indigo trigger execution or physical reader
behavior. UI rendering, real tag/protocol reads, USB/network disconnection and
reconnection, and actual feeder actions still need live acceptance testing.
Timer tests deterministically deliver stale callbacks; they do not constitute
a general concurrency stress test. No unrelated-device audit was performed.
