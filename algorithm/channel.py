from collections import deque


class Channel:
    """Directed FIFO channel src -> dst. Chandy-Lamport REQUIRES FIFO delivery."""

    def __init__(self, src, dst):
        self.src = src
        self.dst = dst
        self.queue = deque()

    @property
    def id(self):
        return f"{self.src}-{self.dst}"
