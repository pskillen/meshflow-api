# Meshtastic Packet Fields Documentation

This document outlines the structure of different packet types in the Meshtastic network.

## Common Fields

All packet types share these common fields:

| Field Name | Data Type | Description              | Notes                               |
|------------|-----------|--------------------------|-------------------------------------|
| from       | integer   | Sender's node ID         | Numeric identifier                  |
| to         | integer   | Recipient's node ID      | 4294967295 for broadcast            |
| channel    | integer   | Channel number           | 0-based                             |
| id         | integer   | Packet identifier        | Unique per sender, not globally     |
| rxTime     | integer   | Reception timestamp      | Unix timestamp; optional (see below) |
| rxSnr      | float     | Signal-to-noise ratio    | -                                   |
| hopLimit   | integer   | Maximum number of hops   | -                                   |
| hopStart   | integer   | Initial hop count        | -                                   |
| fromId     | string    | Sender's node ID         | String format (e.g. "!433d4494")    |
| toId       | string    | Recipient's node ID      | String format, "^all" for broadcast |
| raw        | string    | Raw packet data          | Text format of the complete packet  |
| rxRssi     | float     | Received signal strength | Absent on a 2.8 replay; feeds replay detection |
| priority   | string    | Packet priority          | `BACKGROUND` on a 2.8 replay; feeds replay detection |
| transportMechanism | string or int | How the packet arrived | `TRANSPORT_LORA` on a 2.8 replay; `TRANSPORT_MQTT` is never a replay. Feeds replay detection and is stored as `PacketObservation.transport_mechanism` (an int becomes its name, an unknown int `TRANSPORT_<n>`). **Absent means `TRANSPORT_INTERNAL`** (protobuf JSON omits 0: the feeder's own packet), not LoRa: stored null |
| viaMqtt    | boolean   | Packet came from MQTT    | Stored as `PacketObservation.via_mqtt`; absent is false |
| replayed   | boolean   | Bot-side replay flag     | Optional (body only, default false). Stored as `PacketObservation.replayed` |

### Transport and hop limit

`PacketObservation.via_mqtt` and `transport_mechanism` record how the packet reached the feeder. Both are null on rows
from before they existed, and `transport_mechanism` is null for the feeder's own packets (absent means
`TRANSPORT_INTERNAL`). Null counts as radio. MQTT, multicast UDP, unicast UDP and API packets are not radio: see
[meshtastic.md](meshtastic.md#non-rf-transports). The observation API returns both fields.

`hopLimit` absent with a non-zero `hopStart` is stored as `hop_limit` 0 (proto3 JSON omits zero: the packet used its
last hop). On a replay, or with no `hopStart`, it stays null (unknown).

### Replayed packets

`PacketObservation.replayed` is true for a 2.8 connect-time replay: the body says `replayed: true`, or the packet has
the replay shape (no `rxRssi`, `TRANSPORT_LORA`, `BACKGROUND`, not the feeder's own). It is exposed as `replayed` in
the observation API. See [meshtastic.md](meshtastic.md#replayed-packets-28).

### Hops, `decoded.bitfield` and unknown hop counts

`decoded.bitfield` (2.8+ firmware, any port) is stored on `PacketObservation.bitfield`, a nullable non-negative bigint column
(`PositiveBigIntegerField`) so any firmware uint32 fits. Absent stays null, which is different from `0`.

2.8 HopScaling lowers `hopStart` on broadcast POSITION, TELEMETRY, NODEINFO and NEIGHBORINFO packets depending on
mesh density, and a 2.8 relay can send `hopStart == 0` on a packet that travelled. So **`hopStart == 0` with no
bitfield means the hop count is unknown**, not direct:

- `hop_count` in the observation API is null and `direct_from_sender` is false;
- DX detection does not treat the observation as direct;
- `hopStart == 0` with a bitfield (even `0`) is a real zero: `hopLimit == 0` then means direct.

`NodeLatestStatus.meshtastic_inferred_max_hops` (with `_at` and `_source`, the port name) ignores unknown-hop,
inconsistent (`hopStart < hopLimit`) and MQTT observations. TEXT_MESSAGE, TRACEROUTE, ROUTING, ADMIN and generic
ports are authoritative and can lower it. POSITION, TELEMETRY, NODEINFO and NEIGHBORINFO may only raise it, and only
when no authoritative value is younger than 7 days.

## Packet Type Specific Fields

### NODEINFO_APP

Node information packets contain device details:

| Field Name             | Data Type | Description            | Notes                 |
|------------------------|-----------|------------------------|-----------------------|
| decoded.portnum        | string    | Packet type identifier | Always "NODEINFO_APP" |
| decoded.user.id        | string    | Node ID                | Format: "!<hex>"      |
| decoded.user.longName  | string    | Full node name         | UTF-8 encoded         |
| decoded.user.shortName | string    | Short node name        | Max 4 characters      |
| decoded.user.macaddr   | string    | MAC address            | Base64 encoded        |
| decoded.user.hwModel   | string    | Hardware model         | Normalised to the enum name: a number (lib 2.7.11 sends 2.8 models as `150`) maps to its name, an unknown number becomes `HW_<n>`, and renamed 2.7 names (`SENSELORA_S3`) map to their 2.8 name. e.g. "HELTEC_V3" |
| decoded.user.role      | string    | Node role              | e.g. "CLIENT_MUTE"    |
| decoded.user.publicKey | string    | Public key             | Base64 encoded        |
| decoded.user.isLicensed | boolean  | Ham radio operator flag | -                    |
| decoded.user.isUnmessagable | boolean | Whether node can receive messages | -        |

### POSITION_APP

Position packets contain location data:

| Field Name                      | Data Type | Description            | Notes                 |
|---------------------------------|-----------|------------------------|-----------------------|
| decoded.portnum                 | string    | Packet type identifier | Always "POSITION_APP" |
| decoded.position.latitudeI      | integer   | Latitude (integer)     | Scaled by 1e7         |
| decoded.position.longitudeI     | integer   | Longitude (integer)    | Scaled by 1e7         |
| decoded.position.altitude       | integer   | Altitude in meters     | -                     |
| decoded.position.time           | integer   | Position timestamp     | Unix timestamp        |
| decoded.position.locationSource | string    | Source of location     | e.g. "LOC_MANUAL"     |
| decoded.position.groundSpeed    | integer   | Speed in km/h          | -                     |
| decoded.position.groundTrack    | integer   | Track in degrees       | 0-359                 |
| decoded.position.precisionBits  | integer   | Position precision     | -                     |
| decoded.position.latitude       | float     | Latitude (decimal)     | -                     |
| decoded.position.longitude      | float     | Longitude (decimal)    | -                     |

**0,0 and missing coordinates.** Fixed-position nodes on Meshtastic 2.7.24-2.7.26 broadcast 0,0 ("null island").
The packet is accepted (201, not 400) and still counts as hearing the node (`last_heard`, inferred max hops), but
it is stored with null `latitude` and `longitude`, no `nodes.Position` row is created, and `NodeLatestStatus`
keeps its previous position. A position counts as 0,0 when both coordinates are within 1e-7 of zero
(`common.geo.is_null_island`). A packet missing either coordinate is treated the same way. A position on one axis
only (for example 0, 12.3) is a real position and is kept. Rows stored before this rule are cleaned up with
`python manage.py cleanup_null_island_positions` (dry run by default; `--apply` writes).

### TELEMETRY_APP

Telemetry packets contain device and sensor metrics. All TELEMETRY_APP packets share common fields, and **exactly one** of the variant objects (deviceMetrics, localStats, environmentMetrics, etc.) appears in `decoded.telemetry` per packet.

**Spec reference:** [meshtastic/telemetry.proto](https://github.com/meshtastic/protobufs/blob/master/meshtastic/telemetry.proto)

#### Common TELEMETRY_APP fields

| Field Name          | Data Type | Description            | Notes                  |
|---------------------|-----------|------------------------|------------------------|
| decoded.portnum     | string    | Packet type identifier | Always "TELEMETRY_APP" |
| decoded.telemetry.time | integer | Telemetry timestamp    | Unix timestamp         |

#### 1. deviceMetrics

| Field Name                                         | Data Type | Description            | Notes                  |
|----------------------------------------------------|-----------|------------------------|------------------------|
| decoded.telemetry.deviceMetrics.batteryLevel       | integer   | Battery level          | 0-100                  |
| decoded.telemetry.deviceMetrics.voltage            | float     | Battery voltage        | In volts               |
| decoded.telemetry.deviceMetrics.channelUtilization | float     | Channel usage          | Percentage             |
| decoded.telemetry.deviceMetrics.airUtilTx          | float     | Air utilization        | Percentage             |
| decoded.telemetry.deviceMetrics.uptimeSeconds      | integer   | Device uptime          | In seconds             |

#### 2. localStats

| Field Name                                           | Data Type | Description            | Notes |
|------------------------------------------------------|-----------|------------------------|-------|
| decoded.telemetry.localStats.uptimeSeconds           | integer   | Device uptime          | In seconds |
| decoded.telemetry.localStats.channelUtilization      | float     | Channel usage          | Percentage |
| decoded.telemetry.localStats.airUtilTx               | float     | Air utilization        | Percentage |
| decoded.telemetry.localStats.numPacketsTx           | integer   | Packets transmitted    | - |
| decoded.telemetry.localStats.numPacketsRx           | integer   | Packets received       | - |
| decoded.telemetry.localStats.numPacketsRxBad         | integer   | Bad packets received   | - |
| decoded.telemetry.localStats.numOnlineNodes         | integer   | Online nodes seen      | - |
| decoded.telemetry.localStats.numTotalNodes           | integer   | Total nodes seen       | - |
| decoded.telemetry.localStats.numRxDupe              | integer   | Duplicate packets rx   | - |
| decoded.telemetry.localStats.numTxRelay             | integer   | Relay transmissions    | - |
| decoded.telemetry.localStats.numTxRelayCanceled     | integer   | Relay tx canceled      | - |
| decoded.telemetry.localStats.heapTotalBytes         | integer   | Total heap size        | - |
| decoded.telemetry.localStats.heapFreeBytes          | integer   | Free heap bytes        | - |
| decoded.telemetry.localStats.numTxDropped            | integer   | Dropped transmissions  | - |
| decoded.telemetry.localStats.noiseFloor             | integer   | Noise floor            | dBm |

#### 3. environmentMetrics

| Field Name                                              | Data Type | Description            | Notes |
|---------------------------------------------------------|-----------|------------------------|-------|
| decoded.telemetry.environmentMetrics.temperature         | float     | Temperature            | °C |
| decoded.telemetry.environmentMetrics.relativeHumidity   | float     | Relative humidity      | % |
| decoded.telemetry.environmentMetrics.barometricPressure | float     | Barometric pressure    | - |
| decoded.telemetry.environmentMetrics.gasResistance       | float     | Gas resistance          | - |
| decoded.telemetry.environmentMetrics.voltage            | float     | Voltage                 | - |
| decoded.telemetry.environmentMetrics.current            | float     | Current                 | - |
| decoded.telemetry.environmentMetrics.iaq                | integer   | Indoor air quality idx  | - |
| decoded.telemetry.environmentMetrics.distance           | float     | Distance                | - |
| decoded.telemetry.environmentMetrics.lux                | float     | Lux                     | - |
| decoded.telemetry.environmentMetrics.whiteLux           | float     | White lux               | - |
| decoded.telemetry.environmentMetrics.irLux              | float     | IR lux                  | - |
| decoded.telemetry.environmentMetrics.uvLux               | float     | UV lux                  | - |
| decoded.telemetry.environmentMetrics.windDirection      | integer   | Wind direction          | degrees |
| decoded.telemetry.environmentMetrics.windSpeed          | float     | Wind speed              | - |
| decoded.telemetry.environmentMetrics.weight             | float     | Weight                  | - |
| decoded.telemetry.environmentMetrics.windGust           | float     | Wind gust               | - |
| decoded.telemetry.environmentMetrics.windLull           | float     | Wind lull               | - |
| decoded.telemetry.environmentMetrics.radiation           | float     | Radiation               | - |
| decoded.telemetry.environmentMetrics.rainfall1h         | float     | Rainfall 1h              | - |
| decoded.telemetry.environmentMetrics.rainfall24h        | float     | Rainfall 24h             | - |
| decoded.telemetry.environmentMetrics.soilMoisture       | integer   | Soil moisture            | - |
| decoded.telemetry.environmentMetrics.soilTemperature    | float     | Soil temperature         | - |

#### 4. airQualityMetrics

| Field Name                                                | Data Type | Description            | Notes |
|-----------------------------------------------------------|-----------|------------------------|-------|
| decoded.telemetry.airQualityMetrics.pm10Standard           | integer   | PM10 standard          | µg/m³ |
| decoded.telemetry.airQualityMetrics.pm25Standard            | integer   | PM2.5 standard        | µg/m³ |
| decoded.telemetry.airQualityMetrics.pm100Standard           | integer   | PM100 standard         | µg/m³ |
| decoded.telemetry.airQualityMetrics.pm10Environmental       | integer   | PM10 environmental     | - |
| decoded.telemetry.airQualityMetrics.pm25Environmental      | integer   | PM2.5 environmental    | - |
| decoded.telemetry.airQualityMetrics.pm100Environmental     | integer   | PM100 environmental    | - |
| decoded.telemetry.airQualityMetrics.particles03um          | integer   | Particles 0.3µm        | - |
| decoded.telemetry.airQualityMetrics.particles05um          | integer   | Particles 0.5µm        | - |
| decoded.telemetry.airQualityMetrics.particles10um          | integer   | Particles 1.0µm        | - |
| decoded.telemetry.airQualityMetrics.particles25um          | integer   | Particles 2.5µm        | - |
| decoded.telemetry.airQualityMetrics.particles50um          | integer   | Particles 5.0µm        | - |
| decoded.telemetry.airQualityMetrics.particles100um        | integer   | Particles 10µm         | - |
| decoded.telemetry.airQualityMetrics.co2                    | integer   | CO2 ppm                 | - |
| decoded.telemetry.airQualityMetrics.co2Temperature          | float     | CO2 sensor temp        | - |
| decoded.telemetry.airQualityMetrics.co2Humidity            | float     | CO2 sensor humidity    | - |
| decoded.telemetry.airQualityMetrics.formFormaldehyde       | float     | Formaldehyde            | - |
| decoded.telemetry.airQualityMetrics.formHumidity            | float     | Form sensor humidity   | - |
| decoded.telemetry.airQualityMetrics.formTemperature        | float     | Form sensor temp       | - |
| decoded.telemetry.airQualityMetrics.pm40Standard           | integer   | PM4.0 standard         | - |
| decoded.telemetry.airQualityMetrics.particles40um          | integer   | Particles 4.0µm         | - |
| decoded.telemetry.airQualityMetrics.pmTemperature          | float     | PM sensor temp         | - |
| decoded.telemetry.airQualityMetrics.pmHumidity             | float     | PM sensor humidity     | - |
| decoded.telemetry.airQualityMetrics.pmVocIdx               | float     | VOC index               | - |
| decoded.telemetry.airQualityMetrics.pmNoxIdx               | float     | NOx index               | - |
| decoded.telemetry.airQualityMetrics.particlesTps          | float     | Particles per second    | - |

#### 5. powerMetrics

| Field Name                                    | Data Type | Description            | Notes |
|-----------------------------------------------|-----------|------------------------|-------|
| decoded.telemetry.powerMetrics.ch1Voltage     | float     | Channel 1 voltage      | - |
| decoded.telemetry.powerMetrics.ch1Current     | float     | Channel 1 current      | - |
| decoded.telemetry.powerMetrics.ch2Voltage     | float     | Channel 2 voltage      | - |
| decoded.telemetry.powerMetrics.ch2Current     | float     | Channel 2 current      | - |
| decoded.telemetry.powerMetrics.ch3Voltage     | float     | Channel 3 voltage      | - |
| decoded.telemetry.powerMetrics.ch3Current     | float     | Channel 3 current      | - |
| decoded.telemetry.powerMetrics.ch4Voltage     | float     | Channel 4 voltage      | - |
| decoded.telemetry.powerMetrics.ch4Current     | float     | Channel 4 current      | - |
| decoded.telemetry.powerMetrics.ch5Voltage     | float     | Channel 5 voltage      | - |
| decoded.telemetry.powerMetrics.ch5Current     | float     | Channel 5 current      | - |
| decoded.telemetry.powerMetrics.ch6Voltage     | float     | Channel 6 voltage      | - |
| decoded.telemetry.powerMetrics.ch6Current     | float     | Channel 6 current      | - |
| decoded.telemetry.powerMetrics.ch7Voltage     | float     | Channel 7 voltage      | - |
| decoded.telemetry.powerMetrics.ch7Current     | float     | Channel 7 current      | - |
| decoded.telemetry.powerMetrics.ch8Voltage     | float     | Channel 8 voltage      | - |
| decoded.telemetry.powerMetrics.ch8Current     | float     | Channel 8 current      | - |

#### 6. healthMetrics

| Field Name                                    | Data Type | Description            | Notes |
|-----------------------------------------------|-----------|------------------------|-------|
| decoded.telemetry.healthMetrics.heartBpm      | integer   | Heart rate             | BPM |
| decoded.telemetry.healthMetrics.spO2         | integer   | Blood oxygen           | % |
| decoded.telemetry.healthMetrics.temperature  | float     | Body temperature       | °C |

#### 7. hostMetrics

| Field Name                                    | Data Type | Description            | Notes |
|-----------------------------------------------|-----------|------------------------|-------|
| decoded.telemetry.hostMetrics.uptimeSeconds  | integer   | Host uptime            | seconds |
| decoded.telemetry.hostMetrics.freememBytes   | integer   | Free memory            | bytes |
| decoded.telemetry.hostMetrics.diskfree1Bytes | integer   | Disk 1 free            | bytes |
| decoded.telemetry.hostMetrics.diskfree2Bytes | integer   | Disk 2 free            | bytes |
| decoded.telemetry.hostMetrics.diskfree3Bytes | integer   | Disk 3 free            | bytes |
| decoded.telemetry.hostMetrics.load1          | integer   | Load average 1m         | - |
| decoded.telemetry.hostMetrics.load5          | integer   | Load average 5m         | - |
| decoded.telemetry.hostMetrics.load15         | integer   | Load average 15m        | - |
| decoded.telemetry.hostMetrics.userString     | string    | Custom user string     | - |

#### 8. trafficManagementStats

| Field Name                                              | Data Type | Description            | Notes |
|---------------------------------------------------------|-----------|------------------------|-------|
| decoded.telemetry.trafficManagementStats.packetsInspected | integer   | Packets inspected      | - |
| decoded.telemetry.trafficManagementStats.positionDedupDrops | integer | Position dedup drops   | - |
| decoded.telemetry.trafficManagementStats.nodeinfoCacheHits | integer | NodeInfo cache hits    | - |
| decoded.telemetry.trafficManagementStats.rateLimitDrops | integer   | Rate limit drops       | - |
| decoded.telemetry.trafficManagementStats.unknownPacketDrops | integer | Unknown packet drops   | - |
| decoded.telemetry.trafficManagementStats.hopExhaustedPackets | integer | Hop exhausted packets  | - |
| decoded.telemetry.trafficManagementStats.routerHopsPreserved | integer | Router hops preserved | - |

### TEXT_MESSAGE_APP

Text message packets contain communication data:

| Field Name      | Data Type | Description            | Notes                     |
|-----------------|-----------|------------------------|---------------------------|
| decoded.portnum | string    | Packet type identifier | Always "TEXT_MESSAGE_APP" |
| decoded.text    | string    | Message content        | UTF-8 encoded             |
| decoded.replyId | integer   | Reply message ID       | Optional                  |
| decoded.emoji   | integer   | Emoji indicator        | 0 or 1                    |
| publicKey       | string    | Public key             | Base64 encoded            |
| pkiEncrypted    | boolean   | Encryption status      | true/false                |
| nextHop         | integer   | Next hop node ID       | -                         |
| relayNode       | integer   | Relay node ID          | -                         |

### TRACEROUTE_APP

Traceroute packets contain routing path information:

| Field Name                       | Data Type | Description              | Notes                                      |
|----------------------------------|-----------|--------------------------|--------------------------------------------|
| decoded.portnum                  | string    | Packet type identifier   | Always "TRACEROUTE_APP"                    |
| decoded.traceroute.route         | array     | Path from source to dest | List of node IDs (integers)                |
| decoded.traceroute.routeBack     | array     | Path from dest to source | List of node IDs (integers)                |
| decoded.traceroute.snrTowards    | array     | SNR per hop (forward)    | Scaled by 4; -128 = unknown. Stored as dB. |
| decoded.traceroute.snrBack       | array     | SNR per hop (return)     | Scaled by 4; -128 = unknown. Stored as dB. |

In the response packet, `from` is the target node (responder), `to` is the source node (initiator).
SNR arrays require firmware 2.5+; older nodes report -128 for unknown hops.

### Other ports

Any `decoded.portnum` without a section above (for example `STORE_FORWARD_APP`, `ROUTING_APP`, or a port the sender could only give as an integer) is accepted and stored as a `GenericPacket`.

| Field Name              | Data Type        | Description                | Notes                                                                 |
|-------------------------|------------------|----------------------------|-----------------------------------------------------------------------|
| decoded.portnum         | string or integer | Port                       | Ints and numeric strings become the enum name; unknown numbers become `PORT_<n>` |
| decoded.*               | object           | Port payload               | Stored as JSON minus `portnum`; null for `ROUTING_APP`, null when over 4 KB |
| decoded.telemetry.*     | object           | Unknown telemetry variant  | `TELEMETRY_APP` only; the first dict-valued key other than `time` is stored as `telemetry_variant` |

`rxTime` may be omitted (protobuf3 drops zero). The API then uses its own clock and flags the observation `rx_time_estimated`.
