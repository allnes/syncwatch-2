package syncwatch.room

/** Explicit clipboard transfer. Parsing performs no network or persistence work. */
class RoomInvitation(val roomId: String, val credential: RoomSecret) {
    init { RoomWire.id(roomId) }
    fun copyText(): String = roomId + "\n" + credential.copyInvitation()
    override fun toString(): String = "[redacted invitation]"
    companion object {
        fun parse(text: String): RoomInvitation {
            if (text.toByteArray(Charsets.UTF_8).size > RoomWire.maximumBytes) throw RoomProtocolException("frameTooLarge")
            val lines = text.replace("\r\n", "\n").split('\n', limit = 3)
            if (lines.size != 2) throw RoomProtocolException("malformed")
            return RoomInvitation(lines[0], RoomSecret.fromInput(lines[1]))
        }
    }
}
