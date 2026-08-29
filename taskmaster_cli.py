import argparse
import asyncio
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich import print as rprint
from agent.orchestrator import TaskmasterOrchestrator
from agent.models import TaskGoal, WorkflowStatus
import uuid

console = Console()

async def main():
    parser = argparse.ArgumentParser(description="Taskmaster CLI - Run workflows from the terminal")
    parser.add_argument("goal", type=str, help="The goal for the agent to execute")
    parser.add_argument("--priority", type=str, default="Normal", help="Priority of the task")
    args = parser.parse_args()

    console.print(Panel(f"[bold green]Taskmaster CLI[/bold green]\nGoal: {args.goal}", expand=False))

    orchestrator = TaskmasterOrchestrator()
    goal_input = TaskGoal(goal=args.goal, context={"priority": args.priority})
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        task1 = progress.add_task("[cyan]Planning workflow...", total=None)
        workflow = orchestrator.create_plan(goal_input)
        progress.update(task1, completed=True)
        
        console.print(f"[bold blue]Created Workflow:[/bold blue] {workflow.workflow_id} with {len(workflow.steps)} steps")
        
        task2 = progress.add_task("[yellow]Executing autonomous workflow...", total=None)
        
        # Execute workflow synchronously for the CLI
        final_workflow = orchestrator.execute_workflow(workflow.workflow_id)
        progress.update(task2, completed=True)

    if final_workflow.status == WorkflowStatus.COMPLETED:
        console.print(Panel(f"[bold green]Workflow Completed Successfully![/bold green]", expand=False))
    else:
        console.print(Panel(f"[bold red]Workflow Failed![/bold red]", expand=False))
        
    table = Table(title="Execution Trace")
    table.add_column("Step", justify="right", style="cyan")
    table.add_column("Tool", style="magenta")
    table.add_column("Status", style="green")
    
    for step in final_workflow.steps:
        status_color = "green" if step.status.value == "COMPLETED" else "red" if step.status.value == "FAILED" else "yellow"
        table.add_row(str(step.step_number), step.tool_name, f"[{status_color}]{step.status.value}[/{status_color}]")
        
    console.print(table)
    
    if final_workflow.summary:
        console.print(Panel(final_workflow.summary, title="Final Summary", expand=False))

if __name__ == "__main__":
    asyncio.run(main())
