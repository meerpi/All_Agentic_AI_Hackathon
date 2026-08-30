"""
Slack Communication Tool — Autonomous Channel Announcements & Block Kit Summaries.

Supports:
1. Live Slack Incoming Webhooks / Bot API (if SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN is set).
2. Autonomous Notification Fallback (formats Block Kit cards and broadcasts to active channels / dashboard).
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error

from agent.tools.base import BaseTool

logger = logging.getLogger("taskmaster.tools.slack")


class SlackTool(BaseTool):
    name = "slack"
    description = (
        "Posts meeting executive summaries, task matrices, and engineering alerts to Slack channels. "
        "Actions: post_message, post_summary, post_block_card."
    )

    def run(
        self,
        action: str = "post_message",
        channel: str = "#product-updates",
        message: Optional[str] = None,
        text: Optional[str] = None,
        title: Optional[str] = None,
        blocks: Optional[List[Dict[str, Any]]] = None,
        fields: Optional[Dict[str, Any]] = None,
        jira_keys: Optional[List[str]] = None,
        doc_url: Optional[str] = None,
        limit: int = 100,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        action = action.lower()
        msg_body = message or text or ""

        if action == "post_message":
            return self._post_message(channel, msg_body)
        elif action in ("post_summary", "post_block_card"):
            return self._post_summary(
                channel=channel,
                title=title or "📊 Executive Sprint & Product Update",
                summary_text=msg_body,
                jira_keys=jira_keys or [],
                doc_url=doc_url or "",
                fields=fields or {}
            )
        elif action == "get_history":
            return self._get_history(channel, limit)
        else:
            return {"error": f"Unknown action '{action}'. Supported: post_message, post_summary, post_block_card, get_history"}

    def _get_history(self, channel: str, limit: int) -> Dict[str, Any]:
        """Retrieve message history for a channel using Slack Web API."""
        bot_token = os.getenv("SLACK_BOT_TOKEN")
        if not bot_token:
            return {"error": "SLACK_BOT_TOKEN is required for get_history"}

        try:
            url = f"https://slack.com/api/conversations.history?channel={channel}&limit={limit}"
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {bot_token}"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
                if not data.get("ok"):
                    return {"error": f"Slack API error: {data.get('error')}"}
                return {
                    "action": "get_history",
                    "channel": channel,
                    "messages": data.get("messages", [])
                }
        except Exception as e:
            return {"error": f"Slack API request failed: {str(e)}"}

    def _post_message(self, channel: str, message: str) -> Dict[str, Any]:
        """Post a text message to a Slack channel via webhook or broadcast."""
        webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        bot_token = os.getenv("SLACK_BOT_TOKEN")

        if webhook_url:
            try:
                payload = {"channel": channel, "text": message}
                req = urllib.request.Request(
                    webhook_url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=10) as response:
                    return {
                        "action": "post_message",
                        "channel": channel,
                        "status": "DELIVERED_TO_SLACK",
                        "status_code": response.getcode()
                    }
            except Exception as e:
                logger.error(f"Slack webhook post failed: {e}")
                return {
                    "action": "post_message",
                    "channel": channel,
                    "status": "FAILED",
                    "error": f"Slack webhook delivery failed: {str(e)}"
                }
        elif bot_token:
            try:
                payload = {"channel": channel, "text": message}
                req = urllib.request.Request(
                    "https://slack.com/api/chat.postMessage",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json; charset=utf-8",
                        "Authorization": f"Bearer {bot_token}"
                    }
                )
                with urllib.request.urlopen(req, timeout=10) as response:
                    resp_body = response.read().decode("utf-8")
                    resp_data = json.loads(resp_body)
                    if not resp_data.get("ok", False):
                        slack_error = resp_data.get("error", "unknown_error")
                        logger.error(f"Slack API returned ok=false: {slack_error}")
                        return {
                            "action": "post_message",
                            "channel": channel,
                            "status": "FAILED",
                            "error": f"Slack API error: {slack_error}"
                        }
                    return {
                        "action": "post_message",
                        "channel": channel,
                        "status": "DELIVERED_TO_SLACK",
                        "status_code": response.getcode()
                    }
            except Exception as e:
                logger.error(f"Slack bot API post failed: {e}")
                return {
                    "action": "post_message",
                    "channel": channel,
                    "status": "FAILED",
                    "error": f"Slack bot API delivery failed: {str(e)}"
                }

        logger.info(f"SLACK_WEBHOOK_URL and SLACK_BOT_TOKEN not configured. Message logged locally for channel {channel}: {message[:120]}...")
        return {
            "action": "post_message",
            "channel": channel,
            "message_snippet": message[:200] + "...",
            "status": "LOCAL_LOGGED",
            "warning": "SLACK_WEBHOOK_URL and SLACK_BOT_TOKEN are not set in environment. Message was logged locally instead of being delivered to Slack.",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def _post_summary(
        self,
        channel: str,
        title: str,
        summary_text: str,
        jira_keys: List[str],
        doc_url: str,
        fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate and post an interactive Slack Block Kit Card with Jira & Doc references."""
        webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        bot_token = os.getenv("SLACK_BOT_TOKEN")

        # Construct Slack Block Kit Payload
        block_elements = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": title[:150], "emoji": True}
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": summary_text}
            }
        ]

        if jira_keys:
            jira_str = " • ".join([f"`{k}`" for k in jira_keys])
            block_elements.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*📋 Created Jira Tasks:* {jira_str}"}
            })

        if doc_url:
            block_elements.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*📄 Full Meeting Minutes:* <{doc_url}|Open Google Doc>"}
            })

        payload = {
            "channel": channel,
            "text": f"{title}: {summary_text[:100]}",
            "blocks": block_elements
        }

        if webhook_url:
            try:
                req = urllib.request.Request(
                    webhook_url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=10) as response:
                    return {
                        "action": "post_summary",
                        "channel": channel,
                        "title": title,
                        "status": "DELIVERED_TO_SLACK",
                        "status_code": response.getcode()
                    }
            except Exception as e:
                logger.error(f"Slack Block Kit post failed via webhook: {e}")
                return {
                    "action": "post_summary",
                    "channel": channel,
                    "title": title,
                    "status": "FAILED",
                    "error": f"Slack Block Kit webhook post failed: {str(e)}"
                }
        elif bot_token:
            try:
                req = urllib.request.Request(
                    "https://slack.com/api/chat.postMessage",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json; charset=utf-8",
                        "Authorization": f"Bearer {bot_token}"
                    }
                )
                with urllib.request.urlopen(req, timeout=10) as response:
                    resp_body = response.read().decode("utf-8")
                    resp_data = json.loads(resp_body)
                    if not resp_data.get("ok", False):
                        slack_error = resp_data.get("error", "unknown_error")
                        logger.error(f"Slack API returned ok=false for post_summary: {slack_error}")
                        return {
                            "action": "post_summary",
                            "channel": channel,
                            "title": title,
                            "status": "FAILED",
                            "error": f"Slack API error: {slack_error}"
                        }
                    return {
                        "action": "post_summary",
                        "channel": channel,
                        "title": title,
                        "status": "DELIVERED_TO_SLACK",
                        "status_code": response.getcode()
                    }
            except Exception as e:
                logger.error(f"Slack Block Kit post failed via bot token: {e}")
                return {
                    "action": "post_summary",
                    "channel": channel,
                    "title": title,
                    "status": "FAILED",
                    "error": f"Slack Block Kit bot API post failed: {str(e)}"
                }

        logger.info(f"SLACK_WEBHOOK_URL and SLACK_BOT_TOKEN not configured. Broadcast logged locally for {channel}: {title}")
        return {
            "action": "post_summary",
            "channel": channel,
            "title": title,
            "jira_keys_referenced": jira_keys,
            "doc_url_referenced": doc_url,
            "status": "LOCAL_LOGGED",
            "warning": "SLACK_WEBHOOK_URL and SLACK_BOT_TOKEN are not set in environment. Summary card was logged locally instead of being delivered to Slack.",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
