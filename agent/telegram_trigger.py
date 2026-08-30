"""
Telegram Event Trigger — The Event-Driven Watcher for Taskmaster.

This is a standalone daemon that runs alongside the FastAPI server.
It listens for messages sent to the Telegram bot (via polling — no public URL needed),
and when a message arrives, it autonomously:
  1. Creates a TaskGoal from the message
  2. Plans a multi-step workflow via the orchestrator
  3. Executes the workflow
  4. Sends the results back to the Telegram chat

This satisfies the Taskmaster hackathon requirement:
  "An event-driven workflow with autonomous routing — watching for a change,
   figuring out what needs to happen next, and interacting with different apps."

Usage:
    python -m agent.telegram_trigger
    # Or: python agent/telegram_trigger.py

Requires TELEGRAM_BOT_TOKEN in .env.
"""

import asyncio
import logging
import os
import sys

# Ensure project root is on sys.path when run as a script
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from agent.config import settings
from agent.orchestrator import TaskmasterOrchestrator
from agent.models import TaskGoal, WorkflowStatus

logger = logging.getLogger("taskmaster.telegram_trigger")
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logger.error("python-telegram-bot not installed. Run: pip install python-telegram-bot")


# Shared orchestrator instance for this daemon
orchestrator = TaskmasterOrchestrator()


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command — introduce the bot."""
    welcome = (
        "🤖 *Taskmaster Autonomous Agent*\n\n"
        "I'm your event-driven workflow agent. Send me a task in plain English "
        "and I'll autonomously plan it, execute it across your connected apps "
        "(Gmail, Google Sheets, Calendar), and report back.\n\n"
        "*Examples:*\n"
        "• `Check my email and summarize today's important ones`\n"
        "• `Create a spreadsheet with my calendar events for this week`\n"
        "• `Read my unread emails and save senders to a Google Sheet`\n\n"
        "Just type your task below 👇"
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")


async def handle_task_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle any plain text message as a task goal.
    This is the EVENT TRIGGER — every incoming message triggers an autonomous workflow.
    """
    user_message = update.message.text
    chat_id = str(update.effective_chat.id)
    user_name = update.effective_user.full_name if update.effective_user else "Unknown"

    logger.info(f"EVENT RECEIVED: Telegram message from {user_name} (chat:{chat_id}): {user_message}")

    # Acknowledge receipt
    status_msg = await update.message.reply_text(
        f"📥 *Task received:* {user_message}\n\n⏳ _Planning workflow..._",
        parse_mode="Markdown",
    )

    try:
        from agent.guardrails.shared import apply_bot_guardrails, get_approval_required_tools
        
        # 1. Input guardrails
        apply_bot_guardrails(user_message=user_message)

        # Step 1: Create a TaskGoal from the message
        goal_input = TaskGoal(
            goal=user_message,
            context={
                "trigger": "telegram",
                "chat_id": chat_id,
                "user": user_name,
            },
        )

        # Step 2: Plan the workflow
        workflow = orchestrator.create_plan(goal_input)
        
        # 2. HITL guardrails — sets require_approval=True if high-risk tools detected
        apply_bot_guardrails(workflow_plan=workflow)
        
        step_list = "\n".join([f"  {s.step_number}. {s.description} (`{s.tool_name}`)" for s in workflow.steps])
        await status_msg.edit_text(
            f"📋 *Plan created* ({len(workflow.steps)} steps):\n{step_list}\n\n⚙️ _Executing..._",
            parse_mode="Markdown",
        )

        # Step 3: Execute the workflow (synchronous, runs in thread pool to not block)
        loop = asyncio.get_event_loop()
        final_workflow = await loop.run_in_executor(
            None, orchestrator.execute_workflow, workflow.workflow_id
        )

        # Step 4: Send results back
        if final_workflow.status == WorkflowStatus.AWAITING_APPROVAL:
            # Workflow paused for HITL approval — notify user with details
            paused_step = final_workflow.paused_at_step
            approval_tools = get_approval_required_tools(final_workflow)
            approval_text = (
                f"⏸️ *Workflow Paused for Approval*\n\n"
                f"*Workflow ID:* `{final_workflow.workflow_id}`\n"
                f"*Paused at Step:* {paused_step}\n"
                f"*Tools requiring approval:* {', '.join(approval_tools)}\n\n"
                f"Approve via the web dashboard:\n"
                f"`POST /api/agent/approve/{final_workflow.workflow_id}`"
            )
            await update.message.reply_text(approval_text, parse_mode="Markdown")
        elif final_workflow.status == WorkflowStatus.COMPLETED:
            # Build a result summary
            result_text = f"✅ *Workflow Completed Successfully!*\n\n"

            # Show step-by-step results
            for step in final_workflow.steps:
                status_emoji = "✅" if step.status.value == "COMPLETED" else "❌"
                result_text += f"{status_emoji} *Step {step.step_number}:* {step.description}\n"
                if step.execution_time_ms:
                    result_text += f"   ⏱️ {step.execution_time_ms:.0f}ms\n"

            result_text += f"\n📄 *Summary:*\n{final_workflow.summary or 'Task completed.'}"

            # Telegram has a 4096 char limit, truncate if needed
            if len(result_text) > 4000:
                result_text = result_text[:3997] + "..."

            # 3. Output guardrails
            masked_result = apply_bot_guardrails(output=result_text)
            await update.message.reply_text(masked_result, parse_mode="Markdown")
        else:
            # Report failures
            failed_steps = [s for s in final_workflow.steps if s.status.value == "FAILED"]
            error_text = f"❌ *Workflow Failed*\n\n"
            for s in failed_steps:
                error_text += f"• Step {s.step_number} ({s.tool_name}): {s.error or 'Unknown error'}\n"
                
            # 3. Output guardrails
            masked_error = apply_bot_guardrails(output=error_text)
            await update.message.reply_text(masked_error, parse_mode="Markdown")

    except ValueError as e:
        logger.warning(f"Validation/Guardrail rejection: {e}")
        await update.message.reply_text(
            f"⚠️ *Policy Notice:* {str(e)}",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Error processing Telegram task: {e}", exc_info=True)
        await update.message.reply_text(
            f"⚠️ *Error:* {str(e)}",
            parse_mode="Markdown",
        )


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command — show recent workflow info."""
    workflows = list(orchestrator.workflows.values())
    if not workflows:
        await update.message.reply_text("No workflows have been executed yet.")
        return

    latest = workflows[-1]
    status_text = (
        f"📊 *Latest Workflow Status*\n\n"
        f"*Goal:* {latest.goal}\n"
        f"*Status:* {latest.status.value}\n"
        f"*Steps:* {len(latest.steps)}\n"
        f"*ID:* `{latest.workflow_id}`"
    )
    await update.message.reply_text(status_text, parse_mode="Markdown")


async def handle_tools(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /tools command — list available tools."""
    from agent.tools.registry import registry
    tools = registry.list_tools()
    tools_text = "🔧 *Available Tools:*\n\n"
    for tool in tools:
        tools_text += f"• `{tool['name']}` — {tool['description']}\n"
    await update.message.reply_text(tools_text, parse_mode="Markdown")


def main():
    """Start the Telegram bot in polling mode (no public URL needed)."""
    if not TELEGRAM_AVAILABLE:
        print("ERROR: python-telegram-bot not installed. Run: pip install python-telegram-bot")
        sys.exit(1)

    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN not set in .env")
        print("Get one from @BotFather on Telegram and add to your .env file.")
        sys.exit(1)

    print("=" * 60)
    print("🤖 Taskmaster Telegram Event Trigger")
    print("=" * 60)
    print(f"Bot Token: ...{token[-6:]}")
    print("Mode: Long Polling (no public URL needed)")
    print("Listening for messages...")
    print("=" * 60)

    # Build the application
    app = Application.builder().token(token).build()

    # Register handlers
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("status", handle_status))
    app.add_handler(CommandHandler("tools", handle_tools))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_task_message))

    # Start polling — this blocks and runs the event loop
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
