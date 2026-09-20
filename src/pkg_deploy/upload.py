import os
import sys
import logging
import subprocess
from pathlib import Path
from abc import ABC, abstractmethod

from .build import DeployConfig


logger = logging.getLogger(__name__)


class Upload(ABC):
    """Upload strategy: hand the built wheels to an index."""

    @abstractmethod
    def upload(self, config: DeployConfig, dist_dir: Path) -> bool:
        pass


class NexusUpload(Upload):
    """Upload with twine. Despite the name this serves any index - PyPI or a private
    one such as Nexus - since twine speaks the same protocol to all of them."""

    @staticmethod
    def get_wheel_files(config: DeployConfig):
        wheel_files = []
        dist_dir = config.project_dir / 'dist'
        for binary in dist_dir.iterdir():
            if config.package_name.replace("-", "_") in binary.name and binary.suffix == '.whl':
                wheel_files.append(binary.name)

        if len(wheel_files) < 1:
            raise ValueError(f"No wheel files found under {config.project_dir / 'dist'}")
        else:
            logger.info(f"Built {len(wheel_files)} wheel files: {wheel_files}")
            for file in wheel_files:
                file_path = dist_dir / file
                size_bytes = file_path.stat().st_size
                size_mb = size_bytes / (1024 * 1024)
                logger.info(f"Found valid package wheel: {file} ({size_mb:.2f} MB)")
        return wheel_files

    def upload(self, config: DeployConfig, dist_dir: Path) -> bool:
        try:
            cmd = [sys.executable, "-m", "twine", "upload",
                   "--disable-progress-bar",
                   "--verbose"
                   ]

            wheel_files = self.get_wheel_files(config)
            wheel_paths = [str(dist_dir / wheel_file) for wheel_file in wheel_files]
            cmd.extend(wheel_paths)

            if config.repository_name != "pypi":
                cmd.extend(["--repository-url", config.repository_url])

            # Credentials go through TWINE_USERNAME / TWINE_PASSWORD, never argv.
            env = os.environ.copy()
            if config.username:
                env["TWINE_USERNAME"] = config.username
            if config.password:
                env["TWINE_PASSWORD"] = config.password

            logger.info(f"Running: {' '.join(cmd)}")

            if config.dry_run:
                logger.info(f"DRY RUN: wheel files from dist directory: {wheel_files}")
                logger.info(f"DRY RUN: cmd: {cmd}")
            else:
                result = subprocess.run(cmd, capture_output=True, text=True, env=env)
                if result.returncode != 0:
                    raise ValueError(f"Upload failed, \nstdout: {result.stdout}\nstderr: {result.stderr}")
                logger.info(f"Package uploaded to {config.repository_url} successfully")
            return True
        except Exception as e:
            logger.error(f"Package upload error: {e}")
            return False
