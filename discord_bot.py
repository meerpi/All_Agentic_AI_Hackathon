import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
from agent.orchestrator import TaskmasterOrchestrator
from agent.models import TaskGoal, WorkflowStatus

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "mock_discord_token_for_hackathon")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

orchestrator = TaskmasterOrchestrator()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} - Ready to accept tasks via Discord!')

@bot.command(name="task")
async def handle_task(ctx, *, goal: str):
    await ctx.send(f"🤖 **Taskmaster received goal:** {goal}\n_Planning workflow..._")
    
    try:
        # Run planning
        goal_input = TaskGoal(goal=goal, context={"channel": "discord", "user": str(ctx.author)})
        workflow = orchestrator.create_plan(goal_input)
        
        await ctx.send(f"📋 **Plan Created** (ID: {workflow.workflow_id}) with {len(workflow.steps)} steps.\n_Executing..._")
        
        # Execute workflow synchronously (for simplicity in the bot)
        # In a true prod app this would be async/offloaded to a task queue
        loop = asyncio.get_event_loop()
        final_workflow = await loop.run_in_executor(None, orchestrator.execute_workflow, workflow.workflow_id)
        
        if final_workflow.status == WorkflowStatus.COMPLETED:
            await ctx.send(f"✅ **Workflow Completed Successfully!**\n\n**Summary:**\n{final_workflow.summary}")
        else:
            await ctx.send(f"❌ **Workflow Failed!** Check traces for details.")
            
    except Exception as e:
        await ctx.send(f"⚠️ **Error:** {str(e)}")

if __name__ == "__main__":
    if DISCORD_TOKEN and DISCORD_TOKEN != "mock_discord_token_for_hackathon":
        bot.run(DISCORD_TOKEN)
    else:
        print("DISCORD_TOKEN not set. Discord bot disabled.")
