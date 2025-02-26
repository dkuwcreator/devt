# command_utils.py
import shlex
import shutil
from pathlib import Path
from devt.utils import load_manifest, validate_manifest, merge_configs


def needs_shell_fallback(args, posix: bool) -> bool:
    """
    Determine whether the given command requires a shell fallback.
    """
    if isinstance(args, list):
        first_arg = args[0]
    else:
        first_arg = shlex.split(args, posix=posix)[0]
    return shutil.which(first_arg) is None


def default_shell_prefix(command: str, is_windows: bool) -> list:
    """
    Return the default shell prefix for the current OS.
    """
    if is_windows:
        if shutil.which("pwsh"):
            return ["pwsh", "-Command", f"& {command}"]
        else:
            return ["powershell", "-Command", f"& {command}"]
    else:
        return ["bash", "-c", command]


def to_tokens(val, *, posix: bool, split: bool = True) -> list:
    """
    Normalize a value into a list of tokens.
    If `split` is True and the value is a string, it will be split using shlex.
    """
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return shlex.split(val, posix=posix) if split else [val]


def build_command_tokens(
    args, shell, extra_args, is_windows: bool, is_posix: bool
) -> list:
    """
    Build the final command tokens based on the provided parameters.
    """
    if shell == "":
        main_tokens = to_tokens(args, posix=is_posix, split=True)
        extra_tokens = to_tokens(extra_args, posix=is_posix, split=True)
        return main_tokens + extra_tokens
    elif shell is not None:
        wrapper_tokens = to_tokens(shell, posix=is_posix, split=True)
        # If args is a list, join them into a single token
        main_token = args if isinstance(args, str) else " ".join(args)
        extra_tokens = to_tokens(extra_args, posix=is_posix, split=True)
        return wrapper_tokens + [main_token] + extra_tokens
    else:
        if needs_shell_fallback(args, is_posix):
            prefix_tokens = default_shell_prefix(
                args if isinstance(args, str) else " ".join(args), is_windows
            )
            extra_tokens = to_tokens(extra_args, posix=is_posix, split=True)
            return prefix_tokens + extra_tokens
        main_tokens = to_tokens(args, posix=is_posix, split=True)
        extra_tokens = to_tokens(extra_args, posix=is_posix, split=True)
        return main_tokens + extra_tokens


def load_and_validate_manifest(manifest_path: Path) -> dict:
    """
    Load and validate a manifest file.
    """
    manifest = load_manifest(manifest_path)
    if not validate_manifest(manifest):
        raise ValueError(f"Invalid manifest file at {manifest_path}")
    return manifest


def merge_global_and_script_configs(
    manifest: dict, subprocess_allowed_keys: set
) -> dict:
    """
    Merge global configuration with per-script configuration from the manifest.
    """
    global_config = {k: v for k, v in manifest.items() if k in subprocess_allowed_keys}
    scripts_config = manifest.get("scripts", {})
    if not scripts_config:
        raise ValueError("No scripts found in the manifest file.")
    return merge_configs(global_config, scripts_config)
