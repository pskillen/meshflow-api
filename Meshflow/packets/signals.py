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
