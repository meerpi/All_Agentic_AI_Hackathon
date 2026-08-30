import csv
import io
import json
import logging
import re
from typing import Any, Dict, List, Optional
from agent.tools.base import BaseTool

logger = logging.getLogger("taskmaster.tools.data_extractor")


class DataExtractorTool(BaseTool):
    name = "data_extractor"
    description = (
        "Extracts structured data from unstructured text, HTML, ARIA snapshots, logs, CSV, or any raw content. "
        "Supports natural language extraction queries (e.g. 'Extract the top 5 headlines as a list'). "
        "Pass 'extraction_query' to describe what to extract."
    )

    def run(
        self,
        source_type: str = "text_payload",
        raw_content: Optional[str] = None,
        fields_to_extract: Optional[List[str]] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        raw_input = (
            raw_content
            or kwargs.get("content")
            or kwargs.get("source_data")
            or kwargs.get("input_data")
            or kwargs.get("input")
            or kwargs.get("data")
            or kwargs.get("text")
            or kwargs.get("source_content")
            or kwargs.get("extracted_content")
            or kwargs.get("page_content")
            or kwargs.get("html")
            or kwargs.get("observation")
            or ""
        )
        if isinstance(raw_input, (dict, list)):
            content = json.dumps(raw_input)
        else:
            content = str(raw_input or "")

        fields = fields_to_extract or kwargs.get("schema") or ["status", "metric", "timestamp", "severity"]
        if isinstance(fields, dict):
            fields = list(fields.keys())

        extraction_query = kwargs.get("extraction_query") or kwargs.get("query") or kwargs.get("prompt") or ""

        if not content.strip():
            return {
                "status": "FAILED",
                "error": "No input content provided for extraction. The source data was empty or not passed correctly.",
                "source_type": source_type,
                "processed_records_count": 0,
                "extracted_fields": {f: None for f in fields},
                "records": [],
                "raw_snippet": "No raw input provided"
            }

        # ── LLM-powered extraction when a natural language query is provided ──
        if extraction_query and len(content) > 20:
            return self._llm_extract(content, extraction_query, source_type)

        # ── Fallback: structural parsing (JSON / CSV / regex) ──
        return self._structural_extract(content, fields, source_type)

    def _llm_extract(self, content: str, query: str, source_type: str) -> Dict[str, Any]:
        """Use LLM to extract structured data based on a natural language query."""
        try:
            from agent.llm_client import GeminiClient
            _llm = GeminiClient()

            # Truncate content to avoid token overflow
            truncated = content[:6000] if len(content) > 6000 else content

            prompt = (
                "You are a precise data extraction assistant. Extract the requested information from the provided content.\n\n"
                f"EXTRACTION REQUEST: {query}\n\n"
                f"SOURCE CONTENT:\n{truncated}\n\n"
                "INSTRUCTIONS:\n"
                "- Extract ONLY what is requested, nothing extra\n"
                "- Return a valid JSON object with these keys:\n"
                '  - "items": a list of the extracted items (strings or objects)\n'
                '  - "count": the number of items extracted\n'
                '  - "summary": a one-line summary of what was extracted\n'
                '- If you cannot find the requested information, return {"items": [], "count": 0, "summary": "No matching data found"}\n'
                "- Do NOT add commentary outside the JSON\n\n"
                "Return ONLY the JSON object:"
            )

            result = _llm.generate_json(prompt, role="research")

            if isinstance(result, dict):
                items = result.get("items", [])
                return {
                    "status": "SUCCESS" if items else "FAILED",
                    "source_type": source_type,
                    "extraction_query": query,
                    "processed_records_count": len(items),
                    "extracted_data": items,
                    "records": items if isinstance(items, list) else [items],
                    "summary": result.get("summary", ""),
                    "raw_snippet": (content[:200] + "...") if len(content) > 200 else content,
                }
            else:
                return {
                    "status": "FAILED",
                    "error": f"LLM returned unexpected type: {type(result).__name__}",
                    "source_type": source_type,
                    "processed_records_count": 0,
                    "records": [],
                }

        except Exception as e:
            logger.warning(f"LLM extraction failed, falling back to structural: {e}")
            return self._structural_extract(content, ["status", "metric", "timestamp", "severity"], source_type)

    def _structural_extract(self, content: str, fields: List[str], source_type: str) -> Dict[str, Any]:
        """Structural extraction using JSON/CSV/regex parsing."""
        extracted_fields: Dict[str, Any] = {}
        records: List[Dict[str, Any]] = []
        processed_count = 0

        # 1. Try parsing as JSON
        try:
            parsed_json = json.loads(content)
            if isinstance(parsed_json, dict):
                processed_count = 1
                records = [parsed_json]
                for f in fields:
                    for k, v in parsed_json.items():
                        if f.lower() in k.lower():
                            extracted_fields[f] = v
                            break
                    if f not in extracted_fields:
                        extracted_fields[f] = parsed_json.get(f)
            elif isinstance(parsed_json, list):
                processed_count = len(parsed_json)
                records = [r for r in parsed_json if isinstance(r, dict)]
                if records:
                    for f in fields:
                        values = [r.get(f) for r in records if f in r or any(f.lower() in k.lower() for k in r)]
                        extracted_fields[f] = values if len(values) > 1 else (values[0] if values else None)
        except (json.JSONDecodeError, TypeError):
            # 2. Try parsing as CSV / TSV
            lines = [l.strip() for l in content.strip().splitlines() if l.strip()]
            processed_count = len(lines)

            if len(lines) > 1 and ("," in lines[0] or "\t" in lines[0]):
                delimiter = "\t" if "\t" in lines[0] else ","
                try:
                    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
                    csv_records = list(reader)
                    if csv_records:
                        records = csv_records
                        processed_count = len(csv_records)
                        for f in fields:
                            col_match = next((col for col in reader.fieldnames or [] if f.lower() in col.lower()), None)
                            if col_match:
                                vals = [r.get(col_match) for r in csv_records]
                                extracted_fields[f] = vals if len(vals) > 1 else (vals[0] if vals else None)
                except Exception:
                    pass

            # 3. Fallback to regex key-value and log extraction
            if not extracted_fields:
                for f in fields:
                    kv_match = re.search(rf"(?i)\b{re.escape(f)}\s*[:=]\s*([^\r\n,;]+)", content)
                    if kv_match:
                        val = kv_match.group(1).strip().strip('"\'')
                        extracted_fields[f] = val
                    else:
                        if f.lower() in ("severity", "level", "status"):
                            lvl_match = re.search(r"\b(CRITICAL|FATAL|ERROR|WARN(?:ING)?|INFO|DEBUG|TRACE|PASSED|FAILED|SUCCESS)\b", content, re.IGNORECASE)
                            extracted_fields[f] = lvl_match.group(1).upper() if lvl_match else None
                        elif f.lower() in ("timestamp", "time", "date"):
                            ts_match = re.search(r"\b(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\b", content)
                            extracted_fields[f] = ts_match.group(1) if ts_match else None
                        elif f.lower() in ("count", "total", "records", "metric"):
                            num_match = re.search(rf"(?i)\b{re.escape(f)}[^\d]*(\d+)", content)
                            extracted_fields[f] = int(num_match.group(1)) if num_match else None
                        else:
                            extracted_fields[f] = None

        return {
            "source_type": source_type,
            "processed_records_count": processed_count,
            "extracted_fields": extracted_fields,
            "records_sample": records[:5] if records else [],
            "raw_snippet": (content[:150] + "...") if len(content) > 150 else content
        }
