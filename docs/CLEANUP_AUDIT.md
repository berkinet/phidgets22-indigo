# Preparatory cleanup audit

Audit date: 2026-08-21  
First identifiable test version: `0.2.1.1`

## Scope

This cleanup is intentionally narrow. It removes only imports that are mechanically unused by plugin-owned modules and assigns a distinct beta version to the test build. It does not change device addressing, channel opening, events, states, actions, configuration defaults, or the bundled Phidget22 SDK.

## Removed now

Unused imports were removed from the plugin lifecycle module, shared wrapper base, seven device wrappers, discovery utilities, sensor metadata helper, and standalone scanner. These names had no references in their modules and their removal does not alter control flow.

No source file or Indigo XML definition was deleted.

## Retained intentionally

| Item | Reason retained |
| --- | --- |
| `NetInfo.hostname`, `port`, and `password` | Plausible seam for explicit server constraints; server-selection design is not yet complete. |
| `NetInfo.serverDiscovery` | Records an existing preference even though the current channel path does not consume it. Remove or connect only after preference semantics are decided. |
| Long `deviceStartComm()` conditional | Awkward but production-proven and not blocking hierarchical selection. Refactoring now would mix risk with UI work. |
| Empty `Actions.xml` | Retained as part of the conventional Indigo plugin bundle and because standard Indigo actions are handled through callbacks. |
| Bundled `Phidget22` package | Vendor-generated dependency; it is not a cleanup target. |
| `make_phidget_lists.py` | Build/maintenance utility for `phidgets.json`, not runtime dead code. |
| Manual addressing fields | Required production fallback until discovery-backed configuration is validated. |

## Deferred behavior-affecting cleanup

The baseline assessment records several suspicious or awkward paths, including humidity trigger bounds, frequency count states, digital-input display state naming, post-attach error state, and stop/timer assumptions. Those are not mechanical cleanup. Each requires a focused reproduction or hardware-backed test before modification.

The misspelled `defualtValue` attributes in `Devices.xml` are also deferred. Correcting them could change saved/default UI behavior and should be handled as a separately tested configuration fix.

## Deletion rule

A spur should be deleted only when all three conditions hold:

1. It has no active runtime, build, diagnostic, or migration use.
2. The replacement path is implemented and tested in Indigo.
3. Removal is isolated in a reviewable commit with validation proving that the plugin bundle still loads.

As of 0.3.28, hierarchical Indigo discovery is implemented and validated, so
the obsolete standalone `scan.py` reference utility has been removed.
