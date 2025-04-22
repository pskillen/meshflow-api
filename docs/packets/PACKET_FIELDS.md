# Meshtastic Packet Fields Documentation

This document outlines the structure of different packet types in the Meshtastic network.

## Common Fields

All packet types share these common fields:

| Field Name | Data Type | Description              | Notes                               |
|------------|-----------|--------------------------|-------------------------------------|
| from       | integer   | Sender's node ID         | Numeric identifier                  |
| to         | integer   | Recipient's node ID      | 4294967295 for broadcast            |
| channel    | integer   | Channel number           | 0-based                             |
| id         | integer   | Unique packet identifier | -                                   |
| rxTime     | integer   | Reception timestamp      | Unix timestamp                      |
| rxSnr      | float     | Signal-to-noise ratio    | -                                   |
| hopLimit   | integer   | Maximum number of hops   | -                                   |
| hopStart   | integer   | Initial hop count        | -                                   |
| fromId     | string    | Sender's node ID         | String format (e.g. "!433d4494")    |
| toId       | string    | Recipient's node ID      | String format, "^all" for broadcast |
| raw        | string    | Raw packet data          | Text format of the complete packet  |

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
| decoded.user.hwModel   | string    | Hardware model         | e.g. "HELTEC_V3"      |
| decoded.user.role      | string    | Node role              | e.g. "CLIENT_MUTE"    |
| decoded.user.publicKey | string    | Public key             | Base64 encoded        |

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
| decoded.position.groundSpeed    | integer   | Speed in m/s           | -                     |
| decoded.position.groundTrack    | integer   | Track in degrees       | 0-359                 |
| decoded.position.precisionBits  | integer   | Position precision     | -                     |
| decoded.position.latitude       | float     | Latitude (decimal)     | -                     |
| decoded.position.longitude      | float     | Longitude (decimal)    | -                     |

### TELEMETRY_APP

Telemetry packets contain device metrics:

| Field Name                                         | Data Type | Description            | Notes                  |
|----------------------------------------------------|-----------|------------------------|------------------------|
| decoded.portnum                                    | string    | Packet type identifier | Always "TELEMETRY_APP" |
| decoded.telemetry.time                             | integer   | Telemetry timestamp    | Unix timestamp         |
| decoded.telemetry.deviceMetrics.batteryLevel       | integer   | Battery level          | 0-100                  |
| decoded.telemetry.deviceMetrics.voltage            | float     | Battery voltage        | In volts               |
| decoded.telemetry.deviceMetrics.channelUtilization | float     | Channel usage          | Percentage             |
| decoded.telemetry.deviceMetrics.airUtilTx          | float     | Air utilization        | Percentage             |
| decoded.telemetry.deviceMetrics.uptimeSeconds      | integer   | Device uptime          | In seconds             |

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
