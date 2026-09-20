import sys
import shutil
import zipfile
import logging
import argparse
import subprocess
from pathlib import Path
from tomlkit import TOMLDocument

from .upload import Upload, TwineUpload
from .version_managment import VersionManager
from .build import DeployConfig, CythonBuildStrategy, StandardBuildStrategy, resolve_source_root
from .utils import get_pypirc_info, get_credentials, is_uv_venv, validate_version_arg, load_config


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-5.5s] [%(name)-30.30s] [%(lineno)-4.4s] [%(processName)-12.12s]: %(message)s"
)
logger = logging.getLogger(__name__)


def parse_args(args):
    parser = argparse.ArgumentParser(
        description="Modern Python Package Deployment Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
        Examples (run from the project directory, the one holding pyproject.toml):
          # Patch bump, upload to the [pypi] section of ~/.pypirc
          pkg-deploy --repository-name pypi

          # Minor bump, Cython-compiled and minified, to a private index
          pkg-deploy --repository-name my-nexus --version-type minor --cython --minify

          # Same, but with an explicit URL and credentials prompted interactively
          pkg-deploy --repository-url https://nexus.example.com/repository/pypi-internal/ --cython

          # Start a pre-release cycle: 1.2.4 -> 1.2.5a1, then a2, b1, rc1, and finally 1.2.5
          pkg-deploy --repository-name pypi --version-type alpha

          # Build and inspect without publishing, bumping or touching git
          pkg-deploy --repository-name pypi --dry-run --verbose
          """)

    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path.cwd(),
        help="Project directory (default: current directory)"
    )

    parser.add_argument(
        "--package-dir",
        type=Path,
        default=None,
        help="Directory that holds the package sources, e.g. src. Default: resolved from "
             "tool.setuptools.packages.find.where / tool.setuptools.package-dir in "
             "pyproject.toml, falling back to <project-dir>/<package-name>"
    )

    parser.add_argument(
        "--version-type", "-vt",
        default="patch",
        help="Version bump type (default: patch). From a final release, alpha/beta/rc start a "
             "cycle on the next patch version (1.2.4 -> 1.2.5a1); from a pre-release, patch "
             "finalises it (1.2.5rc1 -> 1.2.5) and stages only move forward",
        choices=["major", "minor", "patch", "alpha", "beta", "rc"]
    )

    parser.add_argument(
        "--new-version", "-v",
        type=validate_version_arg,
        help="Exact version to publish, overriding --version-type. Format: MAJOR.MINOR.PATCH with "
             "an optional aN / bN / rcN suffix"
    )

    parser.add_argument(
        "--cython", "-c",
        action="store_true",
        help="Use Cython for compilation"
    )

    parser.add_argument(
        "--cibuildwheel",
        action="store_true",
        help="Build with cibuildwheel: one wheel per configured Python version, for this platform "
             "only (needs Docker on Linux)"
    )

    parser.add_argument(
        "--minify", "-m",
        dest="minify",
        action="store_true",
        help="Minify the code before compilation to reduce its size. Must be used together "
             "with --cython."
    )

    parser.add_argument(
        "--repository-name", "-rn",
        help="Repository name (.pypirc)"
    )

    parser.add_argument(
        "--repository-url", "-ru",
        help="Upload URL of the index; used when --repository-name is not in ~/.pypirc"
    )

    parser.add_argument(
        "--username", "-u",
        help="Username; prompted for if omitted and not in ~/.pypirc"
    )

    parser.add_argument(
        "--password", "-p",
        help="Password or API token; prompted for (hidden) if omitted and not in ~/.pypirc"
    )

    parser.add_argument(
        "--discard-version-bump",
        action="store_true",
        help="Leave the repository untouched: no bump commit, no tag, no push, and the version "
             "bump written to pyproject.toml is reverted after a successful upload. The published "
             "version therefore is not recorded anywhere in the repo, so the next deploy resolves "
             "to that same version again - pass --new-version to avoid the upload clashing."
    )

    parser.add_argument(
        "--skip-git-status-check",
        action="store_true",
        help="Skip git status check before deployment"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the wheel and log what would be uploaded, but do not publish, bump the "
             "version, or touch git. dist/ and build/ are still created and cleaned up "
             "(add --keep-dist to inspect the wheel)"
    )

    parser.add_argument(
        "--keep-dist",
        action="store_true",
        help="Leave dist/ in place after the run instead of deleting it, so the built wheel can "
             "be inspected or reused. dist/ is always emptied before the next build"
    )

    parser.add_argument(
        "--verbose", "-V",
        action="store_true",
        help="Debug logging, including the full output of the build tool"
    )

    args = parser.parse_args(args)
    if not args.repository_url and not args.repository_name:
        parser.error("Either --repository-url or --repository-name must be provided.")
    # --minify lives inside the generated Cython setup.py; the standard build has no hook for it.
    if args.minify and not args.cython:
        parser.error("--minify/-m only applies to Cython builds. Add --cython/-c, or drop --minify.")
    return args


class PackageDeploy:
    def __init__(self, argv=None):
        self.args = parse_args(sys.argv[1:] if argv is None else argv)
        if not (self.args.project_dir / "pyproject.toml").exists():
            raise ValueError(f"pyproject.toml not found under project directory: {self.args.project_dir}")
        else:
            pyproject_path = self.args.project_dir / "pyproject.toml"

        if self.args.verbose:
            logging.getLogger().setLevel(logging.DEBUG)

        self.check_require_package(self.args.cython)

        toml_config = load_config(pyproject_path)
        package_dir = self.resolve_package_dir(toml_config)
        source_root = resolve_source_root(self.args.project_dir, package_dir)

        url, username, password = self.get_twine_upload_info()

        self.version_manager = VersionManager(pyproject_path, toml_config)
        self.config = DeployConfig(
            package_name=toml_config["project"]["name"],
            project_dir=self.args.project_dir,
            package_dir=package_dir,
            source_root=source_root,
            pyproject_path=pyproject_path,
            version_type=self.args.version_type,
            new_version=self.args.new_version,
            use_cython=self.args.cython,
            use_cibuildwheel=self.args.cibuildwheel,
            use_minifier=self.args.minify,
            is_uv_venv=is_uv_venv(),
            repository_name=self.args.repository_name,
            repository_url=url,
            username=username,
            password=password,
            dry_run=self.args.dry_run,
            keep_dist=self.args.keep_dist,
        )
        self.setup_file_exist = (self.config.project_dir / "setup.py").exists()

    def deploy(self):
        logger.info("=== Deployment Configuration ===")
        for field, value in vars(self.config).items():
            if field == "password":
                logger.info(f"{field}: ***MASKED***")
            else:
                logger.info(f"{field}: {value}")
        logger.info("=================================")
        
        if self.config.dry_run:
            logger.info("DRY RUN: Starting deployment simulation")
        else:
            logger.info(f"Starting deployment")

        if not self.args.skip_git_status_check:
            self.check_git_status()
            
        built = False
        uploaded = False
        try:
            new_version = self.version_manager.bump_version(
                version_type=self.config.version_type,
                new_version=self.config.new_version,
                dry_run=self.config.dry_run
            )
            if self.config.dry_run:
                logger.info(f"DRY RUN: Would bump version to: {new_version}")
            else:
                logger.info(f"New version: {new_version}")

            if self.config.use_cython:
                build_strategy = CythonBuildStrategy()
            else:
                build_strategy = StandardBuildStrategy()

            # get_wheel_files() uploads every wheel in dist/, so a leftover from an earlier
            # run must not be there when the new one lands.
            shutil.rmtree(self.config.project_dir / 'dist', ignore_errors=True)
            try:
                built = build_strategy.build(self.config, self.version_manager.toml_config)
                if built:
                    dist_dir = self.config.project_dir / "dist"
                    if self.config.use_cython:
                        self.check_wheel_no_source_leak(dist_dir)
                    upload_strategy = self.get_upload_strategy(self.config)
                    uploaded = upload_strategy.upload(self.config, dist_dir)
            finally:
                self.cleanup_build_files()

            # Nothing was published: safe to undo the version bump and start over.
            if not uploaded:
                self.git_roll_back(self.config.project_dir, self.version_manager.touched_files)
                logger.error("Deploy failed: build failed" if not built else "Deploy failed: upload failed")
                return False

            # Past this point the package is on the index. Re-running deploy would bump
            # and publish a second version, so the working tree is only ever restored
            # below when the caller explicitly asked for it.
            logger.info(f"Deploy succeeded: {self.config.package_name} {new_version} uploaded")

            if self.args.discard_version_bump:
                # Requested behaviour: leave no trace of the release in the repository -
                # no bump commit, no tag, and the version bump itself is reverted.
                self.git_roll_back(self.config.project_dir, self.version_manager.touched_files)
                logger.warning(
                    f"--discard-version-bump: reverted the version bump, {self.config.pyproject_path.name} "
                    f"is back at its previous version even though {new_version} was published. "
                    f"The next deploy will resolve to {new_version} again and fail to upload unless "
                    f"you pass --new-version explicitly."
                )
                return True

            try:
                self.git_push(
                    project_dir=self.config.project_dir,
                    new_version=new_version,
                    files=self.version_manager.touched_files,
                    dry_run=self.config.dry_run,
                )
            except Exception as ex:
                logger.error(
                    f"Deploy SUCCEEDED, but updating git FAILED: {ex}\n"
                    f"  {self.config.package_name} {new_version} is already published - do NOT re-run "
                    f"deploy, it would bump the version and upload again.\n"
                    f"  The bump commit and tag v{new_version} exist locally only. Push them manually:\n"
                    f"      cd {self.config.project_dir} && git pull --rebase && git push --follow-tags"
                )
                return True

            logger.info("Deploy completed")
            return True
        except Exception as e:
            if uploaded:
                logger.error(
                    f"{self.config.package_name} {new_version} WAS published, but a later step failed: "
                    f"{e}. Skipping rollback - fix the repository manually.",
                    exc_info=True
                )
                return True
            logger.error(f"Deployment failed, rolling back: {e}", exc_info=True)
            self.git_roll_back(self.config.project_dir, self.version_manager.touched_files)
            logger.error(f"Deploy failed: {e}")
            return False

    def get_twine_upload_info(self):
        if not self.args.repository_name:
            # Explicit --repository-url: .pypirc is not consulted at all.
            url = self.args.repository_url
            username, password = get_credentials(username=self.args.username,
                                                 password=self.args.password,
                                                 url=url)
            return url, username, password

        try:
            repos = get_pypirc_info()["repositories"]
        except FileNotFoundError:
            # 'pypi' needs nothing from the file (token is prompted for); any other
            # name is a lookup into it, so the file must exist.
            if self.args.repository_name != "pypi":
                raise
            repos = {}

        if self.args.repository_name == "pypi":
            url = None
            username = "__token__"
            password = None
            if "pypi" in repos:
                password = repos["pypi"].get("password")
            if not password:
                _, password = get_credentials(username=username, is_pypi=True)
        elif self.args.repository_name in repos:
            repository_info = repos[self.args.repository_name]
            url = repository_info.get("repository")
            username = repository_info.get("username")
            password = repository_info.get("password")
            if not url:
                raise ValueError(
                    f"Repository '{self.args.repository_name}' must have a 'repository' url in .pypirc. "
                    f"Only 'pypi' can omit the repository URL.")
            if not username or not password:
                username, password = get_credentials(
                    username=username,
                    password=password,
                    url=url
                )
        elif not self.args.repository_url:
            raise ValueError(
                f"Repository '{self.args.repository_name}' not found in .pypirc. "
                f"Please provide --repository-url or add required info in .pypirc"
            )
        else:
            url = self.args.repository_url
            username, password = get_credentials(username=self.args.username,
                                                 password=self.args.password,
                                                 url=url)
        return url, username, password

    @staticmethod
    def check_require_package(cython: bool):
        required_packages = ["build", "twine", "tomlkit"]
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

    def resolve_package_dir(self, toml_config: TOMLDocument) -> Path:
        package_dir = self.args.project_dir / toml_config["project"]["name"].replace("-", "_")
        if self.args.package_dir is not None:
            package_dir = self.args.package_dir
        else:
            pkg_dir_candidates = []

            # Safely extract 'packages.find.where'
            where = (
                toml_config
                .get("tool", {})
                .get("setuptools", {})
                .get("packages", {})
                .get("find", {})
                .get("where")
            )
            if where and isinstance(where, list):
                pkg_dir_candidates.append(where[0])
            elif where is not None:
                logger.warning("'tool.setuptools.packages.find.where' is not a list; skipping.")

            # Safely extract first value from 'package-dir' dict
            package_dir_map = (
                toml_config
                .get("tool", {})
                .get("setuptools", {})
                .get("package-dir")
            )
            if package_dir_map and isinstance(package_dir_map, dict) and package_dir_map:
                first_value = next(iter(package_dir_map.values()))
                if isinstance(first_value, str):
                    pkg_dir_candidates.append(first_value)
                else:
                    logger.warning("'tool.setuptools.package-dir' values should be strings; skipping.")

            if len(set(pkg_dir_candidates)) > 1:
                raise ValueError(
                    f"Package directory from toml are not the same: {pkg_dir_candidates}. "
                    f"'tool.setuptools.packages.find.where' and 'tool.setuptools.package-dir' "
                    f"must point at the same directory. Fix {self.args.project_dir / 'pyproject.toml'}, "
                    f"or pass --package-dir to override both."
                )
            elif len(pkg_dir_candidates) == 0:
                logger.warning(f"No entry point find, use the default directory: {package_dir}")
            else:
                package_dir = self.args.project_dir / pkg_dir_candidates[0]

        if not package_dir.exists():
            raise FileNotFoundError(f"Failed to resolve package directory, directory not found: {package_dir}")
        return package_dir

    @staticmethod
    def check_wheel_no_source_leak(dist_dir: Path):
        """Inspect built wheels and refuse to continue if any source or
        intermediate file leaked in. A Cython build should ship only compiled
        extensions (.pyd/.so) plus __init__.py; anything else means a module
        failed to cythonize or was excluded. Raises ValueError on a leak."""
        wheels = sorted(dist_dir.glob("*.whl"))
        if not wheels:
            raise ValueError(f"No wheel found under {dist_dir} to inspect for source leaks")

        source_suffixes = {".c", ".cpp", ".cxx", ".pyx", ".pxd", ".h", ".hpp", ".pdb"}
        leaks = {}
        for wheel in wheels:
            found = []
            with zipfile.ZipFile(wheel) as zf:
                for name in zf.namelist():
                    if name.endswith("/"):
                        continue
                    # Wheel metadata is not importable package content.  Do not skip
                    # .data/purelib or .data/platlib: installers move those files into
                    # site-packages, so source files there are leaks too.
                    if ".dist-info/" in name:
                        continue
                    base = name.rsplit("/", 1)[-1]
                    suffix = Path(base).suffix.lower()
                    if suffix == ".py" and base.lower() != "__init__.py":
                        found.append(name)
                    elif suffix in source_suffixes:
                        found.append(name)
            if found:
                leaks[wheel.name] = found

        if leaks:
            detail = "\n".join(
                f"  {w}:\n" + "\n".join(f"      - {f}" for f in files)
                for w, files in leaks.items()
            )
            raise ValueError(
                "Source leak detected in built wheel(s) - refusing to upload.\n"
                "A Cython build should contain only compiled extensions (.pyd/.so) "
                "plus __init__.py, but these source/intermediate files were found:\n"
                f"{detail}\n"
                "Likely a module failed to cythonize or was excluded from the build."
            )
        logger.info(f"Wheel source-leak check passed for: {[w.name for w in wheels]}")

    def cleanup_build_files(self):
        logger.info('Deleting build, dist and egg-info files after deployment')
        project_dir = Path(self.config.project_dir)
        # setuptools writes *.egg-info next to the top-level packages, i.e. under source_root.
        egg_root = project_dir / self.config.source_root
        # Cython intermediates are generated under build/cython. Never recursively
        # remove *.c from the package tree because projects may own those sources.
        if self.config.keep_dist:
            logger.info(f"--keep-dist: leaving {project_dir / 'dist'} in place")
        else:
            shutil.rmtree(project_dir / 'dist', ignore_errors=True)
        shutil.rmtree(project_dir / 'build', ignore_errors=True)
        shutil.rmtree(egg_root / f'{self.config.package_name}.egg-info', ignore_errors=True)
        egg_info_name = self.config.package_name.replace("-", "_")
        shutil.rmtree(egg_root / f'{egg_info_name}.egg-info', ignore_errors=True)
        if not self.setup_file_exist:
            (project_dir / "setup.py").unlink(missing_ok=True)

    def check_git_status(self):
        logger.info("Checking git status, --porcelain to make sure git repo is clean")
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self.config.project_dir,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise IOError(f"Git command failed: {result.stderr.strip()}")
        if result.stdout.strip():
            raise IOError(f"Git repo is NOT clean: \n{result.stdout}")

    @staticmethod
    def git_push(project_dir: Path, new_version: str, files: list, dry_run: bool = False):
        paths = [str(f) for f in files]
        try:
            if dry_run:
                logger.info(f"DRY RUN: Would run: git add -- {' '.join(paths)}")
                logger.info(f"DRY RUN: Would run: git commit -m 'Bump version to {new_version}'")
                tag_name = f"v{new_version}"
                logger.info(f"DRY RUN: Would create Git tag: {tag_name}")
                logger.info("DRY RUN: Would run: git push --follow-tags")
                logger.info('DRY RUN: Git push simulation completed')
            else:
                subprocess.check_output(['git', 'add', '--', *paths], stderr=subprocess.STDOUT, cwd=project_dir)
                subprocess.check_output(['git', 'commit', '-m', f'Bump version to {new_version}'], stderr=subprocess.STDOUT, cwd=project_dir)
                tag_name = f"v{new_version}"

                # Check if the tag already exists
                result = subprocess.run(['git', 'tag', '-l', tag_name], capture_output=True, text=True, cwd=project_dir)
                if result.stdout.strip():
                    logger.warning(f"Warning: Git tag {tag_name} already exists, skipping tag creation")
                else:
                    subprocess.check_output(['git', 'tag', '-a', tag_name, '-m', f'Release {tag_name}'], stderr=subprocess.STDOUT, cwd=project_dir)
                    logger.info(f"Created Git tag: {tag_name}")

                subprocess.check_output(['git', 'push', '--follow-tags'], stderr=subprocess.STDOUT, cwd=project_dir)
                logger.info('Pushing to github')
        except subprocess.CalledProcessError as ex:
            logger.error(f"Git command failed: {ex.output.decode()}")
            logger.warning('Failed to push bump version commit. Please push manually.')
            raise
        except Exception as ex:
            logger.error(f"Unexpected error: {ex}")
            logger.warning('Failed to push bump version commit. Please push manually.')
            raise

    @staticmethod
    def git_roll_back(project_dir: Path, files: list):
        """Revert the version bump: only the files bump_version() wrote are touched."""
        if not files:
            return
        paths = [str(f) for f in files]
        try:
            subprocess.check_output(['git', 'restore', '--staged', '--worktree', '--', *paths],
                                    stderr=subprocess.STDOUT, cwd=project_dir)
            logger.info(f"Restored {', '.join(Path(p).name for p in paths)}")
        except subprocess.CalledProcessError as ex:
            logger.error(f"Git command failed: {ex.output.decode()}")
        except Exception as ex:
            logger.error(f"Unexpected error: {ex}")
            logger.warning('Failed to roll back changes. Please roll back manually.')

    @staticmethod
    def get_upload_strategy(config) -> Upload:
        return TwineUpload()


def main(argv=None):
    sys.exit(0 if PackageDeploy(argv).deploy() else 1)


if __name__ == "__main__":
    main()
