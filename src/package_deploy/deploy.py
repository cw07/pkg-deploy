#!/usr/bin/env python3
"""
Modern Python Package Deployment Tool
"""
import sys
import shutil
import argparse
import logging
import subprocess
import tempfile
from pathlib import Path
from abc import ABC, abstractmethod

from package_deploy.utils import get_credentials, logger
from package_deploy.version_managment import VersionManager
from package_deploy.strategy import StandardBuildStrategy, CythonBuildStrategy, DeployConfig


class Deploy(ABC):
    """Deploy Base class"""

    @abstractmethod
    def deploy(self, config: DeployConfig, dist_dir: Path) -> bool:
        """执行部署"""
        pass


class PyPIDeploy(Deploy):
    """PyPI Deploy"""

    def deploy(self, config: DeployConfig, dist_dir: Path) -> bool:
        try:
            cmd = [sys.executable, "-m", "twine", "upload"]

            if config.repository_url:
                cmd.extend(["--repository-url", config.repository_url])

            if config.username:
                cmd.extend(["--username", config.username])

            if config.password:
                cmd.extend(["--password", config.password])

            if config.dry_run:
                cmd.append("--dry-run")
                logger.info("Dry run mode enabled")

            # 添加所有分发文件
            dist_files = list(dist_dir.glob("*"))
            cmd.extend([str(f) for f in dist_files])

            logger.info(f"Running: {' '.join(cmd[:-len(dist_files)])} [dist_files...]")

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"Deploy failed: {result.stderr}")
                return False

            logger.info("Package deployed successfully")
            return True

        except Exception as e:
            logger.error(f"Deploy error: {e}")
            return False


class NexusDeploy(Deploy):
    """Nexus Deploy"""

    def deploy(self, config: DeployConfig, dist_dir: Path) -> bool:
        try:
            if not config.repository_url:
                raise ValueError("Repository URL is required for Nexus deployment")

            cmd = [sys.executable, "-m", "twine", "upload",
                   "--repository-url", config.repository_url]

            if config.username:
                cmd.extend(["--username", config.username])

            if config.password:
                cmd.extend(["--password", config.password])

            if config.dry_run:
                cmd.append("--dry-run")
                logger.info("Dry run mode enabled")

            # 跳过已存在的包
            cmd.append("--skip-existing")

            # 添加所有分发文件
            dist_files = list(dist_dir.glob("*"))
            cmd.extend([str(f) for f in dist_files])

            logger.info(f"Running: {' '.join(cmd[:-len(dist_files)])} [dist_files...]")

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"Nexus deploy failed: {result.stderr}")
                return False

            logger.info("Package deployed to Nexus successfully")
            return True

        except Exception as e:
            logger.error(f"Nexus deploy error: {e}")
            return False


class PackageDeployer:
    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.pyproject_path = project_dir / "pyproject.toml"
        self.version_manager = VersionManager(self.pyproject_path)

    def deploy(self, config: DeployConfig) -> bool:
        """执行部署流程"""
        logger.info(f"Starting deployment for package: {config.package_name}")

        try:
            # 1. Update package name (if specified)
            self._update_package_name(config.package_name)

            # 2. Update version number
            new_version = self.version_manager.bump_version(config.version_type)
            logger.info(f"New version: {new_version}")

            # 3. Create temporary working directory
            with tempfile.TemporaryDirectory() as temp_dir:
                work_dir = Path(temp_dir)

                # 复制项目文件到临时目录
                self._copy_project_files(work_dir)

                # 4. 选择构建策略
                build_strategy = (CythonBuildStrategy()
                                  if config.use_cython
                                  else StandardBuildStrategy())

                # 5. 构建包
                if not build_strategy.build(config, work_dir):
                    return False

                # 6. 选择部署策略
                deploy_strategy = self._get_deploy_strategy(config)

                # 7. 部署包
                dist_dir = work_dir / "dist"
                return deploy_strategy.deploy(config, dist_dir)

        except Exception as e:
            logger.error(f"Deployment failed: {e}")
            return False

    def _update_package_name(self, package_name: str):
        """更新包名称"""
        if package_name != self.version_manager.config['project']['name']:
            logger.info(f"Updating package name to: {package_name}")
            self.version_manager.config['project']['name'] = package_name
            self.version_manager._save_config()

    def _copy_project_files(self, dest_dir: Path):
        """复制项目文件到目标目录"""
        # 复制必要的文件和目录
        files_to_copy = [
            "pyproject.toml",
            "README.md",
            "LICENSE",
            "src",
            "setup.py",  # 如果存在
        ]

        for item_name in files_to_copy:
            src_path = self.project_dir / item_name
            if src_path.exists():
                dest_path = dest_dir / item_name
                if src_path.is_file():
                    shutil.copy2(src_path, dest_path)
                else:
                    shutil.copytree(src_path, dest_path)

    def _get_deploy_strategy(self, config: DeployConfig) -> Deploy:
        """获取部署策略"""
        if config.repository_url and "nexus" in config.repository_url.lower():
            return NexusDeploy()
        else:
            return PyPIDeploy()


class PackageDeploy:
    def __init__(self, args):
        parser = argparse.ArgumentParser(
            description="Modern Python Package Deployment Tool",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=
            """
            Examples:
              # Deploy to PyPI，patch version
              python deploy.py --package-name my-package --version-type patch
    
              # Deploy to private Nexus, using cython
              python deploy.py --package-name my-package --version-type minor --use-cython
                --repository-url https://nexus.example.com/repository/pypi-internal/
                --username admin
                --password secret
                
              # Dry run
              python deploy.py --package-name my-package --version-type patch --dry-run
            """)

        parser.add_argument(
            "--project-dir",
            type=Path,
            default=Path.cwd(),
            help="Project directory (default: current directory)"
        )

        parser.add_argument(
            "--package-name", "-n",
            required=True,
            help="Package name"
        )

        parser.add_argument(
            "--version-type", "-v",
            choices=["patch", "minor", "major"],
            default="patch",
            help="Version bump type (default: patch)"
        )

        parser.add_argument(
            "--use-cython", "-c",
            action="store_true",
            help="Use Cython for compilation"
        )

        parser.add_argument(
            "--repository-url", "-r",
            help="Repository URL (for private repositories)"
        )

        parser.add_argument(
            "--username", "-u",
            help="Username for authentication"
        )

        parser.add_argument(
            "--password", "-p",
            help="Password for authentication"
        )

        parser.add_argument(
            "--interactive", "-i",
            action="store_true",
            help="Force interactive credential input (useful for Nexus)"
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Perform a dry run without actual deployment"
        )

        parser.add_argument(
            "--create-sample",
            action="store_true",
            help="Create a sample pyproject.toml file"
        )

        parser.add_argument(
            "--verbose", "-V",
            action="store_true",
            help="Enable verbose logging"
        )

        args = parser.parse_args(args)

        if args.verbose:
            logging.getLogger().setLevel(logging.DEBUG)

        required_packages = ["build", "twine", "toml"]
        if args.use_cython:
            required_packages.append("Cython")

        missing_packages = []
        for package in required_packages:
            try:
                __import__(package)
            except ImportError:
                missing_packages.append(package)

        if missing_packages:
            logger.error(f"Missing required packages: {', '.join(missing_packages)}")
            logger.info(f"Install them with: pip install {' '.join(missing_packages)}")
            sys.exit(1)

        username, password = get_credentials(args)

        self.config = DeployConfig(
            project_dir=args.project_dir,
            package_name=args.package_name,
            version_type=args.version_type,
            use_cython=args.use_cython,
            repository_url=args.repository_url,
            username=username,
            password=password,
            dry_run=args.dry_run
        )

    def deploy(self):
        deployer = PackageDeployer(self.config.project_dir)
        if deployer.deploy(self.config):
            logger.info("Deployment completed successfully!")
            sys.exit(0)
        else:
            logger.error("Deployment failed!")
            sys.exit(1)
