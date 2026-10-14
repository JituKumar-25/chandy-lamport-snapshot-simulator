import unittest
from algorithm import Simulator, SimError


def ring(n=3):
    s = Simulator()
    for i in range(1, n + 1):
        s.add_process(f"P{i}", i * 10)
    for i in range(1, n + 1):
        s.add_channel(f"P{i}", f"P{i % n + 1}")
    return s


def run_all(s):
    while s.snapshot_running:
        s.step()


class SnapshotTests(unittest.TestCase):
    def test01_create_processes(self):
        self.assertEqual(len(ring(3).processes), 3)

    def test02_create_channels(self):
        self.assertEqual(len(ring(3).channels), 3)

    def test03_send_normal_message(self):
        s = ring(); s.send_data("P1", "P2", "Hi")
        self.assertEqual(s.processes["P1"].counter, 11)
        self.assertEqual(len(s.channels[("P1", "P2")].queue), 1)
        s.step()
        self.assertEqual(s.processes["P2"].counter, 21)

    def test04_start_snapshot(self):
        s = ring(); s.start_snapshot("P1")
        self.assertTrue(s.snapshot_running)

    def test05_initiator_records_state(self):
        s = ring(); s.start_snapshot("P1")
        self.assertEqual(s.processes["P1"].recorded_state, 10)

    def test06_marker_propagation(self):
        s = ring(); s.start_snapshot("P1")
        self.assertEqual(s.channels[("P1", "P2")].queue[0].type, "MARKER")
        s.step()
        self.assertEqual(s.channels[("P2", "P3")].queue[0].type, "MARKER")

    def test07_first_marker_behavior(self):
        s = ring(); s.start_snapshot("P1"); s.step()
        p2 = s.processes["P2"]
        self.assertEqual(p2.recorded_state, 20)
        self.assertEqual(p2.channel_state["P1"], [])
        self.assertFalse(p2.recording["P1"])

    def test08_channel_state_recording(self):
        # P3 -> P2 carries a message that was sent before P3 recorded and arrives after P2 recorded.
        s = Simulator()
        for p in ("P1", "P2", "P3"):
            s.add_process(p, 0)
        for a, b in (("P1", "P2"), ("P2", "P3"), ("P3", "P1"), ("P3", "P2")):
            s.add_channel(a, b)
        s.send_data("P3", "P2", "late")           # in transit before snapshot
        s.start_snapshot("P1")                     # markers: P1->P2 (after "late" in P3->P2? different channel)
        s.step()                                   # P3->P2 "late" is older, delivered first (P2 not recorded yet)
        run_all(s)
        self.assertEqual(s.snap["status"], "COMPLETED")
        # now a case where it is recorded:
        s2 = Simulator()
        for p in ("P1", "P2", "P3"):
            s2.add_process(p, 0)
        for a, b in (("P1", "P2"), ("P2", "P3"), ("P3", "P1"), ("P3", "P2")):
            s2.add_channel(a, b)
        s2.start_snapshot("P1")
        s2.step()                                  # P2 gets first marker, records, records P3->P2
        s2.send_data("P3", "P2", "x")              # sent by P3 before it saw a marker
        run_all(s2)
        self.assertEqual(len(s2.snap["global"]["channel_states"]["P3->P2"]), 1)

    def test09_snapshot_completion(self):
        s = ring(); s.start_snapshot("P2"); run_all(s)
        self.assertEqual(s.snap["status"], "COMPLETED")
        self.assertTrue(all(p.is_done() for p in s.processes.values()))

    def test10_final_global_state_conserves_counter_sum(self):
        s = ring(); s.send_data("P1", "P2", "a"); s.send_data("P2", "P3", "b")
        s.start_snapshot("P1"); run_all(s)
        g = s.snap["global"]
        self.assertEqual(set(g["process_states"]), {"P1", "P2", "P3"})
        self.assertEqual(g["process_states"]["P1"], 11)       # recorded before any delivery

    def test11_reset(self):
        s = ring(); s.start_snapshot("P1"); s.reset_snapshot()
        self.assertIsNone(s.snap)
        self.assertTrue(all(not c.queue for c in s.channels.values()))
        s.clear(); self.assertEqual(len(s.processes), 0)

    def test12_invalid_operations(self):
        s = ring()
        for call in (lambda: s.add_process("P1", 0), lambda: s.add_channel("P1", "P1"),
                     lambda: s.add_channel("P1", "P2"), lambda: s.send_data("P1", "P3", "x"),
                     lambda: s.send_data("P9", "P1", "x"), lambda: s.remove_process("P1"),
                     lambda: s.send_data("P1", "P2", " ")):
            with self.assertRaises(SimError):
                call()
        s.start_snapshot("P1")
        with self.assertRaises(SimError):
            s.start_snapshot("P2")


if __name__ == "__main__":
    unittest.main()
