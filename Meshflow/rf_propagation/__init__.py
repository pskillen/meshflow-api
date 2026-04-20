"""RF propagation render pipeline.

This package wires the `meshflow-rf-propagation` (Meshtastic Site Planner)
engine into the API via a dedicated Celery worker and a content-addressed
render cache.

Public submodules:

- :mod:`rf_propagation.hashing` – SHA256 over a normalized RF profile.
- :mod:`rf_propagation.bounds` – centre+radius to WGS84 bbox maths.
- :mod:`rf_propagation.payload` – :class:`nodes.models.NodeRfProfile` to
  Site Planner ``CoveragePredictionRequest``.
- :mod:`rf_propagation.image` – GeoTIFF bytes to PNG bytes.
- :mod:`rf_propagation.client` – thin httpx-based Site Planner client.
- :mod:`rf_propagation.tasks` – the Celery render task itself.
"""
