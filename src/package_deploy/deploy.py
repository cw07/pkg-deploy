#!/usr/bin/env python3
"""
Modern Python Package Deployment Tool
"""
import os
import sys
import glob
import shutil
import argparse
import logging
import subprocess
from pathlib import Path
from typing import Optional
from abc import ABC, abstractmethod

from package_deploy.version_managment import VersionManager
from package_deploy.utils import get_credentials, logger, get_pypirc_info, save_config
from package_deploy.strategy import StandardBuildStrategy, CythonBuildStrategy, DeployConfig


def parse_args(args):
    parser = argparse.ArgumentParser(
        description="Modern Python Package Deployment Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
        Examples:
          # Deploy to PyPI, patch version
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
        help="Package name"
    )

    parser.add_argument(
        "--version-type", "-v",
        choices=["patch", "minor", "major", "prerelease"],
        default="patch",
        help="Version bump type (default: patch)"
    )

    parser.add_argument(
        "--cython", "-c",
        action="store_true",
        help="Use Cython for compilation"
    )

    parser.add_argument(
        "--repository-name", "-rn",
        help="Repository name (.pypirc)"
    )

    parser.add_argument(
        "--repository-url", "-rl",
        help="Repository URL"
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
        "--verbose", "-V",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args(args)
    return args


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


class PackageDeploy:
    def __init__(self, args):
        args = parse_args(args)
        if args.verbose:
            logging.getLogger().setLevel(logging.DEBUG)

        required_packages = ["build", "twine", "toml"]
        if args.cython:
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

        pypirc_info = get_pypirc_info()
        repos = pypirc_info["repositories"]

        if args.repository_name and args.repository_name in repos:
            repository_info = repos[args.repository_name]
            url = repository_info["repository"]
            username = repository_info["username"]
            password = repository_info["password"]
        elif args.repository_name:
            raise ValueError("Repository name is provided but not found in .pypirc")
        else:
            url = args.repository_url
            username, password = get_credentials(args)

        self.config = DeployConfig(
            project_dir=args.project_dir,
            pyproject_path=args.project_dir / "pyproject.toml",
            package_name=args.package_name,
            version_type=args.version_type,
            use_cython=args.cython,
            repository_name=args.repository_name,
            repository_url=url,
            username=username,
            password=password,
            dry_run=args.dry_run
        )
        self.setup_file_exist = (self.config.project_dir / "setup.py").exists()
        self.version_manager = VersionManager(self.config.pyproject_path)

    def deploy(self):
        logger.info(f"Starting deployment for package: {self.config.package_name}")

        try:
            # 1. Update package name (if specified)
            self._update_package_name(self.config.package_name)

            new_version = self.version_manager.bump_version(self.config.version_type)
            logger.info(f"New version: {new_version}")

            if self.config.use_cython:
                build_strategy = CythonBuildStrategy()
            else:
                build_strategy = StandardBuildStrategy()

            build_strategy.build(self.config, self.config.project_dir)

            deploy_strategy = self._get_deploy_strategy(self.config)

            dist_dir = self.config.project_dir / "dist"
            deploy_strategy.deploy(self.config, dist_dir)

            self.cleanup_build()
            self.git_push()

            logger.info('Deploy Complete')
        except Exception as e:
            logger.error(f"Deployment failed: {e}")
            return False

    def cleanup_build(self):
        logger.info('Deleting build, dist and egg-info')
        shutil.rmtree('dist', ignore_errors=True)
        shutil.rmtree('build', ignore_errors=True)
        shutil.rmtree(f'src/{self.config.package_name}.egg-info', ignore_errors=True)
        egg_info_name = logger.project_name.replace("-", "_")
        shutil.rmtree(f'src/{egg_info_name}.egg-info', ignore_errors=True)
        launcher_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        directory = os.path.join(launcher_dir, 'src', self.config.package_name.replace("-", "_"))
        c_files = glob.glob(os.path.join(directory, '**', '*.c'), recursive=True)
        if not self.setup_file_exist:
            Path("setup.py").unlink(missing_ok=True)
        for file_path in c_files:
            Path(file_path).unlink(missing_ok=True)

    @staticmethod
    def git_push():
        logger.info('Pushing to github')
        try:
            subprocess.check_output(['git', 'pull'], stderr=subprocess.STDOUT)
            subprocess.check_output(['git', 'push', '--tags', '--force'], stderr=subprocess.STDOUT)
            subprocess.check_output(['git', 'push'], stderr=subprocess.STDOUT)
        except Exception as ex:
            if isinstance(ex, subprocess.CalledProcessError):
                logger.error(ex.output)
            logger.warning('Failed to push bump version commit. Please merge and push manually.')

    def _update_package_name(self, package_name: Optional[str]):
        if package_name and package_name != self.version_manager.config['project']['name']:
            logger.info(f"Updating package name to: {package_name}")
            self.version_manager.config['project']['name'] = package_name
            save_config(self.version_manager.config, self.config.pyproject_path)

    @staticmethod
    def _get_deploy_strategy(config) -> Deploy:
        return NexusDeploy()
