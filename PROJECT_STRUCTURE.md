


## Apps

### Users

* Provides User (??), Region

### Nodes

* Models: MeshtasticNode, DeviceMetrics, 

### Messages

Stores structured messages

### Packets

* Stores raw packet data
* Models:
    * RawPacket
    * 
* Provides ingestion API
    * DeviceMetricsPacket -> DeviceMetrics
    * PositionPacket -> NodePosition
    * MessagePacket -> TextMessage (+/- TextMessageReply)


