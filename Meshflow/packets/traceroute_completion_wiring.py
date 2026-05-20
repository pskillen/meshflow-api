"""Register auto_traceroute_completed_from_packet handlers in product order (dx → mesh → traceroute)."""

from packets.signals import auto_traceroute_completed_from_packet


def connect_auto_traceroute_completed_receivers() -> None:
    """Connect completion handlers once; called from packets.apps.PacketsConfig.ready()."""
    from dx_monitoring.receivers import on_auto_traceroute_completed_from_packet as dx_handler
    from mesh_monitoring.receivers import on_auto_traceroute_completed_from_packet as mesh_handler
    from traceroute.receivers import on_auto_traceroute_completed_from_packet as tr_handler

    signal = auto_traceroute_completed_from_packet
    signal.connect(dx_handler, dispatch_uid="dx_monitoring.auto_traceroute_completed")
    signal.connect(mesh_handler, dispatch_uid="mesh_monitoring.auto_traceroute_completed")
    signal.connect(tr_handler, dispatch_uid="traceroute.auto_traceroute_completed")
