from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class ProcessModel(db.Model):
    __tablename__ = "process"
    id = db.Column(db.Integer, primary_key=True)
    process_id = db.Column(db.String(20))
    initial_state = db.Column(db.Integer)
    current_state = db.Column(db.Integer)
    status = db.Column(db.String(20))


class ChannelModel(db.Model):
    __tablename__ = "channel"
    id = db.Column(db.Integer, primary_key=True)
    source_process = db.Column(db.String(20))
    destination_process = db.Column(db.String(20))
    status = db.Column(db.String(20))


class MessageModel(db.Model):
    __tablename__ = "message"
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.String(20))
    sender = db.Column(db.String(20))
    receiver = db.Column(db.String(20))
    content = db.Column(db.String(200))
    message_type = db.Column(db.String(10))
    timestamp = db.Column(db.String(20))
    status = db.Column(db.String(20))


class SnapshotModel(db.Model):
    __tablename__ = "snapshot"
    id = db.Column(db.Integer, primary_key=True)
    snapshot_id = db.Column(db.String(20), unique=True)
    initiator = db.Column(db.String(20))
    status = db.Column(db.String(20))
    start_time = db.Column(db.String(30))
    completion_time = db.Column(db.String(30))


class ProcessStateModel(db.Model):
    __tablename__ = "process_state"
    id = db.Column(db.Integer, primary_key=True)
    snapshot_id = db.Column(db.String(20))
    process_id = db.Column(db.String(20))
    state = db.Column(db.Integer)


class ChannelStateModel(db.Model):
    __tablename__ = "channel_state"
    id = db.Column(db.Integer, primary_key=True)
    snapshot_id = db.Column(db.String(20))
    source_process = db.Column(db.String(20))
    destination_process = db.Column(db.String(20))
    messages = db.Column(db.Text)          # JSON list of recorded messages


class EventModel(db.Model):
    __tablename__ = "event"
    id = db.Column(db.Integer, primary_key=True)
    snapshot_id = db.Column(db.String(20))  # extra column: lets history show a snapshot's events
    event_type = db.Column(db.String(20))
    description = db.Column(db.String(300))
    timestamp = db.Column(db.String(20))
