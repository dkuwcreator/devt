# devt/manifest.py
import json
import logging
from pathlib import Path
from jsonschema import validate, ValidationError

logger = logging.getLogger("devt")

MANIFEST_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "command": {"type": "string"},
        "scripts": {"type": "object"},
    },
    "required": ["name", "command", "scripts"],
}

def validate_manifest(manifest_path: Path):
    try:
        with open(manifest_path, "r") as file:
            manifest = json.load(file)
        validate(instance=manifest, schema=MANIFEST_SCHEMA)
        scripts = manifest.get("scripts", {})

        # Check for the presence of an install script (generic or shell-specific)
        install_present = (
            "install" in scripts or
            ("windows" in scripts and "install" in scripts["windows"]) or
            ("posix" in scripts and "install" in scripts["posix"])
        )
        if not install_present:
            logger.error(f"Manifest scripts: {json.dumps(scripts, indent=4)}")
            raise ValueError("At least one install script is required in the manifest.")
    except (FileNotFoundError, json.JSONDecodeError, ValidationError) as e:
        raise ValueError(f"Error validating manifest: {e}")
