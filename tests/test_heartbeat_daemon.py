"""
Automated Live Verification of HeartbeatDaemon & SQLite Schedule Runs.
"""

import time
import unittest
from agent.database import db
from agent.heartbeat_daemon import heartbeat_daemon


class TestHeartbeatDaemon(unittest.TestCase):
    def test_database_schedule_runs(self):
        # 1. Create a test schedule
        sched = db.create_schedule(
            name="Autonomous Unit Test Schedule",
            goal="Verify database replica lag and SLA thresholds",
            interval_minutes=30,
        )
        self.assertIsNotNone(sched["id"])
        self.assertEqual(sched["interval_minutes"], 30)

        # 2. Record a schedule run
        run_record = db.record_schedule_run(
            schedule_id=sched["id"],
            schedule_name=sched["name"],
            status="COMPLETED",
            summary="All replicas synchronized. Latency 18ms.",
            duration_ms=450,
            is_alert=False,
        )
        self.assertIsNotNone(run_record["id"])
        self.assertEqual(run_record["status"], "COMPLETED")

        # 3. Retrieve schedule runs
        runs = db.list_schedule_runs(schedule_id=sched["id"])
        self.assertGreaterEqual(len(runs), 1)
        self.assertEqual(runs[0]["id"], run_record["id"])

        # 4. Update next run timestamp
        now_ms = int(time.time() * 1000)
        next_ms = now_ms + (30 * 60 * 1000)
        db.update_schedule_next_run(sched["id"], last_run_at=now_ms, next_run_at=next_ms)

        # 5. Check due schedules
        # At next_ms - 1000, it shouldn't be due
        due_early = [s for s in db.get_due_schedules(next_ms - 1000) if s["id"] == sched["id"]]
        self.assertEqual(len(due_early), 0)

        # At next_ms + 1000, it SHOULD be due
        due_late = [s for s in db.get_due_schedules(next_ms + 1000) if s["id"] == sched["id"]]
        self.assertEqual(len(due_late), 1)

    def test_heartbeat_daemon_status(self):
        status = heartbeat_daemon.get_status()
        self.assertIn("status", status)
        self.assertIn("active_schedules_count", status)
        self.assertIn("total_runs_executed", status)


if __name__ == "__main__":
    unittest.main()
