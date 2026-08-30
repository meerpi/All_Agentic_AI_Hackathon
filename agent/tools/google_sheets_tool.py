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
        rows: Optional[Any] = None,
        values: Optional[Any] = None,
        headers: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        raw_rows = rows if rows is not None else values if values is not None else kwargs.get("data")
        raw_headers = headers or kwargs.get("headers")

        action = action.lower() if action else "read_sheet"
        # Auto-infer intent if action was omitted or defaulted
        if raw_rows and spreadsheet_id and action == "read_sheet":
            action = "append_rows"
        elif title and not spreadsheet_id and action in ("read_sheet", "create_spreadsheet"):
            action = "create_spreadsheet"

        try:
            if action == "create_spreadsheet":
                return self._create_spreadsheet(
                    title=title or "Taskmaster Data",
                    rows=raw_rows,
                    headers=raw_headers,
                )
            elif action == "read_sheet":
                return self._read_sheet(spreadsheet_id or "", range_notation or f"{sheet_name}!A:Z")
            elif action == "append_rows":
                return self._append_rows(spreadsheet_id or "", range_notation or f"{sheet_name}!A:A", raw_rows or [])
            elif action == "update_cells":
                return self._update_cells(spreadsheet_id or "", range_notation or f"{sheet_name}!A1", raw_rows or [])
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

    # ---------- Helper methods ----------

    def _normalize_rows(self, raw_rows: Any, headers: Optional[List[str]] = None) -> List[List[Any]]:
        """Ensure rows is strictly a 2D list of primitive values for Google Sheets API."""
        normalized: List[List[Any]] = []

        if raw_rows:
            if isinstance(raw_rows, str):
                normalized = [[raw_rows]]
            elif isinstance(raw_rows, dict):
                normalized = [[str(k), str(v)] for k, v in raw_rows.items()]
            elif isinstance(raw_rows, list):
                if raw_rows:
                    if isinstance(raw_rows[0], dict):
                        extracted_headers = list(raw_rows[0].keys())
                        data_rows = [[str(d.get(h, "")) for h in extracted_headers] for d in raw_rows]
                        normalized = [extracted_headers] + data_rows
                    elif isinstance(raw_rows[0], (list, tuple)):
                        normalized = [[str(cell) for cell in r] for r in raw_rows]
                    else:
                        # 1D list of items -> single row
                        normalized = [[str(item) for item in raw_rows]]
            else:
                normalized = [[str(raw_rows)]]

        if headers:
            # Prepend headers if not already the first row of normalized
            header_row = [str(h) for h in headers]
            if not normalized or normalized[0] != header_row:
                normalized = [header_row] + normalized

        return normalized

    # ---------- Private action implementations ----------

    def _create_spreadsheet(
        self,
        title: str,
        rows: Optional[Any] = None,
        headers: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create a new Google Sheet and immediately populate with initial rows/headers."""
        service = self._get_service()
        spreadsheet_body = {
            "properties": {"title": title},
            "sheets": [{"properties": {"title": "Sheet1"}}],
        }
        result = service.spreadsheets().create(body=spreadsheet_body).execute()
        spreadsheet_id = result["spreadsheetId"]
        url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"

        all_rows = self._normalize_rows(rows, headers=headers)
        rows_written = 0

        if all_rows:
            try:
                write_result = service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range="Sheet1!A1",
                    valueInputOption="USER_ENTERED",
                    body={"values": all_rows}
                ).execute()
                rows_written = write_result.get("updatedRows", len(all_rows))
                logger.info(f"Successfully populated Google Sheet '{title}' with {rows_written} rows at {url}")
            except Exception as e:
                logger.error(f"Failed to write initial rows to new sheet: {e}")

        return {
            "action": "create_spreadsheet",
            "spreadsheet_id": spreadsheet_id,
            "title": title,
            "url": url,
            "rows_written": rows_written,
            "total_rows": len(all_rows),
            "status": "SUCCESS",
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
            "status": "SUCCESS",
        }

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

    def _update_cells(self, spreadsheet_id: str, range_notation: str, values: Any) -> Dict[str, Any]:
        """Update specific cells in a Google Sheet."""
        if not spreadsheet_id or spreadsheet_id.startswith("$") or len(spreadsheet_id) < 15:
            raise ValueError(f"Unresolved or invalid spreadsheet_id: '{spreadsheet_id}'. A valid Google Spreadsheet ID is required to update cells.")

        normalized_rows = self._normalize_rows(values)
        if not normalized_rows:
            raise ValueError("values (list of lists or structured rows) is required for update_cells action.")

        service = self._get_service()
        body = {"values": normalized_rows}
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
