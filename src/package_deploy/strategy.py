import os
import sys
from dataclasses import dataclass
from typing import Optional

import toml
import subprocess
from pathlib import Path
from abc import ABC, abstractmethod


from package_deploy.utils import logger


@dataclass
class DeployConfig:
    project_dir: Path
    package_name: str
    version_type: str
    use_cython: bool
    repository_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    dry_run: bool = False


class BuildStrategy(ABC):
    """构建策略抽象基类"""

    @abstractmethod
    def build(self, config: DeployConfig, work_dir: Path) -> bool:
        """执行构建"""
        pass


class StandardBuildStrategy(BuildStrategy):
    """标准构建策略"""

    def build(self, config: DeployConfig, project_dir: Path) -> bool:
        """使用标准 build 构建"""
        try:
            cmd = [sys.executable, "-m", "build", str(project_dir)]
            logger.info(f"Running: {' '.join(cmd)}")

            result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_dir)

            if result.returncode != 0:
                logger.error(f"Build failed: {result.stderr}")
                return False

            logger.info("Standard build completed successfully")
            return True

        except Exception as e:
            logger.error(f"Build error: {e}")
            return False


class CythonBuildStrategy(BuildStrategy):
    """Cython 构建策略"""

    def build(self, config: DeployConfig, project_dir: Path) -> bool:
        """使用 Cython 编译构建"""
        try:
            # 检查是否有 setup.py 或需要创建 Cython 构建配置
            self._setup_cython_build(project_dir)

            # 使用 build 构建，但添加 Cython 支持
            cmd = [sys.executable, "-m", "build", str(project_dir)]
            logger.info(f"Running Cython build: {' '.join(cmd)}")

            env = os.environ.copy()
            env['CYTHONIZE'] = '1'  # 环境变量指示使用 Cython

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
        """设置 Cython 构建配置"""
        pyproject_path = project_dir / "pyproject.toml"
        if pyproject_path.exists():
            config = toml.load(pyproject_path)

            # 添加 Cython 构建依赖
            if 'build-system' not in config:
                config['build-system'] = {}

            if 'requires' not in config['build-system']:
                config['build-system']['requires'] = []

            cython_deps = ['setuptools', 'wheel', 'Cython']
            for dep in cython_deps:
                if dep not in config['build-system']['requires']:
                    config['build-system']['requires'].append(dep)

            if 'build-backend' not in config['build-system']:
                config['build-system']['build-backend'] = 'setuptools.build_meta'

            # 保存修改
            with open(pyproject_path, 'w', encoding='utf-8') as f:
                toml.dump(config, f)


