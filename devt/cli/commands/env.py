import typer
import logging
from pathlib import Path
from dotenv import set_key, get_key, unset_key

logger = logging.getLogger(__name__)
env_app = typer.Typer(help="Environment commands wrapper for python-dotenv")
DEFAULT_ENV_FILE = ".env"

@env_app.command("set")
def set_env(
    key: str = typer.Argument(..., help="Environment variable key"),
    value: str = typer.Argument(..., help="Environment variable value"),
    env_file: Path = typer.Option(DEFAULT_ENV_FILE, help="Path to the environment file")
):
    """
    Set an environment variable in the dotenv file.
    """
    env_path = Path(env_file)
    if not env_path.exists():
        logger.info(f"{env_file} does not exist. Creating a new one.")
        env_path.touch()
    set_key(str(env_path), key, value)
    logger.info(f"Set {key}={value} in {env_file}")


@env_app.command("see")
def see_env(
    key: str = typer.Argument(..., help="Environment variable key"),
    env_file: Path = typer.Option(DEFAULT_ENV_FILE, help="Path to the environment file")
):
    """
    View the current value of an environment variable in the dotenv file.
    """
    val = get_key(str(env_file), key)
    if val is None:
        logger.info(f"{key} not found in {env_file}")
    else:
        logger.info(f"{key}={val}")


@env_app.command("remove")
def remove_env(
    key: str = typer.Argument(..., help="Environment variable key"),
    env_file: Path = typer.Option(DEFAULT_ENV_FILE, help="Path to the environment file")
):
    """
    Remove an environment variable from the dotenv file.
    """
    if get_key(str(env_file), key) is None:
        logger.info(f"{key} not found in {env_file}")
    else:
        unset_key(str(env_file), key)
        logger.info(f"Removed {key} from {env_file}")

if __name__ == "__main__":
    env_app()