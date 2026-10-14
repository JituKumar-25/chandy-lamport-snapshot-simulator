class Process:
    """One distributed process with its local state (a counter) and snapshot bookkeeping."""

    def __init__(self, pid, initial=0):
        self.pid = pid
        self.initial = initial
        self.counter = initial       # the local state
        self.sent = 0
        self.received = 0
        self.reset_snapshot()

    def reset_snapshot(self):
        self.recorded_state = None   # local state saved for the snapshot
        self.recording = {}          # incoming source -> True while recording that channel
        self.channel_state = {}      # incoming source -> list of in-transit messages

    @property
    def has_recorded(self):
        return self.recorded_state is not None

    def record_state(self, incoming_sources, first_marker_from=None):
        """Save local state. The channel the first marker arrived on is recorded EMPTY
        and stops recording; every other incoming channel starts recording."""
        self.recorded_state = self.counter
        for src in incoming_sources:
            self.channel_state[src] = []
            self.recording[src] = (src != first_marker_from)

    def is_done(self):
        """Done = local state recorded AND a marker arrived on every incoming channel."""
        return self.has_recorded and not any(self.recording.values())
