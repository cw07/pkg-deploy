import os
import sys
import copy
import logging
import textwrap
import subprocess
from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass
from abc import ABC, abstractmethod
from tomlkit.toml_document import TOMLDocument

from package_deploy.utils import save_config, is_uv_venv, ensure_uv_installed


logger = logging.getLogger(__name__)


@dataclass
class DeployConfig:
    package_name: str
    project_dir: Path
    pyproject_path: Path
    version_type: str
    new_version: str
    use_cython: bool
    is_uv_venv: bool
    repository_name: str
    repository_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    dry_run: bool = False


class BuildStrategy(ABC):

    @staticmethod
    def build_cmd():
        if is_uv_venv():
            ensure_uv_installed()
            cmd = ["uv", "build", "--wheel"]
        else:
            cmd = [sys.executable, "-m", "build", "--wheel"]
        return cmd

    @abstractmethod
    def build(self, config: DeployConfig, toml_config: TOMLDocument) -> bool:
        pass


class StandardBuildStrategy(BuildStrategy):

    def build(self, config: DeployConfig, toml_config: TOMLDocument) -> bool:
        cmd = self.build_cmd()
        logger.info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=config.project_dir)
        if result.returncode != 0:
           raise ValueError(f"Build failed, \nstdout: {result.stdout}\nstderr: {result.stderr}")
        logger.info("Standard build completed successfully")
        return True

class CythonBuildStrategy(BuildStrategy):

    def build(self, config: DeployConfig, toml_config: TOMLDocument) -> bool:
        try:
            self.prepare_pyproject_for_cython_build(config.project_dir, toml_config)
            self.create_setup_py_for_cython(toml_config, config.project_dir)
            cmd = self.build_cmd()
            logger.info(f"Running Cython build: {' '.join(cmd)}")
            env = os.environ.copy()
            env['CYTHONIZE'] = '1'
            result = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=config.project_dir)
            if result.returncode != 0:
                raise ValueError(f"Cython build failed, \nstdout: {result.stdout}\nstderr: {result.stderr}")
            logger.info("Cython build completed successfully")
            return True
        except Exception as e:
            logger.error(f"Cython build error: {e}")
            return False
        finally:
            self.restore_pyproject_toml(project_dir=config.project_dir, original_config=toml_config)

    @staticmethod
    def prepare_pyproject_for_cython_build(project_dir: Path, toml_config: Dict):
        pyproject_path = project_dir / "pyproject.toml"
        if pyproject_path.exists():
            new_config = copy.deepcopy(toml_config)

            # Add Cython build dependency
            if 'build-system' not in new_config:
                new_config['build-system'] = {}

            if 'requires' not in new_config['build-system']:
                new_config['build-system']['requires'] = []

            cython_deps = ['setuptools', 'Cython']
            requires = new_config['build-system']['requires']
            for dep in cython_deps:
                if not any(req.startswith(dep) for req in requires):
                    new_config['build-system']['requires'].append(dep)

            if 'build-backend' not in new_config['build-system'] or new_config['build-system'][
                'build-backend'] != 'setuptools.build_meta':
                new_config['build-system']['build-backend'] = 'setuptools.build_meta'
            save_config(new_config, pyproject_path)

    @staticmethod
    def restore_pyproject_toml(project_dir: Path, original_config: Dict):
        pyproject_path = project_dir / "pyproject.toml"
        if original_config:
            save_config(original_config, pyproject_path)
            logger.info("Restored original pyproject.toml")

    @staticmethod  # cw07*
    def create_setup_py_for_cython(toml_config: Dict, project_dir: Path):
        author_names = ", ".join([p["name"] for p in toml_config["project"]["authors"]])
        author_emails = ", ".join(p["email"] for p in toml_config["project"]["authors"])
        if "scripts" in toml_config["project"]:
            entry_points = ", ".join(f"{k}={v}" for k, v in toml_config["project"]["scripts"].items())
        else:
            entry_points = ""
        setup_py_content = textwrap.dedent(f'''
        import os
        import glob
        from Cython.Build import cythonize
        from setuptools import setup, find_packages
        from setuptools.dist import Distribution
        from setuptools.command.build_py import build_py as _build_py
    
        py_files = glob.glob("src/**/**/*.py", recursive=True)
        py_files = [f for f in py_files if not f.endswith("__init__.py")]
    
        class build_py(_build_py):
            def find_package_modules(self, package, package_dir):
                modules = super().find_package_modules(package, package_dir)
                if self.distribution.ext_modules:
                    # Get the list of compiled module names
                    compiled_modules = {{ext.name for ext in self.distribution.ext_modules}}
                    # Filter out the modules that are compiled
                    modules = [
                        (pkg, mod, file) for (pkg, mod, file) in modules
                        if f"{{pkg}}.{{mod}}" not in compiled_modules
                    ]
                return modules
    
        class BinaryDistribution(Distribution):
            def has_ext_modules(self):
                return True
    
        setup(
            name="{toml_config["project"]["name"]}",
            version="{toml_config["project"]["version"]}",
            author="{author_names}",
            author_email="{author_emails}",
            description="{toml_config["project"]["description"]}",
            python_requires="{toml_config["project"]["requires-python"]}",
            install_requires={toml_config["project"]["dependencies"]},
            entry_points={{
                'console_scripts': [{entry_points}]
            }},
            packages=find_packages(where="src"),
            package_dir={{"": "src"}},
            include_package_data=True,
            ext_modules=cythonize(
                py_files,
                compiler_directives={{'language_level': "3"}},
            ),
            distclass=BinaryDistribution,
            setup_requires=["cython>=3.1"],
            cmdclass={{'build_py': build_py}},
            zip_safe=False
        )
        ''').strip()

        with open(project_dir / "setup.py", 'w') as f:
            f.write(setup_py_content)
