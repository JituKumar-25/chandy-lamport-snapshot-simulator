from datetime import datetime


class Message:
    """A message travelling on a channel. type is DATA or MARKER."""

    def __init__(self, mid, sender, receiver, content, mtype, seq):
        self.id = mid
        self.sender = sender
        self.receiver = receiver
        self.content = content
        self.type = mtype
        self.seq = seq                      # global send order (used to schedule deliveries)
        self.timestamp = datetime.now().strftime("%H:%M:%S")
        self.status = "IN_TRANSIT"          # IN_TRANSIT / DELIVERED / DISCARDED

    def label(self):
        return f"{self.id}:{self.content}"

    def to_dict(self):
        return {"id": self.id, "sender": self.sender, "receiver": self.receiver,
                "content": self.content, "type": self.type,
                "timestamp": self.timestamp, "status": self.status}
