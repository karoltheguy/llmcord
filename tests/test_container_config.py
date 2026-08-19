import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_owns_data_dir():
    dockerfile = (REPO_ROOT / "Dockerfile").read_text()

    user_match = re.search(r"^USER\s+llmcord\s*$", dockerfile, re.MULTILINE)
    assert user_match is not None, "Dockerfile must switch to the llmcord user"

    before_user = dockerfile[: user_match.start()]

    mkdir_match = re.search(r"mkdir\s+(-p\s+)?/app/data", before_user)
    assert mkdir_match is not None, (
        "Dockerfile must create /app/data before switching to the llmcord user"
    )

    chown_match = re.search(r"chown\s+\S*llmcord\S*\s+/app/data", before_user) or re.search(
        r"--chown=llmcord\S*", before_user
    )
    assert chown_match is not None, (
        "Dockerfile must give ownership of /app/data to llmcord before switching users"
    )


def test_compose_data_mount_is_named_volume():
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.yaml").read_text())

    service_volumes = compose["services"]["container"]["volumes"]

    data_mount = None
    for entry in service_volumes:
        if isinstance(entry, str):
            parts = entry.split(":")
            if len(parts) >= 2 and parts[1] == "/app/data":
                data_mount = entry
                source = parts[0]
                break
        elif isinstance(entry, dict):
            if entry.get("target") == "/app/data":
                data_mount = entry
                source = entry.get("source", "")
                break

    assert data_mount is not None, "docker-compose.yaml must mount something at /app/data"

    assert not source.startswith(".") and not source.startswith("/"), (
        f"/app/data must be backed by a named volume, not a host bind (got source={source!r})"
    )

    top_level_volumes = compose.get("volumes") or {}
    assert source in top_level_volumes, (
        f"volume {source!r} used for /app/data must be declared under the top-level volumes: key"
    )
