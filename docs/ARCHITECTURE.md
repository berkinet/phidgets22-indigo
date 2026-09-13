# Plugin architecture

The plugin keeps Indigo-facing orchestration in `plugin.py` and delegates
shared runtime concerns to small services in the Server Plugin directory.

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

## Version collection

`version_collection.py` asynchronously reads immutable registry snapshots and
publishes the results through the shared state publisher. Indigo device states
remain the canonical store for collected server and firmware version data.
