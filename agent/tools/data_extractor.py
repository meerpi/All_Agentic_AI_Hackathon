import csv
import io
import json
import re
from typing import Any, Dict, List, Optional
from agent.tools.base import BaseTool


class DataExtractorTool(BaseTool):
    name = "data_extractor"
    description = "Parses raw unstructured text, server logs, CSV, or payload data into structured JSON entities."

    def run(
        self,
        source_type: str = "text_payload",
        raw_content: Optional[str] = None,
        fields_to_extract: Optional[List[str]] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        content = raw_content or kwargs.get("content") or kwargs.get("data") or kwargs.get("text") or ""
        fields = fields_to_extract or ["status", "metric", "timestamp", "severity"]
        
        extracted_fields: Dict[str, Any] = {}
        records: List[Dict[str, Any]] = []
        processed_count = 0

        if not content.strip():
            return {
                "source_type": source_type,
                "processed_records_count": 0,
                "extracted_fields": {f: None for f in fields},
                "records": [],
                "raw_snippet": "No raw input provided"
            }

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
                    # Look for "field: value" or "field = value" or "field=value"
                    kv_match = re.search(rf"(?i)\b{re.escape(f)}\s*[:=]\s*([^\r\n,;]+)", content)
                    if kv_match:
                        val = kv_match.group(1).strip().strip('"\'')
                        extracted_fields[f] = val
                    else:
                        # Log-specific patterns
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
