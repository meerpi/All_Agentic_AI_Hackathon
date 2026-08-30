"""
Google Docs Tool — Create, read, and write content to Google Docs documents.

Uses Google Docs API v1 (via OAuth or ADC) to create documents and insert content.
"""

import os
import logging
from typing import Any, Dict, Optional

from agent.tools.base import BaseTool
from agent.tools.google_auth import build_service

logger = logging.getLogger("taskmaster.tools.google_docs")


class GoogleDocsTool(BaseTool):
    name = "google_docs"
    description = (
        "Creates, reads, and writes essays, reports, and content to Google Docs documents. "
        "Actions: create_document, append_content, read_document."
    )

    def _get_service(self):
        service = build_service("docs", "v1")
        if not service:
            raise RuntimeError(
                "Google Docs API not available. Ensure Google credentials are configured."
            )
        return service

    def run(
        self,
        action: str = "create_document",
        title: Optional[str] = None,
        content: Optional[str] = None,
        text: Optional[str] = None,
        document_id: Optional[str] = None,
        style: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        body_content = (
            content
            if content is not None
            else text
            if text is not None
            else kwargs.get("body")
            if kwargs.get("body") is not None
            else kwargs.get("markdown_content")
            if kwargs.get("markdown_content") is not None
            else kwargs.get("data")
            if kwargs.get("data") is not None
            else ""
        )
        if isinstance(body_content, (dict, list)):
            import json
            body_content = json.dumps(body_content, indent=2)
        # Auto-infer intent if action was omitted or defaulted
        if document_id and body_content and action == "create_document":
            action = "append_content"
        elif document_id and not body_content and action == "create_document":
            action = "read_document"

        try:
            if action == "create_document":
                return self._create_document(title or "Taskmaster Document", body_content, style)
            elif action == "append_content":
                return self._append_content(document_id or "", body_content, style)
            elif action == "read_document":
                return self._read_document(document_id or "")
            else:
                return {"error": f"Unknown action '{action}'. Supported: create_document, append_content, read_document"}
        except Exception as e:
            logger.error(f"Google Docs API operation '{action}' failed: {e}")
            return {
                "status": "FAILED",
                "error": f"Google Docs API Error ({action}): {str(e)}. Ensure Google OAuth credentials (token.json or ADC) with 'https://www.googleapis.com/auth/documents' scope are configured.",
                "action": action,
                "title": title
            }

    # ---------- Private action implementations ----------

    def _create_document(self, title: str, content: str, style: Optional[str] = None) -> Dict[str, Any]:
        """Create a new Google Doc and insert the formatted text content."""
        try:
            service = self._get_service()
            doc_body = {"title": title}
            created_doc = service.documents().create(body=doc_body).execute()
            doc_id = created_doc.get("documentId")

            if content:
                requests = [
                    {
                        "insertText": {
                            "location": {"index": 1},
                            "text": content + "\n"
                        }
                    }
                ]
                if style and style.startswith("HEADING_"):
                    requests.append({
                        "updateParagraphStyle": {
                            "range": {
                                "startIndex": 1,
                                "endIndex": len(content) + 1
                            },
                            "paragraphStyle": {
                                "namedStyleType": style
                            },
                            "fields": "namedStyleType"
                        }
                    })
                service.documents().batchUpdate(
                    documentId=doc_id,
                    body={"requests": requests}
                ).execute()

            doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
            logger.info(f"Successfully created Google Doc '{title}' at {doc_url}")

            return {
                "action": "create_document",
                "document_id": doc_id,
                "title": title,
                "url": doc_url,
                "word_count": len(content.split()) if content else 0,
                "status": "SUCCESS",
                "preview": content[:200] + ("..." if len(content) > 200 else "")
            }
        except Exception as e:
            logger.error(f"Google Docs API creation failed: {e}")
            return {
                "action": "create_document",
                "title": title,
                "status": "FAILED",
                "error": f"Google Docs API Error: {str(e)}. Ensure credentials.json is configured with https://www.googleapis.com/auth/documents scope."
            }

    def _append_content(self, document_id: str, content: str, style: Optional[str] = None) -> Dict[str, Any]:
        """Append text to an existing Google Doc."""
        if not document_id or document_id.startswith("$"):
            return {
                "status": "FAILED",
                "error": f"Invalid or missing document_id: '{document_id}'. A valid Google Doc ID is required."
            }

        try:
            service = self._get_service()
            doc = service.documents().get(documentId=document_id).execute()
            content_items = doc.get("body", {}).get("content", [])
            end_index = content_items[-1].get("endIndex", 1) - 1 if content_items else 1
            start_idx = max(1, end_index)
            text_to_insert = "\n" + content if start_idx > 1 else content

            requests = [
                {
                    "insertText": {
                        "location": {"index": start_idx},
                        "text": text_to_insert + "\n"
                    }
                }
            ]
            if style and style.startswith("HEADING_"):
                requests.append({
                    "updateParagraphStyle": {
                        "range": {
                            "startIndex": start_idx,
                            "endIndex": start_idx + len(text_to_insert) + 1
                        },
                        "paragraphStyle": {
                            "namedStyleType": style
                        },
                        "fields": "namedStyleType"
                    }
                })
            service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": requests}
            ).execute()

            return {
                "action": "append_content",
                "document_id": document_id,
                "status": "SUCCESS",
                "appended_chars": len(content)
            }
        except Exception as e:
            logger.error(f"Google Docs append failed: {e}")
            return {
                "status": "FAILED",
                "error": f"Google Docs Append Error: {str(e)}"
            }

    def _read_document(self, document_id: str) -> Dict[str, Any]:
        """Read plain text from a Google Doc."""
        if not document_id or document_id.startswith("$"):
            return {
                "status": "FAILED",
                "error": f"Invalid or missing document_id: '{document_id}'. A valid Google Doc ID is required."
            }

        try:
            service = self._get_service()
            doc = service.documents().get(documentId=document_id).execute()
            title = doc.get("title", "Untitled")

            text_pieces = []
            for item in doc.get("body", {}).get("content", []):
                if "paragraph" in item:
                    for elem in item.get("paragraph", {}).get("elements", []):
                        if "textRun" in elem:
                            text_pieces.append(elem.get("textRun", {}).get("content", ""))

            full_text = "".join(text_pieces)
            return {
                "action": "read_document",
                "document_id": document_id,
                "title": title,
                "char_count": len(full_text),
                "content": full_text
            }
        except Exception as e:
            logger.error(f"Google Docs read failed: {e}")
            return {
                "status": "FAILED",
                "error": f"Google Docs Read Error: {str(e)}"
            }
