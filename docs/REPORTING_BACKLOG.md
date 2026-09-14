# Problem-reporting review (deferred)

Review how the plugin reports outages and other problems before the Indigo
Plugin Store submission. This is a reporting/UX review, not evidence of an
unhandled Python error.

The 2026-09-14 CM-Piscine startup outage produced one Network Server Error,
two channel Errors, and three physical-device Errors at the same two-hour
timeout. All described the same unavailable server. The physical-device
summaries also said `server: any`, even though the configured server was
CM-Piscine.

Questions for the review:

- How many log entries are useful for one underlying server outage, and when
  should channel/physical-device detail be grouped or suppressed?
- Which messages should be Warning versus Error, and when should reminders
  repeat?
- Does each message identify the correct configured/observed server, scope,
  duration, and actionable next check without implying multiple failures?
- Do startup absence, operational detach, short interruption, and recovery
  each produce a clear, consistent narrative?

Preserve immediate diagnostic logging and the existing, separately timed
Indigo Events/Triggers while reviewing message number and wording.

## Job item: startup absence and recovery have no paired Events

**Observed 2026-09-14, CM-Piscine:** The server was absent when the plugin
started at 12:29. After 7,200 seconds, the plugin logged an unavailable-server
Error, but the `CM-Piscine - offline` detach Trigger did not run. Following a
later plugin restart and a Phidget Network Server service restart, the Indigo
Network Server device returned Online without a normal recovery log or an
attach Event/Trigger. The overnight 02:01 detach Trigger was a separate outage.

**Cause to address:** `serverInitiallyUnavailable()` sets Offline state but
does not deliver a detach Event. `serverAvailable()` suppresses the first
attachment Event in each plugin run and logs that attachment only at Debug
level. The Event coordinator also suppresses an attach when no detach was
delivered in the current run.

**Desired outcome / acceptance checks:**

- Define and implement a startup-absence threshold that avoids false alerts on
  a normal plugin restart but delivers one detach Event for a server that
  remains unavailable. Respect each Trigger's configured detach delay.
- When that sustained absence ends, log a visible recovery and deliver one
  matching attach Event; do not lose the outage/recovery pair merely because
  the plugin restarted in between.
- Keep the Indigo device's availability state accurate immediately and retain
  cancellation behavior for short interruptions.
- Test initial absence, recovery before/after the threshold, plugin restart
  during an outage, and ordinary operational detach/reattach.
