"""
Google Sheets Tool — Create, read, write, and append data to Google Sheets.

Requires the user to have completed Google OAuth setup (credentials.json in project root).
"""

import logging
from typing import Any, Dict, List, Optional

from agent.tools.base import BaseTool
from agent.tools.google_auth import build_service

logger = logging.getLogger("taskmaster.tools.google_sheets")


class GoogleSheetsTool(BaseTool):
    name = "google_sheets"
    description = (
        "Creates, reads, and writes data to Google Sheets spreadsheets. "
        "Actions: create_spreadsheet, read_sheet, append_rows, update_cells."
    )

    def _get_service(self):
        service = build_service("sheets", "v4")
        if not service:
            raise RuntimeError(
                "Google Sheets API not available. Ensure credentials.json is in the project root "
                "and run the server once to complete OAuth consent."
            )
        return service

    def run(
        self,
        action: str = "read_sheet",
        spreadsheet_id: Optional[str] = None,
        sheet_name: str = "Sheet1",
        range_notation: Optional[str] = None,
        title: Optional[str] = None,
        rows: Optional[List[List[Any]]] = None,
        values: Optional[List[List[Any]]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        action = action.lower()

        try:
            if action == "create_spreadsheet":
                return self._create_spreadsheet(title or "Taskmaster Data")
            elif action == "read_sheet":
                return self._read_sheet(spreadsheet_id or "", range_notation or f"{sheet_name}!A:Z")
            elif action == "append_rows":
                return self._append_rows(spreadsheet_id or "", range_notation or f"{sheet_name}!A:A", rows or values or [])
            elif action == "update_cells":
                return self._update_cells(spreadsheet_id or "", range_notation or f"{sheet_name}!A1", values or [])
            else:
                return {"error": f"Unknown action '{action}'. Supported: create_spreadsheet, read_sheet, append_rows, update_cells"}
        except Exception as e:
            logger.error(f"Google Sheets API operation '{action}' failed: {e}")
            return {
                "status": "FAILED",
                "error": f"Google Sheets API Error ({action}): {str(e)}. Ensure Google OAuth credentials (token.json or ADC) with 'https://www.googleapis.com/auth/spreadsheets' scope are configured.",
                "action": action,
                "spreadsheet_id": spreadsheet_id
            }

    # ---------- Private action implementations ----------

    def _create_spreadsheet(self, title: str, headers: Optional[List[str]] = None) -> Dict[str, Any]:
        """Create a new Google Sheet and optionally populate initial header row."""
        service = self._get_service()
        spreadsheet_body = {
            "properties": {"title": title},
            "sheets": [{"properties": {"title": "Sheet1"}}],
        }
        result = service.spreadsheets().create(body=spreadsheet_body).execute()
        spreadsheet_id = result["spreadsheetId"]
        url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"

        if headers:
            try:
                service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range="Sheet1!A1",
                    valueInputOption="USER_ENTERED",
                    body={"values": [headers]}
                ).execute()
            except Exception as e:
                logger.warning(f"Failed to write header row to new sheet: {e}")

        return {
            "action": "create_spreadsheet",
            "spreadsheet_id": spreadsheet_id,
            "title": title,
            "url": url,
            "status": "CREATED",
        }

    def _read_sheet(self, spreadsheet_id: str, range_notation: str) -> Dict[str, Any]:
        """Read data from a Google Sheet range."""
        if not spreadsheet_id or spreadsheet_id.startswith("$") or len(spreadsheet_id) < 15:
            raise ValueError(f"Unresolved or invalid spreadsheet_id: '{spreadsheet_id}'. A valid Google Spreadsheet ID is required to read sheet.")

        service = self._get_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=range_notation
        ).execute()

        rows = result.get("values", [])
        return {
            "action": "read_sheet",
            "spreadsheet_id": spreadsheet_id,
            "range": range_notation,
            "row_count": len(rows),
            "data": rows,
        }

    def _normalize_rows(self, raw_rows: Any) -> List[List[Any]]:
        """Ensure rows is strictly a 2D list of primitive values for Google Sheets API."""
        if not raw_rows:
            return []

        if isinstance(raw_rows, str):
            return [[raw_rows]]

        if isinstance(raw_rows, dict):
            return [[str(k), str(v)] for k, v in raw_rows.items()]

        if isinstance(raw_rows, list):
            if not raw_rows:
                return []
            if isinstance(raw_rows[0], dict):
                # List of dicts -> extract values
                headers = list(raw_rows[0].keys())
                data_rows = [[str(d.get(h, "")) for h in headers] for d in raw_rows]
                return [headers] + data_rows
            elif isinstance(raw_rows[0], (list, tuple)):
                return [[str(cell) for cell in r] for r in raw_rows]
            else:
                # 1D list of items -> single row
                return [[str(item) for item in raw_rows]]

        return [[str(raw_rows)]]

    def _append_rows(self, spreadsheet_id: str, range_notation: str, rows: Any) -> Dict[str, Any]:
        """Append rows of data to the bottom of a Google Sheet."""
        service = self._get_service()
        normalized_rows = self._normalize_rows(rows)

        if not spreadsheet_id or spreadsheet_id.startswith("$") or len(spreadsheet_id) < 15:
            raise ValueError(f"Unresolved or invalid spreadsheet_id: '{spreadsheet_id}'. A valid Google Spreadsheet ID is required to append rows.")

        if not normalized_rows:
            return {
                "action": "append_rows",
                "spreadsheet_id": spreadsheet_id,
                "url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
                "rows_appended": 0,
                "status": "SUCCESS",
                "note": "No rows provided to append."
            }

        body = {"values": normalized_rows}
        result = service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range_notation or "Sheet1!A:A",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body,
        ).execute()

        updates = result.get("updates", {})
        return {
            "action": "append_rows",
            "spreadsheet_id": spreadsheet_id,
            "url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
            "rows_appended": updates.get("updatedRows", len(normalized_rows)),
            "updated_range": updates.get("updatedRange", ""),
            "status": "SUCCESS",
        }

    def _update_cells(self, spreadsheet_id: str, range_notation: str, values: List[List[Any]]) -> Dict[str, Any]:
        """Update specific cells in a Google Sheet."""
        if not spreadsheet_id or spreadsheet_id.startswith("$") or len(spreadsheet_id) < 15:
            raise ValueError(f"Unresolved or invalid spreadsheet_id: '{spreadsheet_id}'. A valid Google Spreadsheet ID is required to update cells.")
        if not values:
            raise ValueError("values (list of lists) is required for update_cells action.")

        service = self._get_service()
        body = {"values": values}
        result = service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_notation,
            valueInputOption="USER_ENTERED",
            body=body,
        ).execute()

        return {
            "action": "update_cells",
            "spreadsheet_id": spreadsheet_id,
            "updated_range": result.get("updatedRange", ""),
            "updated_cells": result.get("updatedCells", 0),
            "status": "SUCCESS",
        }
