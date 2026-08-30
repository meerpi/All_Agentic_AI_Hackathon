"""
Google Calendar Tool — List events, create events, and check availability.

Requires the user to have completed Google OAuth setup (credentials.json in project root).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from agent.tools.base import BaseTool
from agent.tools.google_auth import build_service

logger = logging.getLogger("taskmaster.tools.google_calendar")


class GoogleCalendarTool(BaseTool):
    name = "google_calendar"
    description = (
        "Lists upcoming events, creates new events, and checks availability on the user's Google Calendar. "
        "Actions: list_events, create_event, check_availability."
    )

    def _get_service(self):
        service = build_service("calendar", "v3")
        if not service:
            raise RuntimeError(
                "Google Calendar API not available. Ensure credentials.json is in the project root "
                "and run the server once to complete OAuth consent."
            )
        return service

    def run(
        self,
        action: str = "list_events",
        max_results: int = 10,
        time_range: Optional[str] = None,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        location: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        action = action.lower() if action else "list_events"
        # Auto-infer create_event if summary/start_time provided without list flags
        if (summary or start_time) and action == "list_events" and not kwargs.get("time_range"):
            action = "create_event"

        try:
            if action == "list_events":
                return self._list_events(max_results, time_range)
            elif action == "create_event":
                return self._create_event(summary or "Untitled Event", start_time, end_time, description, location)
            elif action == "check_availability":
                return self._check_availability(start_time, end_time)
            else:
                return {"error": f"Unknown action '{action}'. Supported: list_events, create_event, check_availability"}
        except Exception as e:
            logger.error(f"Google Calendar API operation '{action}' failed: {e}")
            return {
                "status": "FAILED",
                "error": f"Google Calendar API Error ({action}): {str(e)}. Ensure Google OAuth credentials with 'https://www.googleapis.com/auth/calendar' scope are configured.",
                "action": action,
                "summary": summary
            }

    # ---------- Private action implementations ----------

    def _list_events(self, max_results: int, time_range: Optional[str]) -> Dict[str, Any]:
        """List upcoming calendar events."""
        service = self._get_service()

        # Determine time bounds
        now = datetime.now(timezone.utc)
        if time_range == "today":
            time_min = now.replace(hour=0, minute=0, second=0, microsecond=0)
            time_max = time_min + timedelta(days=1)
        elif time_range == "week":
            time_min = now
            time_max = now + timedelta(days=7)
        else:
            time_min = now
            time_max = now + timedelta(days=30)

        events_result = service.events().list(
            calendarId="primary",
            timeMin=time_min.isoformat(),
            timeMax=time_max.isoformat(),
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = events_result.get("items", [])
        formatted = []
        for event in events:
            start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date", ""))
            end = event.get("end", {}).get("dateTime", event.get("end", {}).get("date", ""))
            formatted.append({
                "id": event.get("id", ""),
                "summary": event.get("summary", "(No title)"),
                "start": start,
                "end": end,
                "location": event.get("location", ""),
                "description": event.get("description", ""),
            })

        return {
            "action": "list_events",
            "time_range": time_range or "next_30_days",
            "count": len(formatted),
            "events": formatted,
        }

    def _parse_iso(self, time_str: Optional[str]) -> str:
        """Helper to parse clean ISO 8601 strings with timezone."""
        if not time_str:
            raise ValueError("Time string is missing.")
        
        # Clean up string
        time_str = time_str.strip()
        try:
            # Check if it parses with fromisoformat
            dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            # Fallback for simple date 'YYYY-MM-DD'
            try:
                dt = datetime.strptime(time_str[:10], "%Y-%m-%d").replace(hour=14, minute=0, tzinfo=timezone.utc)
                return dt.isoformat()
            except Exception as e:
                raise ValueError(f"Unparseable date format: {time_str}. Expected ISO 8601.") from e

    def _create_event(
        self,
        summary: str,
        start_time: Optional[str],
        end_time: Optional[str],
        description: Optional[str],
        location: Optional[str],
    ) -> Dict[str, Any]:
        """Create a new calendar event."""
        service = self._get_service()

        if not start_time:
            # Default to tomorrow at 10:00 AM UTC
            now = datetime.now(timezone.utc)
            tomorrow = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
            start_time = tomorrow.isoformat()

        clean_start = self._parse_iso(start_time)

        if not end_time:
            # Default to 45 minutes after start
            dt_start = datetime.fromisoformat(clean_start)
            clean_end = (dt_start + timedelta(minutes=45)).isoformat()
        else:
            clean_end = self._parse_iso(end_time)

        event_body = {
            "summary": summary,
            "start": {"dateTime": clean_start},
            "end": {"dateTime": clean_end},
        }
        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location

        event = service.events().insert(calendarId="primary", body=event_body).execute()

        return {
            "action": "create_event",
            "event_id": event.get("id", ""),
            "summary": summary,
            "start": clean_start,
            "end": clean_end,
            "link": event.get("htmlLink", ""),
            "status": "CREATED",
        }

    def _check_availability(self, start_time: Optional[str], end_time: Optional[str]) -> Dict[str, Any]:
        """Check if a given time slot is free on the calendar."""
        if not start_time or not end_time:
            return {"error": "Both start_time and end_time are required for check_availability (ISO format)"}

        service = self._get_service()

        # Query events in the given time window
        events_result = service.events().list(
            calendarId="primary",
            timeMin=start_time if "T" in start_time else start_time + "T00:00:00Z",
            timeMax=end_time if "T" in end_time else end_time + "T23:59:59Z",
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = events_result.get("items", [])
        conflicting = [
            {"summary": e.get("summary", "(No title)"), "start": e.get("start", {}).get("dateTime", "")}
            for e in events
        ]

        is_free = len(conflicting) == 0

        return {
            "action": "check_availability",
            "start": start_time,
            "end": end_time,
            "is_free": is_free,
            "conflicting_events_count": len(conflicting),
            "conflicting_events": conflicting,
            "recommendation": "SLOT_AVAILABLE" if is_free else "SLOT_BUSY",
        }
