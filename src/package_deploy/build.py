import os
import sys
from typing import Optional
from dataclasses import dataclass

import toml
import subprocess
from pathlib import Path
from abc import ABC, abstractmethod

from package_deploy.utils import logger, save_config


@dataclass
class DeployConfig:
    package_name: str
    project_dir: Path
    pyproject_path: Path
    version_type: str
    use_cython: bool
    repository_name: str
    repository_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    dry_run: bool = False


class BuildStrategy(ABC):

    @abstractmethod
    def build(self, config: DeployConfig, work_dir: Path) -> bool:
        pass


class StandardBuildStrategy(BuildStrategy):

    def build(self, config: DeployConfig, project_dir: Path) -> bool:
        """使用标准 build 构建"""
        try:
            cmd = [sys.executable, "-m", "build", "--wheel"]
            logger.info(f"Running: {' '.join(cmd)}")

            result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_dir)

            if result.returncode != 0:
                raise ValueError(f"Build failed: {result.stderr}")

            logger.info("Standard build completed successfully")
            return True

        except Exception as e:
            logger.error(f"Build error: {e}")
            return False


class CythonBuildStrategy(BuildStrategy):

    def build(self, config: DeployConfig, project_dir: Path) -> bool:
        try:
            self._setup_cython_build(project_dir)
            self.create_setup_py_for_cython()

            cmd = [sys.executable, "-m", "build", str(project_dir)]
            logger.info(f"Running Cython build: {' '.join(cmd)}")

            env = os.environ.copy()
            env['CYTHONIZE'] = '1'

            result = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=project_dir)

            if result.returncode != 0:
                logger.error(f"Cython build failed: {result.stderr}")
                return False

            logger.info("Cython build completed successfully")
            return True

        except Exception as e:
            logger.error(f"Cython build error: {e}")
            return False

    def _setup_cython_build(self, project_dir: Path):
        pyproject_path = project_dir / "pyproject.toml"
        if pyproject_path.exists():
            config = toml.load(pyproject_path)

            # Add Cython build dependency
            if 'build-system' not in config:
                config['build-system'] = {}

            if 'requires' not in config['build-system']:
                config['build-system']['requires'] = []

            cython_deps = ['setuptools', 'wheel', 'Cython']
            requires = config['build-system']['requires']
            for dep in cython_deps:
                if not any(req.startswith(dep) for req in requires):
                    config['build-system']['requires'].append(dep)

            if 'build-backend' not in config['build-system']:
                config['build-system']['build-backend'] = 'setuptools.build_meta'

            save_config(config, pyproject_path)

    def create_setup_py_for_cython(self):
        setup_py_content = '''
        import os
        from setuptools import setup, find_packages
        from Cython.Build import cythonize
        import glob
        py_files = glob.glob("src/**/*.py", recursive=True)
        py_files = [f for f in py_files if not f.endswith("__init__.py")]
    
        setup(
            packages=find_packages(where="src"),
            package_dir={"": "src"},
            ext_modules=cythonize(
                py_files,
                compiler_directives={"language_level": "3"},
            ),
            zip_safe=False,
        )
        '''
        with open('setup.py', 'w') as f:
            f.write(setup_py_content)
