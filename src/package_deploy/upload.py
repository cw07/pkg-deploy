#!/usr/bin/env python3
import sys
import logging
import subprocess
from pathlib import Path
from abc import ABC, abstractmethod

from ..package_deploy.build import DeployConfig


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
        for binary in (config.project_dir / 'dist').iterdir():
            if config.package_name.replace("-", "_") in binary.name and binary.suffix == '.whl':
                wheel_files.append(binary.name)
        if len(wheel_files) != 1:
            raise ValueError(f"Unable to determine wheel, candidates are: {wheel_files}")
        wheel_file = wheel_files[0]
        logger.info(f"Built {wheel_file}")
        return wheel_file

    def upload(self, config: DeployConfig, dist_dir: Path) -> bool:
        try:
            if not config.repository_url:
                raise ValueError("Repository URL is required for Nexus deployment")

            wheel_file = self.get_wheel_files(config)

            if config.dry_run:
                cmd = [sys.executable, "-m", "twine", "check",
                       f"dist/{wheel_file}"
                       ]
            else:
                cmd = [sys.executable, "-m", "twine", "upload",
                       "--repository-url", config.repository_url,
                       f"dist/{wheel_file}",
                       "--disable-progress-bar"
                       ]
                if config.username:
                    cmd.extend(["--username", config.username])
                if config.password:
                    cmd.extend(["--password", config.password])

            logger.info(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                raise ValueError(f"Nexus build failed, \nstdout: {result.stdout}\nstderr: {result.stderr}")

            logger.info("Package deployed to Nexus successfully")
            return True

        except Exception as e:
            logger.error(f"Nexus deploy error: {e}")
            return False
