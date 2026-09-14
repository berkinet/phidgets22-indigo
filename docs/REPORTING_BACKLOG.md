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
