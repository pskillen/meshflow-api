from django.dispatch import Signal

# General packet signal
# This is used to signal that a packet has been received
# Args:
#   sender: The sender of the signal
#   packet: The packet that was received
#   observer: The observer that received the packet
#   observation: The observation that was created for the packet
#   user: The user that received the packet
packet_received = Signal()

# Specific packet type signals
# these all have the same signature as the packet_received signal
message_packet_received = Signal()
node_info_packet_received = Signal()
position_packet_received = Signal()
device_metrics_packet_received = Signal()
local_stats_packet_received = Signal()
environment_metrics_packet_received = Signal()
air_quality_metrics_packet_received = Signal()
health_metrics_packet_received = Signal()
host_metrics_packet_received = Signal()
power_metrics_packet_received = Signal()
traffic_management_stats_packet_received = Signal()
traceroute_packet_received = Signal()

# Emitted after a DeviceMetrics row is persisted for an observed node (mesh monitoring, analytics, etc.).
# kwargs: observed_node, device_metrics, battery_level, reported_time
device_metrics_recorded = Signal()

# Emitted after a traceroute response is linked to an AutoTraceRoute and completion is persisted.
# kwargs: auto_tr, traceroute_packet, packet_observation, observer, from_node
auto_traceroute_completed_from_packet = Signal()

# Emitted after packet-type processing, before ObservedNode.last_heard is updated (DX candidate rules).
# kwargs: packet, observer, observation, from_node, previous_last_heard, from_node_created
packet_from_node_processed = Signal()

# Emitted after ObservedNode.last_heard is advanced for this ingest.
# kwargs: observed_node, last_heard
node_last_heard_advanced = Signal()


# Converted packet signals
# These are used to signal that a text message has been received
# Args:
#   sender: The sender of the signal
#   message: The message that was received
#   observer: The observer that received the message
text_message_received = Signal()
# These are used to signal that a node claim has been authorized
# Args:
#   sender: The sender of the signal
#   node: The node that was authorized
#   claim: The claim that was authorized
#   observer: The observer that authorized the claim
node_claim_authorized = Signal()
# These are used to signal that a new node has been observed. It probably doesn't have any userinfo, etc yet.
# Args:
#   sender: The sender of the signal
#   node: The node that was observed
#   observer: The observer that observed the node
new_node_observed = Signal()
