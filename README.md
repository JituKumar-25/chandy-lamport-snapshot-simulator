# Chandy–Lamport Snapshot Simulator

An interactive web simulator that runs the real **Chandy–Lamport distributed snapshot algorithm** and shows it step by step.

## Problem statement
In a distributed system there is no global clock and no shared memory, so nobody can simply "look at" the whole system. How can we record a *consistent* global state while processes keep exchanging messages?

## Objectives
- Simulate processes, directed FIFO channels, data messages and markers.
- Implement the algorithm faithfully (local states, channel states, in-transit messages).
- Let students run it one step at a time or automatically, and keep a history of snapshots.

## Features
Add/remove processes and channels, send messages, animated packets (cyan circle = data, orange diamond = marker), start a snapshot from any process, next-step and auto-run modes, live event log, snapshot panel, SQLite snapshot history, learning mode with explanations, demo data, reset options, error handling.

## Technologies
Python 3, Flask, Flask-SQLAlchemy (SQLite), HTML/CSS/JavaScript, SVG, Docker.

## Architecture
```
Browser (HTML/CSS/JS + SVG)  <--JSON-->  Flask REST API (routes/)  -->  algorithm/ (Simulator)
                                                   |
                                                   +--> SQLite via SQLAlchemy (models/)
```
- `algorithm/` – pure Python engine (no Flask), easy to test.
- `routes/` – REST API; mirrors topology/messages into SQL tables and stores finished snapshots.
- `templates/`, `static/` – dashboard and history pages.

## The algorithm
1. The **initiator** records its local state and sends a MARKER on every outgoing channel.
2. On the **first MARKER** a process records its local state, marks the channel it came from as empty, sends MARKERs on all outgoing channels and starts recording all other incoming channels.
3. A **later MARKER** on a channel stops recording it. Messages recorded in between are that channel's state (messages in transit).
4. The snapshot is complete when every process recorded its state and every incoming channel received a marker. Process states + channel states = **global snapshot**.

Channels are FIFO, which the algorithm requires. The graph must be strongly connected so markers reach every process (otherwise the snapshot is reported as failed).

## How the simulator works
Every action is one *event*. **Next step** delivers one message: the channel head with the oldest send order. Sending a message increments the sender's Counter; receiving increments the receiver's Counter. A process saves its state *before* handling a message, exactly as the algorithm requires.

## Installation and running
```
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000 (the database `database/simulator.db` is created automatically).

## Using the simulator
- **Create processes / channels / messages:** use the three forms on the left. Duplicate IDs, self-channels, duplicate channels and missing channels show an error.
- **Start snapshot:** choose an initiator, press *Start snapshot*.
- **Step-by-step:** press *Next step* and read the "Current step" banner.
- **Auto run:** *Auto run* steps every ~1 second; *Pause* stops it.
- **Global snapshot:** see the *Current snapshot* panel; it shows process states and channel states.
- **History:** the *Snapshot history* page lists saved snapshots; click one for details and events.
- **Demo:** *Load demo* loads P1–P4 with 6 channels and 4 messages in transit. Send messages during a snapshot to see in-transit recording.
- **Learning mode:** tick the box to see why each event happens.

## Tests
```
python -m unittest discover tests -v
```

## Docker
```
docker build -t chandy-lamport .
docker run -p 5000:5000 chandy-lamport
```

## Future scope
Non-FIFO channels, process failures, multiple concurrent snapshots, export of snapshots, comparison with other snapshot algorithms.
