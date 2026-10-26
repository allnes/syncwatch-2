package syncwatch.room

/** The edition accepted at selection.changed, independent of later catalog revisions. */
data class RoomSelectionDefinition(val epoch: String, val sequence: Long, val watchGeneration: Long, val selection: RoomCatalogEntry?) {
    companion object {
        fun decode(bytes: ByteArray, bootstrap: RoomBootstrap): RoomSelectionDefinition {
            val value = RoomWire.parse(bytes)
            RoomWire.keys(value, "v", "roomEpoch", "sequence", "watchGeneration", "selection")
            val sequence = RoomWire.integer(value["sequence"])
            if (RoomWire.integer(value["v"], 1) != 1L || RoomWire.string(value["roomEpoch"]) != bootstrap.snapshot.epoch ||
                sequence < bootstrap.snapshot.sequence || RoomWire.integer(value["watchGeneration"]) != bootstrap.snapshot.watchGeneration) throw RoomWire.bad()
            val selection = value["selection"]?.let {
                val entry = RoomWire.obj(it); RoomWire.keys(entry, "memberId", "media")
                val member = RoomWire.string(entry["memberId"]); RoomWire.id(member)
                // The publishing member may have left since the selection was accepted.
                RoomCatalogEntry(member, RoomMedia.decode(entry["media"]))
            }
            if (selection?.media?.mediaId != bootstrap.snapshot.mediaId) throw RoomWire.bad()
            return RoomSelectionDefinition(bootstrap.snapshot.epoch, sequence, bootstrap.snapshot.watchGeneration, selection)
        }
    }
}
