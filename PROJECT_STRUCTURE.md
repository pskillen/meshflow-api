


## Apps

### Users

* Models: User (??), Region, Constellation, XX memberships

### Nodes

* Models: MeshtasticNode, DeviceMetrics, NodePosition

### Messages

Stores structured messages

* Modes: TextMessage

### Packets

* Stores raw packet data
* Models:
    * RawPacket
    * 
* Provides ingestion API
    * DeviceMetricsPacket -> DeviceMetrics
    * PositionPacket -> NodePosition
    * MessagePacket -> TextMessage (+/- TextMessageReply)


