# Plugin architecture

The plugin keeps Indigo-facing orchestration in `plugin.py` and delegates
shared runtime concerns to small services in the Server Plugin directory.

## Connection identities

`connection_identity.py` defines immutable identities at five distinct levels:
Network Server, physical Phidget, VINT hub port, live channel, and saved Indigo
channel address. Server identities retain configured and runtime aliases while
providing one canonical grouping key and display name.

Discovery, duplicate-address validation, outage reporting, physical attachment
recovery, and version collection consume these identities instead of building
similar but differently interpreted tuples. A serial number is therefore
scoped to its server, while ports and channels remain separate identity levels.

## Runtime device registry

`runtime_registry.py` is the canonical, thread-safe index of active Phidget
wrappers and Network Server monitors. Device lifecycle code registers and
removes entries; actions, display providers, discovery, and version collection
consume snapshots or lookups rather than sharing mutable dictionaries.

## State publication

`state_publisher.py` is the single path for publishing device states to Indigo.
The first observation of each state after plugin startup establishes a silent
hardware baseline. Later observations use Indigo's normal event behavior.
Bulk publication isolates individual state failures, which permits older
Indigo devices to migrate safely when new states are introduced.

## Attachment events

`event_coordinator.py` owns trigger registration and delayed detach timers.
A detach trigger fires only if the source remains detached for its configured
delay. The corresponding attach trigger fires only when that detach was
actually reported, while device status itself remains immediate.

A previously attached physical channel logs its SDK detach immediately. The
grace period suppresses only Indigo detach/attach trigger pairs for transient
interruptions; it does not suppress the diagnostic record of the interruption.
Optional Error escalation has its own cancellable per-channel timer and is
therefore independent of both the diagnostic Warning and Indigo Event delay.

`outage_coordinator.py` separately coalesces simultaneous channel transitions
into physical-device or Network Server diagnostics. It owns the short grouping
timers, outage records, recovery batches, and repeated-error suppression; the
plugin supplies only a thread-safe channel snapshot and logger.

## Version collection

`version_collection.py` asynchronously reads immutable registry snapshots and
publishes the results through the shared state publisher. Indigo device states
remain the canonical store for collected server and firmware version data.
