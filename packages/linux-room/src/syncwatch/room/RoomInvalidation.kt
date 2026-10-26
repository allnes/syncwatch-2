package syncwatch.room

/** Ordered hint to fetch a snapshot; payload data is never applied as state. */
class RoomInvalidation(val epoch: String, val sequence: Long) {
    companion object {
        fun decode(bytes: ByteArray): RoomInvalidation {
            val value = RoomWire.parse(bytes)
            RoomWire.keys(value, "v", "type", "roomEpoch", "sequence", "memberId", "clientRunId", "watchGeneration", "payload")
            if (RoomWire.integer(value["v"], 1) != 1L || RoomWire.string(value["type"]) !in listOf("member.bound", "member.left", "catalog.updated", "selection.changed", "watch.started", "watch.ended", "media.missing", "call.linkChanged")) throw RoomWire.bad()
            val epoch = RoomWire.string(value["roomEpoch"]); RoomWire.id(epoch)
            RoomWire.id(RoomWire.string(value["memberId"])); RoomWire.id(RoomWire.string(value["clientRunId"]))
            RoomWire.integer(value["watchGeneration"]); RoomWire.obj(value["payload"])
            return RoomInvalidation(epoch, RoomWire.integer(value["sequence"]))
        }
    }
}
