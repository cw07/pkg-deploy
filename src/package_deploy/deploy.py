#!/usr/bin/env python3
"""
Modern Python Package Deployment Tool
"""
import sys
import subprocess
from pathlib import Path
from abc import ABC, abstractmethod

from package_deploy.utils import logger
from package_deploy.strategy import DeployConfig


class Deploy(ABC):
    """Deploy Base class"""

    @abstractmethod
    def deploy(self, config: DeployConfig, dist_dir: Path) -> bool:
        """执行部署"""
        pass


class NexusDeploy(Deploy):
    """Nexus Deploy"""

    def deploy(self, config: DeployConfig, dist_dir: Path) -> bool:
        try:
            if not config.repository_url:
                raise ValueError("Repository URL is required for Nexus deployment")

            if config.dry_run:
                cmd = [sys.executable, "-m", "twine", "check",
                       f"dist/{dist_dir.name}"
                       ]
            else:
                cmd = [sys.executable, "-m", "twine", "upload",
                       "--repository-url", config.repository_url,
                       f"dist/{dist_dir.name}",
                       "--disable-progress-bar"
                       ]

                if config.username:
                    cmd.extend(["--username", config.username])

                if config.password:
                    cmd.extend(["--password", config.password])

            cmd.append("--skip-existing")

            logger.info(f"Running: {' '.join(cmd)}")

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"Nexus deploy failed: {result.stderr}")
                return False

            logger.info("Package deployed to Nexus successfully")
            return True

        except Exception as e:
            logger.error(f"Nexus deploy error: {e}")
            return False
