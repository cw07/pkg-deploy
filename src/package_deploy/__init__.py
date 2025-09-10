import os
import sys
import glob
import shutil
import logging
import argparse
import subprocess
from pathlib import Path

from package_deploy.deploy import Deploy, NexusDeploy
from package_deploy.version_managment import VersionManager
from package_deploy.utils import logger, get_pypirc_info, get_credentials, save_config
from package_deploy.build import DeployConfig, CythonBuildStrategy, StandardBuildStrategy


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
    if not args.repository_url and not args.repository_name:
        parser.error("Either --repository-url or --repository-name must be provided.")
    return args


class PackageDeploy:
    def __init__(self, args):
        args = parse_args(args)
        if not (args.project_dir / "pyproject.toml").exists():
            raise ValueError("pyproject.toml not found")

        if args.verbose:
            logging.getLogger().setLevel(logging.DEBUG)

        self.check_require_package(args.cython)

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

        pyproject_path = args.project_dir / "pyproject.toml"

        self.version_manager = VersionManager(pyproject_path)
        self.config = DeployConfig(
            package_name=self.version_manager.config["project"]["name"],
            project_dir=args.project_dir,
            pyproject_path=pyproject_path,
            version_type=args.version_type,
            use_cython=args.cython,
            repository_name=args.repository_name,
            repository_url=url,
            username=username,
            password=password,
            dry_run=args.dry_run
        )
        self.setup_file_exist = (self.config.project_dir / "setup.py").exists()

    @staticmethod
    def check_require_package(cython: bool):
        required_packages = ["build", "twine", "toml"]
        if cython:
            required_packages.append("Cython")

        missing_packages = []
        for package in required_packages:
            try:
                __import__(package)
            except ImportError:
                missing_packages.append(package)

        if missing_packages:
            logger.error(f"Missing required packages: {', '.join(missing_packages)}")
            logger.error(f"Install them with: pip install {' '.join(missing_packages)}")
            raise ValueError("Missing required packages")

    def deploy(self):
        logger.info(f"Starting deployment")

        try:
            new_version = self.version_manager.bump_version(self.config.version_type)
            logger.info(f"New version: {new_version}")

            if self.config.use_cython:
                build_strategy = CythonBuildStrategy()
            else:
                build_strategy = StandardBuildStrategy()

            if build_strategy.build(self.config, self.config.project_dir):
                deploy_strategy = self._get_deploy_strategy(self.config)
                dist_dir = self.config.project_dir / "dist"
                if deploy_strategy.deploy(self.config, dist_dir):
                    self.git_push()

            self.cleanup_build()
            logger.info('Deploy Complete')
        except Exception as e:
            logger.error(f"Deployment failed: {e}")
            return False

    def cleanup_build(self):
        logger.info('Deleting build, dist and egg-info')
        shutil.rmtree('dist', ignore_errors=True)
        shutil.rmtree('build', ignore_errors=True)
        shutil.rmtree(f'src/{self.config.package_name}.egg-info', ignore_errors=True)
        egg_info_name = self.config.package_name.replace("-", "_")
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

    @staticmethod
    def _get_deploy_strategy(config) -> Deploy:
        return NexusDeploy()



