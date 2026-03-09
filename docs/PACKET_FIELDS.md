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
