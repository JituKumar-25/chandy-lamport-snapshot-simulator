"""Chandy-Lamport distributed snapshot engine (in-memory, deterministic).

Rules implemented:
  Initiator       : record own state, send MARKER on every outgoing channel.
  First MARKER    : record own state, mark that incoming channel EMPTY, send MARKERs
                    on all outgoing channels, start recording all other incoming channels.
  Later MARKER    : stop recording that incoming channel; recorded messages = channel state.
  DATA on a channel that is being recorded: processed normally AND added to channel state.
Snapshot is complete when every process recorded its state and every incoming channel
has received its marker.
"""
import re
from datetime import datetime
from collections import deque

from .channel import Channel
from .message import Message
from .process import Process


class SimError(Exception):
    """Raised for any invalid user operation (message is shown in the UI)."""


def _now():
    return datetime.now().strftime("%H:%M:%S")


class Simulator:
    def __init__(self):
        self.on_event = None        # callbacks used for database persistence
        self.on_snapshot = None
        self.snapshot_counter = 0
        self.auto = False
        self.clear()

    def clear(self):
        self.processes, self.channels = {}, {}
        self.messages, self.events = [], []
        self.seq = self.data_no = self.marker_no = 0
        self.snap, self.step_no = None, 0
        self.last = {"text": "Idle", "why": ""}
        self.auto = False

    # ---------------------------------------------------------------- helpers
    @property
    def snapshot_running(self):
        return bool(self.snap and self.snap["status"] == "RUNNING")

    def log(self, kind, text, why=""):
        ev = {"time": _now(), "type": kind, "description": text, "explanation": why,
              "snapshot_id": self.snap["snapshot_id"] if self.snap else None}
        self.events.append(ev)
        self.last = {"text": text, "why": why}
        if self.on_event:
            self.on_event(ev)

    def _proc(self, pid):
        if pid not in self.processes:
            raise SimError(f"Process '{pid}' does not exist.")
        return self.processes[pid]

    def _chan(self, src, dst):
        self._proc(src)
        self._proc(dst)
        if (src, dst) not in self.channels:
            raise SimError(f"No channel from {src} to {dst}. Create it first.")
        return self.channels[(src, dst)]

    def _no_snapshot_running(self):
        if self.snapshot_running:
            raise SimError("A snapshot is running. Finish or reset it first.")

    def _enqueue(self, src, dst, content, mtype):
        self.seq += 1
        if mtype == "DATA":
            self.data_no += 1
            mid = f"M{self.data_no}"
        else:
            self.marker_no += 1
            mid = f"MK{self.marker_no}"
        msg = Message(mid, src, dst, content, mtype, self.seq)
        self.channels[(src, dst)].queue.append(msg)
        self.messages.append(msg)
        return msg

    # ------------------------------------------------------- topology editing
    def add_process(self, pid, state=0):
        pid = str(pid or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_]{1,10}", pid):
            raise SimError("Process ID must be 1-10 letters, digits or underscores.")
        if pid in self.processes:
            raise SimError(f"Process '{pid}' already exists.")
        try:
            state = int(state)
        except (TypeError, ValueError):
            raise SimError("Initial state must be a whole number.")
        self._no_snapshot_running()
        self.processes[pid] = Process(pid, state)
        self.log("DATA", f"Process {pid} added with Counter = {state}")

    def remove_process(self, pid):
        self._proc(pid)
        self._no_snapshot_running()
        if any(pid in key for key in self.channels):
            raise SimError(f"{pid} still has channels. Delete them first.")
        del self.processes[pid]
        self.log("DATA", f"Process {pid} removed")

    def add_channel(self, src, dst):
        self._proc(src)
        self._proc(dst)
        if src == dst:
            raise SimError("A channel cannot connect a process to itself.")
        if (src, dst) in self.channels:
            raise SimError(f"Channel {src} \u2192 {dst} already exists.")
        self._no_snapshot_running()
        self.channels[(src, dst)] = Channel(src, dst)
        self.log("DATA", f"Channel {src} \u2192 {dst} created")

    def remove_channel(self, cid):
        key = tuple(cid.split("-", 1)) if "-" in cid else None
        if key not in self.channels:
            raise SimError(f"Channel '{cid}' does not exist.")
        self._no_snapshot_running()
        if self.channels[key].queue:
            raise SimError("Channel still has messages in transit.")
        del self.channels[key]
        self.log("DATA", f"Channel {key[0]} \u2192 {key[1]} removed")

    # ---------------------------------------------------------- data messages
    def send_data(self, src, dst, content):
        content = (content or "").strip()
        if not content:
            raise SimError("Message text cannot be empty.")
        self._chan(src, dst)
        p = self.processes[src]
        p.counter += 1               # state update rule: sending increments the counter
        p.sent += 1
        m = self._enqueue(src, dst, content, "DATA")
        self.log("DATA", f"{src} sent DATA {m.id} \"{content}\" to {dst} (Counter {src} = {p.counter})")
        return m

    # ------------------------------------------------------------ snapshot
    def start_snapshot(self, initiator):
        if not self.processes:
            raise SimError("Add at least one process first.")
        self._proc(initiator)
        if self.snapshot_running:
            raise SimError("A snapshot is already running.")
        self.snapshot_counter += 1
        for p in self.processes.values():
            p.reset_snapshot()
        self.step_no = 1
        self.snap = {"snapshot_id": f"SNAP-{self.snapshot_counter:03d}", "initiator": initiator,
                     "status": "RUNNING", "global": None,
                     "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                     "completion_time": None}
        self.log("SNAPSHOT", f"Snapshot {self.snap['snapshot_id']} initiated by {initiator}",
                 "Any process may start a snapshot. The initiator acts as if it had received a marker from itself.")
        self._record(self.processes[initiator], None)
        self._check_complete()

    def _record(self, p, first_from):
        incoming = [c.src for c in self.channels.values() if c.dst == p.pid]
        p.record_state(incoming, first_from)
        self.log("SNAPSHOT", f"{p.pid} recorded local state: Counter = {p.recorded_state}",
                 f"{p.pid} must save its state BEFORE handling any later message, so the saved state "
                 "matches the cut that the markers draw through the system.")
        if first_from:
            self.log("SNAPSHOT", f"Channel {first_from} \u2192 {p.pid} recorded as EMPTY",
                     "The marker came down this channel, so nothing sent before the marker is still in transit on it.")
        for ch in [c for c in self.channels.values() if c.src == p.pid]:
            m = self._enqueue(p.pid, ch.dst, "MARKER", "MARKER")
            self.log("MARKER", f"{p.pid} sent MARKER {m.id} to {ch.dst}",
                     "Markers go out on every outgoing channel right after recording, so receivers learn the snapshot has started.")

    def step(self):
        """Deliver exactly one message: the channel head with the smallest send order."""
        ready = [c for c in self.channels.values() if c.queue]
        if not ready:
            if self.snapshot_running:
                self.snap["status"] = "FAILED"
                self.log("ERROR", "Snapshot cannot finish: some process is unreachable by markers.",
                         "Chandy-Lamport needs every process reachable from the initiator through channels.")
                if self.on_snapshot:
                    self.on_snapshot(self.snap)
            raise SimError("Nothing to deliver: all channels are empty."
                           + (" The snapshot failed: the graph must be strongly connected." if self.snap and self.snap["status"] == "FAILED" else ""))
        ch = min(ready, key=lambda c: c.queue[0].seq)
        msg = ch.queue.popleft()
        msg.status = "DELIVERED"
        if self.snapshot_running:
            self.step_no += 1
        dst = self.processes[msg.receiver]
        if msg.type == "DATA":
            self._receive_data(dst, msg)
        else:
            self._receive_marker(dst, msg)
        self._check_complete()
        return {"id": msg.id, "type": msg.type, "source": msg.sender, "target": msg.receiver}

    def _receive_data(self, dst, msg):
        dst.counter += 1             # state update rule: receiving increments the counter
        dst.received += 1
        if dst.has_recorded and dst.recording.get(msg.sender):
            # State already recorded, marker not yet seen on this channel -> message was in transit.
            dst.channel_state[msg.sender].append(msg.label())
            self.log("DATA", f"{dst.pid} received DATA {msg.id} from {msg.sender} \u2014 recorded in channel state {msg.sender} \u2192 {dst.pid}",
                     "This message was sent before the sender recorded its state but arrived after the receiver recorded "
                     "its own. It is in transit in the snapshot, so it belongs to the channel state.")
        else:
            self.log("DATA", f"{dst.pid} received DATA {msg.id} from {msg.sender} (Counter {dst.pid} = {dst.counter})",
                     "A normal message: only the local state changes; it is not part of any channel state.")

    def _receive_marker(self, dst, msg):
        src = msg.sender
        if not dst.has_recorded:
            self.log("MARKER", f"{dst.pid} received first MARKER from {src}",
                     f"The first marker is special: {dst.pid} must record its local state now, mark the channel "
                     f"{src} \u2192 {dst.pid} as empty, forward markers, and start recording its other incoming channels.")
            self._record(dst, src)
        else:
            dst.recording[src] = False
            state = dst.channel_state.get(src, [])
            self.log("MARKER", f"{dst.pid} received MARKER from {src}; channel {src} \u2192 {dst.pid} state = [{', '.join(state)}]",
                     "A later marker ends recording on that channel. Everything recorded since the local snapshot is the channel state.")

    def _check_complete(self):
        if self.snapshot_running and all(p.is_done() for p in self.processes.values()):
            self.snap["status"] = "COMPLETED"
            self.snap["completion_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.snap["global"] = {
                "process_states": {pid: p.recorded_state for pid, p in self.processes.items()},
                "channel_states": {f"{c.src}->{c.dst}": list(self.processes[c.dst].channel_state.get(c.src, []))
                                   for c in self.channels.values()}}
            self.log("COMPLETED", f"Global snapshot {self.snap['snapshot_id']} completed",
                     "Every process recorded its state and every channel received a marker. Process states plus "
                     "in-transit messages form a consistent global state: no message is received without having been sent.")
            if self.on_snapshot:
                self.on_snapshot(self.snap)

    def reset_snapshot(self):
        for ch in self.channels.values():
            ch.queue = deque(m for m in ch.queue if m.type == "DATA")
        for m in self.messages:
            if m.type == "MARKER" and m.status == "IN_TRANSIT":
                m.status = "DISCARDED"
        for p in self.processes.values():
            p.reset_snapshot()
        self.snap, self.step_no, self.auto = None, 0, False
        self.log("DATA", "Current snapshot reset")

    # -------------------------------------------------------------- output
    def to_dict(self):
        procs = []
        for p in self.processes.values():
            status = "NOT RECORDED" if not p.has_recorded else ("COMPLETE" if p.is_done() else "RECORDING")
            procs.append({"id": p.pid, "counter": p.counter, "initial": p.initial, "sent": p.sent,
                          "received": p.received, "status": "ACTIVE", "snapshot": status,
                          "recorded_state": p.recorded_state})
        chans = []
        for c in self.channels.values():
            dst = self.processes[c.dst]
            chans.append({"id": c.id, "source": c.src, "target": c.dst,
                          "queue": [m.to_dict() for m in c.queue],
                          "recording": bool(dst.recording.get(c.src)),
                          "recorded": dst.channel_state.get(c.src)})
        return {"processes": procs, "channels": chans, "snapshot": self.snap, "auto": self.auto,
                "pending": sum(len(c.queue) for c in self.channels.values()),
                "events": self.events[-150:],
                "current_step": {"step": self.step_no, **self.last},
                "stats": {"processes": len(procs), "channels": len(chans), "messages": len(self.messages),
                          "snapshot": self.snap["status"] if self.snap else "IDLE"}}
