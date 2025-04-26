


## Apps

### Users

* Models: User (??), Region, Constellation, XX memberships

### Nodes

* Models: ManagedNode, ObservedNode, DeviceMetrics, NodePosition

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
    * [ ] if "from" node doesn't exist, create it


### Security

* Need individual API keys per node
* Must validate incoming node ID matches API key 

### Tests

* [ ] Add example JSON for each packet type



### TODO

- [ ] We need to support a POST /node with a Node API key auth
    - This will probably be via adding a 
- [ ] Add an auth mechanism for the frontend
- [ ] Add an auth mechanism for Postman
- [ ] Write down the logic + assumptions for the packet ingestion logic
