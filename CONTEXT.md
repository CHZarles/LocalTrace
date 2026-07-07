# LocalTrace Context

LocalTrace is a local-only activity capture system. This glossary keeps issue,
spec, and implementation language aligned.

## Language

**Capture Source**:
A runtime component that observes local activity and posts raw events to the
LocalTrace core.
_Avoid_: Collector, tracker

**Raw Event**:
The stored record of one observed activity signal from a capture source.
_Avoid_: Log line, timeline segment, block

**Source Freshness**:
How old the latest observed event is for one capture source.
_Avoid_: Source latency

**Receive Lag**:
The elapsed time between an event's observation by a capture source and receipt
by the LocalTrace core.
_Avoid_: UI lag, freshness

**UI Freshness**:
How old the Web UI's last successful data refresh is.
_Avoid_: Capture latency
