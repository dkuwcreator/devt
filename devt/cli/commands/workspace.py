import json
import yaml
from pathlib import Path
import typer
from devt.utils import find_file_type
from devt.config_manager import WORKSPACE_APP_DIR

workspace_app = typer.Typer(help="Project-level commands")

WORKSPACE_TEMPLATE = {
    "name": "My Workspace",
    "description": "A basic workspace.",
    "dependencies": {},
    "scripts": {"test": "echo workspace test"},
}


@workspace_app.command("init")
def workspace_init(
    file_format: str = typer.Option(
        "yaml",
        "--format",
        help="File format to initialize the workspace. Options: 'yaml' (default) or 'json'.",
    ),
    force: bool = typer.Option(False, "--force", help="Force initialization"),
):
    """
    Initializes a new development environment in the current workspace.
    """
    file_format_lower = file_format.lower()
    if file_format_lower == "json":
        target_file = WORKSPACE_APP_DIR / "manifest.json"
        workspace_content = json.dumps(WORKSPACE_TEMPLATE, indent=4)
    else:
        target_file = WORKSPACE_APP_DIR / "manifest.yaml"
        workspace_content = yaml.dump(WORKSPACE_TEMPLATE, sort_keys=False)

    if target_file.exists() and not force:
        typer.echo("Project already initialized. Use --force to overwrite.")
        raise typer.Exit(code=0)

    target_file.write_text(workspace_content)
    typer.echo(
        f"Project initialized successfully with {file_format_lower.upper()} format."
    )


@workspace_app.command("info")
def workspace_info():
    """
    Displays workspace configuration settings.
    """
    workspace_file = find_file_type("workspace", WORKSPACE_APP_DIR)
    if workspace_file.exists():
        typer.echo(workspace_file.read_text())
    else:
        typer.echo("No workspace file found. Run 'devt workspace init' first.")


# @workspace_app.command("list")
# def workspace_list():
#     """
#     Displays all tools registered in the workspace's workspace.json.
#     """
#     workspace_file = Path("workspace.json")
#     if workspace_file.exists():
#         typer.echo(workspace_file.read_text())
#     else:
#         typer.echo("No workspace.json found. Run 'devt workspace init' first.")

# @workspace_app.command("info")
# def workspace_info():
#     """
#     Displays workspace configuration settings.
#     """
#     workspace_file = Path("workspace.json")
#     if workspace_file.exists():
#         typer.echo(workspace_file.read_text())
#     else:
#         typer.echo("No workspace.json found.")

# @workspace_app.command("install")
# def workspace_install():
#     """
#     Installs all tools listed in workspace.json.
#     """
#     workspace_file = Path("workspace.json")
#     if not workspace_file.exists():
#         typer.echo("No workspace.json found. Run 'devt workspace init' first.")
#         raise typer.Exit(code=1)
#     try:
#         workspace = json.loads(workspace_file.read_text())
#         tools = workspace.get("tools", [])
#         for tool in tools:
#             # This example assumes an existing run_script function accessible from your CLI context.
#             from devt.cli.main import run_script  # Adjust the import as needed.
#             run_script(tool, "install", scope="both", extra_args=[])
#         typer.echo("All workspace tools installed successfully.")
#     except Exception as e:
#         typer.echo(f"Failed to install workspace tools: {e}")

# @workspace_app.command("run")
# def workspace_run(script: str = typer.Argument(..., help="Script name to run globally")):
#     """
#     Executes a global script defined in workspace.json.
#     """
#     workspace_file = find_file_type("workspace", WORKSPACE_APP_DIR)
#     if not workspace_file.exists():
#         typer.echo("No workspace.json found. Run 'devt workspace init' first.")
#         raise typer.Exit(code=1)
#     try:
#         workspace = json.loads(workspace_file.read_text())
#         scripts = workspace.get("scripts", {})
#         if script not in scripts:
#             typer.echo(f"Script '{script}' not found in workspace.json.")
#             raise typer.Exit(code=1)
#         typer.echo(f"Executing workspace script: {scripts[script]}")
#     except Exception as e:
#         typer.echo(f"Failed to run workspace script: {e}")

# @workspace_app.command("reset")
# def workspace_reset(force: bool = typer.Option(False, "--force", help="Force removal")):
#     """
#     Removes all workspace-level tools.
#     """
#     workspace_file = Path("workspace.json")
#     if workspace_file.exists():
#         workspace_file.unlink()
#         typer.echo("Project reset successfully.")
#     else:
#         typer.echo("No workspace.json found.")
