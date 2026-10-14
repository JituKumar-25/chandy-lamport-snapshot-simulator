import json
from functools import wraps

from flask import Blueprint, jsonify, request

from algorithm import Simulator, SimError
from models import (db, ProcessModel, ChannelModel, MessageModel, SnapshotModel,
                    ProcessStateModel, ChannelStateModel, EventModel)

api = Blueprint("api", __name__, url_prefix="/api")
sim = Simulator()


# ------------------------------------------------------------ persistence
def _save_event(ev):
    db.session.add(EventModel(snapshot_id=ev["snapshot_id"], event_type=ev["type"],
                              description=ev["description"], timestamp=ev["time"]))
    db.session.commit()


def _save_snapshot(snap):
    """Store a finished snapshot (states + channel states) in SQLite."""
    db.session.add(SnapshotModel(snapshot_id=snap["snapshot_id"], initiator=snap["initiator"],
                                 status=snap["status"], start_time=snap["start_time"],
                                 completion_time=snap["completion_time"]))
    g = snap.get("global") or {}
    for pid, state in g.get("process_states", {}).items():
        db.session.add(ProcessStateModel(snapshot_id=snap["snapshot_id"], process_id=pid, state=state))
    for key, msgs in g.get("channel_states", {}).items():
        s, d = key.split("->")
        db.session.add(ChannelStateModel(snapshot_id=snap["snapshot_id"], source_process=s,
                                         destination_process=d, messages=json.dumps(msgs)))
    db.session.commit()


def persist():
    """Mirror the simulator's topology and messages into the SQL tables."""
    for model in (ProcessModel, ChannelModel, MessageModel):
        model.query.delete()
    for p in sim.processes.values():
        db.session.add(ProcessModel(process_id=p.pid, initial_state=p.initial, current_state=p.counter, status="ACTIVE"))
    for c in sim.channels.values():
        db.session.add(ChannelModel(source_process=c.src, destination_process=c.dst, status="ACTIVE"))
    for m in sim.messages:
        db.session.add(MessageModel(message_id=m.id, sender=m.sender, receiver=m.receiver, content=m.content,
                                    message_type=m.type, timestamp=m.timestamp, status=m.status))
    db.session.commit()


def load_demo():
    sim.clear()
    for pid, state in (("P1", 5), ("P2", 8), ("P3", 3), ("P4", 2)):
        sim.add_process(pid, state)
    for s, d in (("P1", "P2"), ("P1", "P3"), ("P2", "P3"), ("P3", "P4"), ("P4", "P1"), ("P2", "P4")):
        sim.add_channel(s, d)
    for s, d, t in (("P1", "P2", "Hello"), ("P2", "P3", "Update"), ("P3", "P4", "Data"), ("P4", "P1", "Ack")):
        sim.send_data(s, d, t)


def init_sim():
    sim.on_event, sim.on_snapshot = _save_event, _save_snapshot
    sim.snapshot_counter = SnapshotModel.query.count()
    EventModel.query.filter_by(snapshot_id=None).delete()
    load_demo()
    persist()


# ---------------------------------------------------------------- helpers
def guarded(fn):
    @wraps(fn)
    def wrapper(*a, **k):
        try:
            return fn(*a, **k)
        except SimError as e:
            sim.auto = False
            persist()
            return jsonify(error=str(e), state=sim.to_dict()), 400
    return wrapper


def ok(**extra):
    persist()
    return jsonify(ok=True, state=sim.to_dict(), **extra)


def body():
    return request.get_json(silent=True) or {}


# --------------------------------------------------------------- processes
@api.get("/state")
def get_state():
    return jsonify(sim.to_dict())


@api.get("/processes")
def list_processes():
    return jsonify(sim.to_dict()["processes"])


@api.post("/processes")
@guarded
def add_process():
    b = body()
    sim.add_process(b.get("process_id"), b.get("initial_state", 0))
    return ok()


@api.delete("/processes/<pid>")
@guarded
def delete_process(pid):
    sim.remove_process(pid)
    return ok()


# ---------------------------------------------------------------- channels
@api.get("/channels")
def list_channels():
    return jsonify(sim.to_dict()["channels"])


@api.post("/channels")
@guarded
def add_channel():
    b = body()
    sim.add_channel(b.get("source"), b.get("destination"))
    return ok()


@api.delete("/channels/<cid>")
@guarded
def delete_channel(cid):
    sim.remove_channel(cid)
    return ok()


# ---------------------------------------------------------------- messages
@api.get("/messages")
def list_messages():
    return jsonify([m.to_dict() for m in sim.messages])


@api.post("/messages")
@guarded
def send_message():
    b = body()
    sim.send_data(b.get("sender"), b.get("receiver"), b.get("content"))
    return ok()


# --------------------------------------------------------------- snapshots
@api.post("/snapshot/start")
@guarded
def snapshot_start():
    sim.start_snapshot(body().get("initiator"))
    return ok()


@api.post("/snapshot/step")
@guarded
def snapshot_step():
    delivered = sim.step()
    return ok(delivered=delivered)


@api.post("/snapshot/auto")
def snapshot_auto():
    sim.auto = True
    return ok()


@api.post("/snapshot/pause")
def snapshot_pause():
    sim.auto = False
    return ok()


@api.post("/snapshot/reset")
def snapshot_reset():
    if body().get("full"):
        sim.clear()
        sim.log("DATA", "Entire simulation reset")
    else:
        sim.reset_snapshot()
    return ok()


@api.post("/demo")
@guarded
def demo():
    load_demo()
    return ok()


@api.get("/snapshot/current")
def snapshot_current():
    return jsonify(sim.snap)


@api.get("/snapshots")
def snapshot_history():
    rows = SnapshotModel.query.order_by(SnapshotModel.id.desc()).all()
    return jsonify([{"snapshot_id": r.snapshot_id, "initiator": r.initiator, "status": r.status,
                     "start_time": r.start_time, "completion_time": r.completion_time} for r in rows])


@api.get("/snapshots/<sid>")
def snapshot_detail(sid):
    r = SnapshotModel.query.filter_by(snapshot_id=sid).first()
    if not r:
        return jsonify(error="Snapshot not found"), 404
    return jsonify({
        "snapshot_id": r.snapshot_id, "initiator": r.initiator, "status": r.status,
        "start_time": r.start_time, "completion_time": r.completion_time,
        "process_states": {s.process_id: s.state for s in ProcessStateModel.query.filter_by(snapshot_id=sid)},
        "channel_states": {f"{c.source_process} \u2192 {c.destination_process}": json.loads(c.messages)
                           for c in ChannelStateModel.query.filter_by(snapshot_id=sid)},
        "events": [{"time": e.timestamp, "type": e.event_type, "description": e.description}
                   for e in EventModel.query.filter_by(snapshot_id=sid).order_by(EventModel.id)]})


@api.get("/events")
def events():
    return jsonify(sim.events)
