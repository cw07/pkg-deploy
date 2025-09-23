import sys
import logging
import subprocess
from pathlib import Path
from abc import ABC, abstractmethod

from .build import DeployConfig


logger = logging.getLogger(__name__)


class Upload(ABC):
    """Deploy Base class"""

    @abstractmethod
    def upload(self, config: DeployConfig, dist_dir: Path) -> bool:
        pass


class NexusUpload(Upload):
    """Nexus Deploy"""

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
                logger.info(f"Found valid package wheel: {file} ({dist_dir})")
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

            cmd.extend(["--username", config.username])
            cmd.extend(["--password", config.password])

            # Create masked command for logging
            masked_cmd = []
            for i, arg in enumerate(cmd):
                if i > 0 and cmd[i - 1] == "--password":
                    masked_cmd.append("******")
                else:
                    masked_cmd.append(arg)

            logger.info(f"Running: {' '.join(masked_cmd)}")

            if config.dry_run:
                logger.info(f"DRY RUN: wheel files from dist directory: {wheel_files}")
                logger.info(f"DRY RUN: cmd: {cmd}")
            else:
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    raise ValueError(f"Upload failed, \nstdout: {result.stdout}\nstderr: {result.stderr}")
                logger.info(f"Package uploaded to {config.repository_url} successfully")
            return True
        except Exception as e:
            logger.error(f"Package upload error: {e}")
            return False
