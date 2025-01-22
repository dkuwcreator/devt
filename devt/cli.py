from typing import List, Optional
import typer
from pathlib import Path
from devt.core.logger import logger
from devt.core.env import TOOLS_DIR
from devt.core.utils import load_tools

TOOL_REGISTRY = load_tools(TOOLS_DIR)

app = typer.Typer()

@app.command()
def init():
    """
    Initialize the environment and repository as required.
    """
    load_tools(TOOLS_DIR)
    logger.info("Initializing the environment...")
    git_tool = TOOL_REGISTRY.get("git")
    vscode_tool = TOOL_REGISTRY.get("vscode")
    cwd = Path.cwd()
    if (cwd / ".git").exists() and git_tool:
        logger.info("Setting up git configuration...")
        git_tool.run_script("set")
    if not (cwd / ".vscode").exists() and vscode_tool:
        logger.info("Setting up VS Code configuration...")
        vscode_tool.run_script("set")
    logger.info("Repository and tools are ready")

@app.command()
def run(
    task_name: str,
    tools: Optional[List[str]] = typer.Argument(
        None, help="List of tool names to run the task for"
    ),
):
    """
    Run a specified task for the given tools.
    Args:
        task_name (str): The name of the task to run.
        tools (Optional[List[str]]): List of tool names to run the task for. Uses all configured tools if not specified.
    """
    task_tools = tools
    for tool_name in task_tools:
        tool_instance = TOOL_REGISTRY.get(tool_name)
        if tool_instance:
            logger.info(f"Running '{task_name}' for {tool_name}...")
            tool_instance.run_script(task_name)
        else:
            logger.error(f"Tool not found or not configured: {tool_name}")
            logger.error(f"The available tools are: {', '.join(TOOL_REGISTRY.keys())}")

if __name__ == '__main__':
    app()