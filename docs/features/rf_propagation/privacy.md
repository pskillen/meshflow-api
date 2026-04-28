# RF propagation privacy

RF propagation coverage maps are intended to be publicly available. Node owners
may provide private, true radio coordinates so Meshflow can render a more
accurate public coverage map than it could from coarse or redacted Meshtastic
position data.

The privacy requirement is to use private coordinates as an internal render
input without exposing those coordinates, or enough derived metadata to infer
them, through the public map.

The open implementation issue is
[meshflow-api#245](https://github.com/pskillen/meshflow-api/issues/245).

## Current model

`NodeRfProfile` stores RF-specific transmitter data:

- `rf_latitude`
- `rf_longitude`
- `rf_altitude_m`
- antenna height, gain, pattern, azimuth, and beamwidth
- transmit power and frequency

The profile serializer hides `rf_latitude`, `rf_longitude`, and
`rf_altitude_m` unless the requester can edit the RF profile. Today that means
staff or the user who has claimed the observed node.

Render generation uses the true coordinates. The worker sends them to the Site
Planner engine as `lat` and `lon`, receives a georeferenced GeoTIFF, converts
it to a PNG, stores bounds on `NodeRfPropagationRender`, and returns those
bounds to the frontend for public display.

## What may leak today

Even when private profile fields are hidden, a ready render can reveal
coordinate-derived information through other surfaces:

- Exact `bounds` in the public RF propagation response.
- Visible RF patterns that can imply a transmitter origin.
- A public immutable asset URL containing the content hash filename.
- Repeated renders with slightly different inputs, which may allow comparison.
- Logs, task payloads, cache rows, or debugging artifacts that include exact
  coordinates.

The PNG being low resolution is not a complete privacy control. Low resolution
reduces visual precision, but exact georeferencing can still make the public
overlay more revealing than intended.

## Public response surface

The current ready response includes:

```json
{
  "status": "ready",
  "input_hash": "...",
  "asset_url": "https://.../{hash}.png",
  "bounds": {
    "west": -4.5,
    "south": 55.0,
    "east": -4.0,
    "north": 55.5
  }
}
```

The asset endpoint is currently public:

```text
GET /api/nodes/observed-nodes/{node_id}/rf-propagation/asset/{filename}
```

The `node_id` path component is reserved for future validation. At present,
the hash filename is the effective asset locator.

## Privacy goals

The feature should support accurate internal rendering and public map display
without exposing private coordinates more precisely than the product intends.

The public contract should define:

- Who can set or update the private coordinate input.
- Who can request recomputation of a public coverage map.
- Whether public bounds are exact, rounded, padded, cropped, or omitted.
- How much precision the public overlay is allowed to reveal.
- Whether the rendered image itself needs origin masking, cropping, blurring,
  or minimum resolution constraints.
- Whether public filenames and response metadata can be correlated with exact
  internal render inputs.

## Candidate approaches

### Rounded public bounds with adjusted raster

Render internally with true coordinates, then expose display bounds snapped to a
lower-precision grid. The image must be cropped, padded, or translated so the
public image still lines up with the public bounds.

This can support public display, but it needs careful tests. Rounding only the
bounds without adjusting the raster will intentionally misalign the overlay.

### Public derivative asset

Keep the exact internal GeoTIFF/PNG as a worker-side intermediate, then generate
a public asset with reduced precision. The public derivative could be lower
resolution, cropped to rounded bounds, padded to a grid, and stripped of exact
georeferencing metadata.

This separates internal correctness from public presentation, but adds storage,
retention, and cache-key complexity.

### Public display after obfuscation only

Until a precision-reducing derivative exists, do not expose exact render bounds
or exact-coordinate-derived assets publicly. The public map should be generated
only after the output has been transformed according to the documented privacy
contract.

This is conservative and avoids accidental leakage while preserving the intended
product shape: public coverage maps.

## Hash and cache considerations

`input_hash` includes normalized private coordinate values. The hash is not
reversible in the ordinary sense, but it can still be sensitive metadata:

- It is stable for a given private coordinate and RF profile.
- It is used as the public PNG filename.
- It may allow correlation between nodes or repeated renders.
- If an attacker can narrow the possible coordinate set enough, brute-force
  comparisons may become more plausible.

Future public contracts should avoid exposing `input_hash` unless clients need
it. Public filenames should likely use a separate random token or public
derivative hash rather than the internal input hash.

## Logging and operations

Private coordinates can also leak outside API responses. Avoid adding logs or
debug artifacts that include:

- raw Site Planner payloads
- `rf_latitude` or `rf_longitude`
- full GeoTIFF bounds for renders that used private coordinates
- temporary filenames or exported samples tied to a render that used private
  coordinates

When reproducing bugs, prefer synthetic coordinates or owner-approved examples.
If a production render must be inspected, store artifacts outside public issue
threads and remove them when the investigation is complete.

## Tests to add

When the privacy contract is implemented, tests should cover:

- RF profile coordinates remain hidden from unauthorized users.
- Public RF propagation responses do not return exact private-coordinate-derived
  bounds beyond the documented precision.
- Public RF assets follow the chosen derivative-asset rules.
- Public display bounds are rounded or transformed according to the documented
  contract.
- `input_hash` exposure matches the documented public response contract.

## Interaction with alignment fixes

Alignment work and privacy work are connected. The display needs accurate
georeferencing to line up with terrain, but exact public georeferencing can
reveal private coordinates.

Any fix that changes asset format, bounds, raster transforms, or frontend
rendering should explicitly answer:

1. Which artifact is the exact internal render intermediate?
2. Which artifact is the public coverage map?
3. Which bounds are exact, and which bounds are public display bounds?
4. Which metadata is safe to expose with the public map?
