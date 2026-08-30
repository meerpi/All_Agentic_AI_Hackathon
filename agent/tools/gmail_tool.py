"""
Gmail Tool — Read, search, and send emails via the Gmail API.

Requires the user to have completed Google OAuth setup (credentials.json in project root).
"""

import base64
import logging
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

from agent.tools.base import BaseTool
from agent.tools.google_auth import build_service
from googleapiclient.errors import HttpError

logger = logging.getLogger("taskmaster.tools.gmail")


class GmailTool(BaseTool):
    name = "gmail"
    description = (
        "Reads, searches, and sends emails via the user's Gmail account. "
        "Actions: read_inbox, read_email, send_email, search_emails."
    )

    def _get_service(self):
        service = build_service("gmail", "v1")
        if not service:
            raise RuntimeError(
                "Gmail API not available. Ensure credentials.json is in the project root "
                "and run the server once to complete OAuth consent."
            )
        return service

    def run(
        self,
        action: str = "read_inbox",
        max_results: int = 10,
        message_id: Optional[str] = None,
        query: Optional[str] = None,
        to: Optional[str] = None,
        subject: Optional[str] = None,
        body: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        to = to or kwargs.get("recipient")
        action = action.lower()

        try:
            if action == "read_inbox":
                return self._read_inbox(max_results)
            elif action == "read_email":
                return self._read_email(message_id or "")
            elif action == "send_email":
                if not to:
                    return {"status": "FAILED", "error": "Missing required parameter 'to' (recipient email address)."}
                return self._send_email(to, subject or "Workflow Update", body or "Task completed.")
            elif action == "search_emails":
                return self._search_emails(query or "is:unread", max_results)
            elif action == "create_draft":
                if not to:
                    return {"status": "FAILED", "error": "Missing required parameter 'to' (recipient email address)."}
                return self._create_draft(to, subject or "Draft", body or "")
            elif action == "read_thread":
                return self._read_thread(kwargs.get("thread_id") or "")
            else:
                return {"error": f"Unknown action '{action}'. Supported: read_inbox, read_email, send_email, search_emails, create_draft, read_thread"}
        except HttpError as e:
            logger.error(f"Gmail API operation '{action}' failed: {e}")
            return {
                "status": "FAILED",
                "error": f"Gmail API Error ({action}): {str(e)}",
                "action": action,
                "target_recipient": to
            }

    # ---------- Private action implementations ----------

    def _read_inbox(self, max_results: int) -> Dict[str, Any]:
        """Fetch the latest N emails from the inbox."""
        service = self._get_service()
        results = service.users().messages().list(
            userId="me", labelIds=["INBOX"], maxResults=max_results
        ).execute()

        messages = results.get("messages", [])
        if not messages:
            return {"action": "read_inbox", "count": 0, "emails": [], "note": "Inbox is empty"}

        emails = []
        for msg_meta in messages:
            msg = service.users().messages().get(
                userId="me", id=msg_meta["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"]
            ).execute()

            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            emails.append({
                "id": msg["id"],
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "snippet": msg.get("snippet", ""),
            })

        return {"action": "read_inbox", "count": len(emails), "emails": emails}

    def _read_email(self, message_id: str) -> Dict[str, Any]:
        """Read the full body of a specific email by its message ID."""
        if not message_id:
            return {"error": "message_id is required for read_email action"}

        service = self._get_service()
        msg = service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()

        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        body_text = self._extract_body(msg.get("payload", {}))

        return {
            "action": "read_email",
            "id": message_id,
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "body": body_text,
        }

    def _send_email(self, to: str, subject: str, body: str) -> Dict[str, Any]:
        """Send an email from the user's Gmail account."""
        if not to:
            return {"error": "'to' address is required for send_email action"}

        service = self._get_service()
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        sent = service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()

        return {
            "action": "send_email",
            "sent_message_id": sent.get("id", ""),
            "to": to,
            "subject": subject,
            "status": "SENT",
        }

    def _search_emails(self, query: str, max_results: int) -> Dict[str, Any]:
        """Search Gmail using a Gmail query string (e.g. 'from:boss@co.com is:unread')."""
        service = self._get_service()
        results = service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()

        messages = results.get("messages", [])
        if not messages:
            return {"action": "search_emails", "query": query, "count": 0, "emails": []}

        emails = []
        for msg_meta in messages:
            msg = service.users().messages().get(
                userId="me", id=msg_meta["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"]
            ).execute()

            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            emails.append({
                "id": msg["id"],
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "snippet": msg.get("snippet", ""),
            })

        return {"action": "search_emails", "query": query, "count": len(emails), "emails": emails}

    # ---------- Helpers ----------

    def _create_draft(self, to: str, subject: str, body: str) -> Dict[str, Any]:
        """Create a draft email."""
        if not to:
            return {"error": "'to' address is required for create_draft action"}

        service = self._get_service()
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        draft = service.users().drafts().create(
            userId="me", body={"message": {"raw": raw}}
        ).execute()

        return {
            "action": "create_draft",
            "draft_id": draft.get("id", ""),
            "to": to,
            "subject": subject,
            "status": "DRAFT_CREATED",
        }

    def _read_thread(self, thread_id: str) -> Dict[str, Any]:
        """Read all messages in a thread by its thread ID."""
        if not thread_id:
            return {"error": "thread_id is required for read_thread action"}

        service = self._get_service()
        thread = service.users().threads().get(
            userId="me", id=thread_id
        ).execute()

        messages = []
        for msg in thread.get("messages", []):
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            body_text = self._extract_body(msg.get("payload", {}))

            messages.append({
                "id": msg["id"],
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "body": body_text,
            })

        return {
            "action": "read_thread",
            "thread_id": thread_id,
            "messages": messages,
        }

    @staticmethod
    def _extract_body(payload: Dict) -> str:
        """Recursively extract plain text body from a Gmail message payload."""
        if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

        for part in payload.get("parts", []):
            text = GmailTool._extract_body(part)
            if text:
                return text

        return "(No plain text body found)"
