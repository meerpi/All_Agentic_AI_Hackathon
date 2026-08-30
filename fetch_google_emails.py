import os
import sys
from datetime import datetime
from agent.tools.gmail_tool import GmailTool
from agent.tools.google_docs_tool import GoogleDocsTool

def main():
    gmail = GmailTool()
    docs = GoogleDocsTool()

    print("Fetching last 50 emails sent by Google (query='from:google')...")
    res = gmail.run(action="search_emails", query="from:google", max_results=50)
    emails = res.get("emails", [])
    print(f"Retrieved {len(emails)} emails from Google.")

    lines = []
    lines.append("# Audit Log: Last 50 Emails Received from Google\n\n")
    lines.append(f"**Total Records:** {len(emails)} emails\n")
    lines.append(f"**Audit Execution Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
    lines.append(f"**Account Audited:** `anima.mahanty1967@gmail.com`\n\n")
    lines.append("---\n\n")

    for i, e in enumerate(emails, 1):
        subj = e.get("subject") or "(No Subject)"
        sender = e.get("from") or "Unknown"
        date_str = e.get("date") or "Unknown"
        snippet = e.get("snippet") or ""
        msg_id = e.get("id") or ""

        lines.append(f"### {i}. {subj}\n")
        lines.append(f"- **From:** `{sender}`\n")
        lines.append(f"- **Timestamp:** `{date_str}`\n")
        lines.append(f"- **Message ID:** `{msg_id}`\n")
        lines.append(f"- **Preview / Snippet:** {snippet}\n\n")

    full_content = "".join(lines)

    # Save to Google Docs
    print("Creating Google Doc deliverable...")
    doc_res = docs.run(
        action="create_document",
        title="Audit: Last 50 Emails from Google",
        content=full_content
    )
    print("Google Doc Result:", doc_res)

    # Print summary to console
    print("\n--- Summary of Retrieved Emails ---")
    for i, e in enumerate(emails, 1):
        print(f"{i:2d}. [{e.get('date', 'Unknown')}] ({e.get('from', '')}) -> {e.get('subject', '')}")

if __name__ == "__main__":
    main()
