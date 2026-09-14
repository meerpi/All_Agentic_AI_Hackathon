"""
Google Sheets Tool — Create, read, write, and format Google Sheets spreadsheets.

Requires the user to have completed Google OAuth setup (credentials.json in project root).
Provides professional styling: bold frozen headers, auto-resized column widths, and cell alignment.
"""

import ast
import json
import logging
from typing import Any, Dict, List, Optional

from agent.tools.base import BaseTool
from agent.tools.google_auth import build_service

logger = logging.getLogger("taskmaster.tools.google_sheets")


class GoogleSheetsTool(BaseTool):
    name = "google_sheets"
    description = (
        "Creates, reads, writes, edits, and formats Google Sheets spreadsheets. "
        "Supports professional table styling: bold frozen headers, auto-resized column widths, and clean alignment. "
        "Actions: create_spreadsheet, read_sheet, append_rows, update_cells, overwrite_sheet, format_sheet."
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
        headers: Optional[Any] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        raw_rows = rows if rows is not None else values if values is not None else kwargs.get("data")
        raw_headers = headers or kwargs.get("headers")

        action = (action or "read_sheet").lower().strip()
        # Auto-infer intent if action was omitted or defaulted
        if raw_rows and spreadsheet_id and action in ("read_sheet", "append"):
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
            elif action in ("read_sheet", "read_range", "get_sheet", "read", "get_spreadsheet"):
                return self._read_sheet(spreadsheet_id or "", range_notation or f"{sheet_name}!A:Z")
            elif action in ("append_rows", "append_row", "append", "add_row", "add_rows"):
                return self._append_rows(spreadsheet_id or "", range_notation or f"{sheet_name}!A:A", raw_rows or [])
            elif action in ("update_cells", "edit_cells"):
                return self._update_cells(spreadsheet_id or "", range_notation or f"{sheet_name}!A1", raw_rows or [])
            elif action in ("overwrite_sheet", "set_sheet", "replace_sheet"):
                return self._overwrite_sheet(
                    spreadsheet_id=spreadsheet_id or "",
                    rows=raw_rows,
                    headers=raw_headers,
                    sheet_name=sheet_name,
                )
            elif action in ("format_sheet", "style_sheet", "auto_format"):
                return self._format_sheet(spreadsheet_id=spreadsheet_id or "", sheet_name=sheet_name)
            else:
                return {
                    "error": f"Unknown action '{action}'. Supported: create_spreadsheet, read_sheet, append_rows, update_cells, overwrite_sheet, format_sheet"
                }
        except Exception as e:
            logger.error(f"Google Sheets API operation '{action}' failed: {e}", exc_info=True)
            return {
                "status": "FAILED",
                "error": f"Google Sheets API Error ({action}): {str(e)}",
                "action": action,
                "spreadsheet_id": spreadsheet_id,
            }

    # ---------- Normalization and Type Parsing ----------

    def _parse_raw_input(self, val: Any) -> Any:
        """Parse stringified lists or JSON structures into native Python objects."""
        if not isinstance(val, str):
            return val
        s = val.strip()
        if (s.startswith("[") and s.endswith("]")) or (s.startswith("{") and s.endswith("}")):
            try:
                return ast.literal_eval(s)
            except Exception:
                try:
                    return json.loads(s)
                except Exception:
                    pass
        return val

    def _normalize_rows(self, raw_rows: Any, headers: Optional[Any] = None) -> List[List[Any]]:
        """Ensure rows is strictly a 2D list of primitive cell values for Google Sheets API."""
        raw_rows = self._parse_raw_input(raw_rows)
        if headers is not None:
            headers = self._parse_raw_input(headers)

        normalized: List[List[Any]] = []

        if raw_rows:
            if isinstance(raw_rows, dict):
                normalized = [[str(k), str(v)] for k, v in raw_rows.items()]
            elif isinstance(raw_rows, (list, tuple)):
                for item in raw_rows:
                    item_parsed = self._parse_raw_input(item)
                    if isinstance(item_parsed, dict):
                        normalized.append([str(v) for v in item_parsed.values()])
                    elif isinstance(item_parsed, (list, tuple)):
                        normalized.append([str(c) if not isinstance(c, (int, float)) else c for c in item_parsed])
                    else:
                        normalized.append([str(item_parsed)])
            elif isinstance(raw_rows, str):
                # Handle CSV or multiline text
                lines = [line.strip() for line in raw_rows.splitlines() if line.strip()]
                if lines:
                    normalized = [[cell.strip() for cell in line.split(",")] for line in lines]
                else:
                    normalized = [[raw_rows]]
            else:
                normalized = [[raw_rows]]

        # Prepend headers if provided
        if headers:
            header_row: List[str] = []
            if isinstance(headers, (list, tuple)):
                header_row = [str(h) for h in headers]
            elif isinstance(headers, str):
                header_row = [h.strip() for h in headers.split(",")]
            else:
                header_row = [str(headers)]

            if not normalized or [str(c) for c in normalized[0]] != header_row:
                normalized = [header_row] + normalized

        return normalized

    # ---------- Professional Formatting Helper ----------

    def _apply_styling(
        self,
        service: Any,
        spreadsheet_id: str,
        row_count: int,
        col_count: int,
        sheet_name: str = "Sheet1",
    ) -> bool:
        """Apply modern styling: frozen header, dark slate header with white text, centered data, and auto-resized columns."""
        try:
            meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            sheets = meta.get("sheets", [])
            target_sheet = next((s for s in sheets if s.get("properties", {}).get("title") == sheet_name), None)
            if not target_sheet and sheets:
                target_sheet = sheets[0]

            if not target_sheet:
                return False

            tab_id = target_sheet["properties"]["sheetId"]
            safe_cols = max(col_count, 1)
            safe_rows = max(row_count, 1)

            requests = [
                # 1. Freeze row 1
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": tab_id,
                            "gridProperties": {"frozenRowCount": 1},
                        },
                        "fields": "gridProperties.frozenRowCount",
                    }
                },
                # 2. Header format: Dark slate navy (#1E293B) with bold white text
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": tab_id,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": safe_cols,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {"red": 0.12, "green": 0.16, "blue": 0.23},
                                "textFormat": {
                                    "bold": True,
                                    "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                                    "fontSize": 11,
                                },
                                "horizontalAlignment": "CENTER",
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
                    }
                },
                # 3. Center align numerical / status columns (columns 1..safe_cols)
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": tab_id,
                            "startRowIndex": 1,
                            "endRowIndex": safe_rows,
                            "startColumnIndex": 1,
                            "endColumnIndex": safe_cols,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "horizontalAlignment": "CENTER",
                            }
                        },
                        "fields": "userEnteredFormat.horizontalAlignment",
                    }
                },
                # 4. Auto-resize all active columns so no text is truncated
                {
                    "autoResizeDimensions": {
                        "dimensions": {
                            "sheetId": tab_id,
                            "dimension": "COLUMNS",
                            "startIndex": 0,
                            "endIndex": safe_cols,
                        }
                    }
                },
            ]

            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body={"requests": requests}
            ).execute()
            logger.info(f"Successfully applied professional styling to Google Sheet '{spreadsheet_id}'")
            return True
        except Exception as e:
            logger.warning(f"Could not apply sheet styling to '{spreadsheet_id}': {e}")
            return False

    # ---------- Private action implementations ----------

    def _create_spreadsheet(
        self,
        title: str,
        rows: Optional[Any] = None,
        headers: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Create a new Google Sheet, populate rows, and apply professional styling."""
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
                    body={"values": all_rows},
                ).execute()
                rows_written = write_result.get("updatedRows", len(all_rows))
                col_count = max(len(r) for r in all_rows) if all_rows else 1

                # Apply styling: auto-resize, frozen header, bold colors
                self._apply_styling(service, spreadsheet_id, row_count=len(all_rows), col_count=col_count)
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

    def _overwrite_sheet(
        self,
        spreadsheet_id: str,
        rows: Optional[Any] = None,
        headers: Optional[Any] = None,
        sheet_name: str = "Sheet1",
    ) -> Dict[str, Any]:
        """Clear existing sheet and write clean, professionally formatted rows."""
        if not spreadsheet_id or len(spreadsheet_id) < 15:
            raise ValueError(f"Invalid spreadsheet_id: '{spreadsheet_id}'")

        service = self._get_service()
        all_rows = self._normalize_rows(rows, headers=headers)
        if not all_rows:
            raise ValueError("No valid rows provided to write.")

        # Clear old cells
        service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id, range=f"{sheet_name}!A1:Z500"
        ).execute()

        # Update cells
        write_result = service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": all_rows},
        ).execute()

        col_count = max(len(r) for r in all_rows) if all_rows else 1
        self._apply_styling(service, spreadsheet_id, row_count=len(all_rows), col_count=col_count, sheet_name=sheet_name)

        return {
            "action": "overwrite_sheet",
            "spreadsheet_id": spreadsheet_id,
            "url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
            "rows_written": write_result.get("updatedRows", len(all_rows)),
            "status": "SUCCESS",
        }

    def _format_sheet(self, spreadsheet_id: str, sheet_name: str = "Sheet1") -> Dict[str, Any]:
        """Apply professional styling to an existing sheet."""
        if not spreadsheet_id or len(spreadsheet_id) < 15:
            raise ValueError(f"Invalid spreadsheet_id: '{spreadsheet_id}'")

        service = self._get_service()
        read_res = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=f"{sheet_name}!A1:Z100"
        ).execute()
        existing_rows = read_res.get("values", [])
        row_count = len(existing_rows) or 1
        col_count = max(len(r) for r in existing_rows) if existing_rows else 1

        styled = self._apply_styling(service, spreadsheet_id, row_count=row_count, col_count=col_count, sheet_name=sheet_name)
        return {
            "action": "format_sheet",
            "spreadsheet_id": spreadsheet_id,
            "url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
            "status": "SUCCESS" if styled else "FAILED",
        }

    def _read_sheet(self, spreadsheet_id: str, range_notation: str) -> Dict[str, Any]:
        """Read data from a Google Sheet range."""
        if not spreadsheet_id or len(spreadsheet_id) < 15:
            raise ValueError(f"Invalid spreadsheet_id: '{spreadsheet_id}'")

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

        if not spreadsheet_id or len(spreadsheet_id) < 15:
            raise ValueError(f"Invalid spreadsheet_id: '{spreadsheet_id}'")

        if not normalized_rows:
            return {
                "action": "append_rows",
                "spreadsheet_id": spreadsheet_id,
                "url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
                "rows_appended": 0,
                "status": "SUCCESS",
                "note": "No rows provided to append.",
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
        if not spreadsheet_id or len(spreadsheet_id) < 15:
            raise ValueError(f"Invalid spreadsheet_id: '{spreadsheet_id}'")

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
