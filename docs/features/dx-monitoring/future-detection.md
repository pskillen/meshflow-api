# Future DX Detection Ideas

This guide records detection ideas that are useful for DX Monitoring but outside
the MVP candidate detection phase. They should be revisited after the system has
real event data, traceroute exploration, and enough operator visibility to tune
thresholds safely.

## Direct Link Emerges From A Previously Multi-Hop Path

A future detector should identify cases where packets between two nodes normally
arrive over a multi-hop path, but suddenly appear to link directly or nearly
directly.

This can indicate a transient propagation event. For example, two regions that
usually communicate only through intermediate routers may temporarily become
directly reachable during tropo. When that happens, a traceroute is useful while
the path is active because it can confirm whether the mesh has a new direct path,
a shorter route, or just one unusual packet.

## Inputs

This detector uses packet hop metadata rather than only positions:

- `PacketObservation.hop_start`.
- `PacketObservation.hop_limit`.
- The inferred hop count from those fields.
- The source `ObservedNode`.
- The observing `ManagedNode`.
- Historical hop counts for the same source and observer, or for the same source
and observing constellation.
- Optional position and distance data from the MVP detector.

## Candidate Signal

The detector opens or reinforces a candidate when:

- The source and observer are already known to be distant enough to be DX
relevant.
- Recent historical observations for that source normally require multiple hops.
- The current packet is observed with a direct or significantly lower-hop path.
- The change persists for enough packets, or is strong enough, to avoid reacting
to a single malformed or partial observation.

The exact threshold is a tuning decision. A useful first version might compare a
current inferred hop count of zero or one against a rolling baseline where the
same source is normally two or more hops away.

## Event Behaviour

The event reason code should be distinct from the MVP distance rules, for
example `shorter_path_detected` or `direct_link_detected`. It should deduplicate
by observing constellation, source node, observer, and active window.

Once traceroute exploration exists, this signal is a good trigger for a bounded
traceroute request because the most valuable evidence is the route shape while
the direct path is present.

## Open Questions

- How reliable are `hop_start` and `hop_limit` across packet types, firmware
versions, and relayed observations?
- Should the baseline be per observer, per constellation, or global?
- How many historical packets are needed before a shorter path is meaningful?
- Should one direct packet be enough during a known active DX event, while normal
conditions require repeated packets?
- How should encrypted or incomplete packets contribute to the baseline?
- How do we filter out mobile nodes, where the node is now literally closer to a previously far away node?

