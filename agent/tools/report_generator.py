import json
import time
from typing import Any, Dict, List, Optional, Union
from agent.tools.base import BaseTool


class ReportGeneratorTool(BaseTool):
    name = "report_generator"
    description = "Compiles structured executive markdown reports, action summaries, and audit trail artifacts from real data."

    def run(
        self,
        report_title: Optional[str] = None,
        title: Optional[str] = None,
        sections: Optional[Dict[str, Any]] = None,
        content: Optional[Union[str, Dict, List]] = None,
        summary: Optional[str] = None,
        results: Optional[Union[List, Dict]] = None,
        format: str = "markdown",
        **kwargs: Any
    ) -> Dict[str, Any]:
        final_title = report_title or title or kwargs.get("name") or "Taskmaster Operational Report"
        
        # Collect dynamic sections
        report_sections: Dict[str, str] = {}

        if sections and isinstance(sections, dict):
            for k, v in sections.items():
                if isinstance(v, dict):
                    lines = []
                    for sub_k, sub_v in v.items():
                        title_fmt = sub_k.replace("_", " ").title()
                        if isinstance(sub_v, list):
                            lines.append(f"**{title_fmt}**:")
                            for it in sub_v:
                                lines.append(f"- {it}")
                        else:
                            lines.append(f"- **{title_fmt}**: {sub_v}")
                    report_sections[str(k)] = "\n".join(lines)
                elif isinstance(v, list):
                    report_sections[str(k)] = "\n".join([f"- {it}" for it in v])
                else:
                    report_sections[str(k)] = str(v)

        # Ingest content/summary/results if provided
        raw_summary = summary or kwargs.get("executive_summary") or kwargs.get("text")
        if raw_summary and "Executive Summary" not in report_sections:
            report_sections["Executive Summary"] = str(raw_summary)

        raw_content = content or kwargs.get("data")
        if raw_content and "Key Findings & Analysis" not in report_sections:
            if isinstance(raw_content, dict):
                lines = []
                for sub_k, sub_v in raw_content.items():
                    title_fmt = sub_k.replace("_", " ").title()
                    if isinstance(sub_v, list):
                        lines.append(f"### {title_fmt}")
                        for it in sub_v:
                            lines.append(f"- {it}")
                    elif isinstance(sub_v, dict):
                        lines.append(f"### {title_fmt}")
                        for dk, dv in sub_v.items():
                            lines.append(f"- **{dk.replace('_', ' ').title()}**: {dv}")
                    else:
                        lines.append(f"- **{title_fmt}**: {sub_v}")
                report_sections["Key Findings & Analysis"] = "\n".join(lines)
            elif isinstance(raw_content, list):
                report_sections["Key Findings & Analysis"] = "\n".join([f"- {it}" for it in raw_content])
            else:
                report_sections["Key Findings & Analysis"] = str(raw_content)

        raw_results = results or kwargs.get("artifacts") or kwargs.get("step_results")
        if raw_results and "Execution Results" not in report_sections:
            if isinstance(raw_results, list):
                res_lines = []
                for idx, item in enumerate(raw_results, start=1):
                    if isinstance(item, dict):
                        res_lines.append(f"- **Step {idx}**: `{item.get('status', 'COMPLETED')}` — {item.get('summary', item.get('description', json.dumps(item)))}")
                    else:
                        res_lines.append(f"- **Step {idx}**: {item}")
                report_sections["Execution Results"] = "\n".join(res_lines)
            elif isinstance(raw_results, dict):
                lines = []
                for rk, rv in raw_results.items():
                    lines.append(f"- **{rk.replace('_', ' ').title()}**: {rv}")
                report_sections["Execution Results"] = "\n".join(lines)

        # If still empty, provide clean default structure reflecting actual state
        if not report_sections:
            report_sections["Overview"] = "Autonomous task execution report compiled from live operational traces."
            report_sections["Status"] = "Execution completed. No custom section breakdown was specified by caller."

        # Pick appropriate icon
        icon = "🎬" if any(w in final_title.lower() for w in ["video", "youtube", "media", "speech"]) else "📊"

        # Assemble markdown document
        md_content = f"# {icon} {final_title}\n\n"
        md_content += f"> *Generated autonomously by Taskmaster Agent Engine on {time.strftime('%Y-%m-%d %H:%M:%S UTC')}*\n\n"

        for sec_title, sec_text in report_sections.items():
            md_content += f"## {sec_title}\n{sec_text}\n\n"

        return {
            "report_title": final_title,
            "format": format,
            "sections_count": len(report_sections),
            "artifact_length_chars": len(md_content),
            "markdown_content": md_content
        }

