from pathlib import Path


def ensure_secrets_dir() -> Path:
    """Ensure secrets directory exists and return the path."""
    secrets_path = Path("secrets")
    secrets_path.mkdir(exist_ok=True)
    return secrets_path


def get_secret_path(filename: str) -> str:
    """Get full path to a secret file."""
    return str(ensure_secrets_dir() / filename)


# Ensure secrets directory exists on import
ensure_secrets_dir()
