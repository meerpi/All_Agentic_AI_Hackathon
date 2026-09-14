"""
Autonomous Heartbeat Daemon for Taskmaster Pro (24/7 Continuous Background Agent).

Continuously monitors operational schedules stored in SQLite, runs overdue jobs
autonomously via Strands Agents SDK, monitors microservice SLAs, and pushes
proactive Server-Sent Events (SSE) to connected clients when anomalies occur.
"""

import asyncio
import json
import logging
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional

from agent.database import db

logger = logging.getLogger("taskmaster.heartbeat")

ANOMALY_PATTERNS = [
    re.compile(r"\b(?:sla\s*(?:breach|violation|exceeded))\b", re.IGNORECASE),
    re.compile(r"\b(?:p99|latency|lag)\s*(?:>|exceeds?|above)\s*\d+", re.IGNORECASE),
    re.compile(r"\b(?:critical|degraded|outage|unhealthy|replica\s+lag)\b", re.IGNORECASE),
    re.compile(r"\b(?:error\s+rate\s*>|5xx\s+spike)\b", re.IGNORECASE),
]


class HeartbeatDaemon:
    """
    Continuous 24/7 Autonomous Operations Agent.
    Manages recurring maintenance, automated health checks, and proactive alerting.
    """

    def __init__(self, poll_interval_seconds: int = 15):
        self.poll_interval = poll_interval_seconds
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.start_time: float = 0.0
        self.total_runs: int = 0
        self.last_check_at: Optional[str] = None
        self.active_alerts: List[Dict[str, Any]] = []
        self._listeners: List[asyncio.Queue] = []

    def start(self):
        """Start the continuous background worker thread."""
        if self.is_running:
            logger.warning("HeartbeatDaemon is already active.")
            return

        self.is_running = True
        self.start_time = time.time()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="HeartbeatDaemon")
        self._thread.start()
        logger.info(f"🚀 Autonomous Heartbeat Daemon started (polling every {self.poll_interval}s).")

    def stop(self):
        """Stop the continuous background worker."""
        if not self.is_running:
            return

        self.is_running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        logger.info("🛑 Autonomous Heartbeat Daemon stopped.")

    def get_status(self) -> Dict[str, Any]:
        """Return operational health metrics for the heartbeat daemon."""
        now = time.time()
        uptime = int(now - self.start_time) if self.is_running else 0
        schedules = db.list_schedules(status="ACTIVE")

        return {
            "status": "ONLINE" if self.is_running else "OFFLINE",
            "uptime_seconds": uptime,
            "poll_interval_seconds": self.poll_interval,
            "total_runs_executed": self.total_runs,
            "active_schedules_count": len(schedules),
            "active_schedules": schedules,
            "last_check_at": self.last_check_at,
            "recent_alerts": self.active_alerts[-10:],
        }

    def _run_loop(self):
        """Background poll execution loop."""
        while not self._stop_event.is_set():
            try:
                self.check_and_execute_due_schedules()
            except Exception as e:
                logger.error(f"Error in HeartbeatDaemon poll loop: {e}", exc_info=True)

            # Sleep with periodic stop check
            for _ in range(self.poll_interval * 2):
                if self._stop_event.is_set():
                    break
                time.sleep(0.5)

    def check_and_execute_due_schedules(self) -> List[Dict[str, Any]]:
        """Query due schedules from SQLite and execute them autonomously."""
        now_ms = int(time.time() * 1000)
        self.last_check_at = datetime.now(timezone.utc).isoformat()
        due_schedules = db.get_due_schedules(now_ms)

        if not due_schedules:
            # Broadcast routine heartbeat tick
            self._broadcast_event({
                "type": "heartbeat_tick",
                "timestamp": self.last_check_at,
                "active_schedules_count": len(db.list_schedules(status="ACTIVE")),
            })
            return []

        logger.info(f"⏱️ Heartbeat Daemon detected {len(due_schedules)} due schedule(s). Running autonomous cycle...")
        results = []
        for sched in due_schedules:
            res = self.execute_schedule(sched)
            results.append(res)

        return results

    def execute_schedule(self, schedule: Dict[str, Any], is_manual: bool = False) -> Dict[str, Any]:
        """Execute a single operational schedule using Strands Agents SDK."""
        sched_id = schedule["id"]
        sched_name = schedule["name"]
        goal = schedule["goal"]
        interval_min = int(schedule.get("interval_minutes") or 60)

        logger.info(f"▶️ Executing autonomous scheduled job [{sched_id}]: '{sched_name}'...")
        start_t = time.time()

        from agent.strands_bridge import TaskmasterProAgent

        # Initialize headless professional agent
        agent = TaskmasterProAgent(
            enable_hitl=False,
            workflow_id=f"heartbeat-{sched_id}-{int(time.time())}",
        )

        res = agent.run(goal)
        duration_ms = int((time.time() - start_t) * 1000)
        status = res.get("status", "COMPLETED")
        output_text = res.get("output", "")
        summary = output_text[:280] if output_text else f"Autonomous task executed in {duration_ms}ms"

        # Anomaly / SLA breach detection
        is_alert = False
        alert_reason = ""
        for pattern in ANOMALY_PATTERNS:
            match = pattern.search(output_text)
            if match:
                is_alert = True
                alert_reason = f"Anomaly match: '{match.group(0)}'"
                break

        if status != "COMPLETED":
            is_alert = True
            alert_reason = f"Execution failed with status: {status}"

        # Update next run timestamp in SQLite
        now_ms = int(time.time() * 1000)
        next_run_ms = now_ms + (interval_min * 60 * 1000)
        db.update_schedule_next_run(sched_id, last_run_at=now_ms, next_run_at=next_run_ms, status="ACTIVE")

        # Record run history
        run_record = db.record_schedule_run(
            schedule_id=sched_id,
            schedule_name=sched_name,
            status=status if not is_alert else "ALERT",
            summary=summary,
            output=output_text,
            duration_ms=duration_ms,
            is_alert=is_alert,
        )

        self.total_runs += 1

        payload = {
            "type": "schedule_executed",
            "schedule_id": sched_id,
            "schedule_name": sched_name,
            "run_id": run_record["id"],
            "status": run_record["status"],
            "duration_ms": duration_ms,
            "summary": summary,
            "output_preview": output_text[:400],
            "is_alert": is_alert,
            "alert_reason": alert_reason,
            "next_run_at": next_run_ms,
            "is_manual": is_manual,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if is_alert:
            self.active_alerts.append(payload)
            logger.warning(f"🚨 [HEARTBEAT ALERT] Schedule '{sched_name}' flagged anomaly: {alert_reason}")
            self._broadcast_event({"type": "anomaly_alert", **payload})
        else:
            logger.info(f"✅ [HEARTBEAT SUCCESS] Schedule '{sched_name}' executed cleanly ({duration_ms}ms).")
            self._broadcast_event(payload)

        return payload

    def trigger_now(self, schedule_id: str) -> Dict[str, Any]:
        """Manually trigger an immediate execution of an operational schedule."""
        schedules = db.list_schedules()
        target = next((s for s in schedules if s["id"] == schedule_id), None)
        if not target:
            raise ValueError(f"Schedule '{schedule_id}' not found.")

        return self.execute_schedule(target, is_manual=True)

    def _broadcast_event(self, event_data: Dict[str, Any]):
        """Broadcast event to all connected SSE async queues."""
        if not self._listeners:
            return

        for q in list(self._listeners):
            try:
                q.put_nowait(event_data)
            except Exception:
                pass

    async def subscribe(self) -> AsyncGenerator[str, None]:
        """SSE generator yielding live heartbeat status ticks and alerts."""
        q = asyncio.Queue(maxsize=100)
        self._listeners.append(q)
        try:
            # Emit immediate initial status
            yield f"event: heartbeat_connected\ndata: {json.dumps(self.get_status())}\n\n"
            while True:
                data = await q.get()
                evt_type = data.get("type", "heartbeat_event")
                yield f"event: {evt_type}\ndata: {json.dumps(data)}\n\n"
        finally:
            if q in self._listeners:
                self._listeners.remove(q)


# Global singleton instance
heartbeat_daemon = HeartbeatDaemon(poll_interval_seconds=20)
