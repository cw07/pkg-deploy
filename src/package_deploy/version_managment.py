import tomlkit
from pathlib import Path
from typing import Dict, Any

from package_deploy.utils import parse_prerelease, logger


class VersionManager:
    """Version Manager"""

    def __init__(self, pyproject_path: Path):
        self.pyproject_path = pyproject_path
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """加载 pyproject.toml 配置"""
        if not self.pyproject_path.exists():
            raise FileNotFoundError(f"pyproject.toml not found at {self.pyproject_path}")

        with open(self.pyproject_path, "r", encoding="utf-8") as f:
            content = f.read()
        doc = tomlkit.parse(content)
        return doc

    def _save_config(self):
        """保存配置到 pyproject.toml"""
        with open(self.pyproject_path, 'w', encoding='utf-8') as f:
            f.write(tomlkit.dumps(self.config))

    def get_current_version(self) -> str:
        """获取当前版本"""
        return self.config['project']['version']

    def bump_version(self, version_type: str) -> str:
        current_version = self.get_current_version()

        version_info = parse_prerelease(current_version)
        major = version_info['major']
        minor = version_info['minor']
        patch = version_info['patch']
        prerelease_type = version_info['prerelease_type']
        prerelease_version = version_info['prerelease_version']
        has_prerelease = version_info['has_prerelease']

        # Handle version bumping
        if version_type == 'patch':
            if has_prerelease:
                # Remove prerelease, keep same patch number
                prerelease_type = None
                prerelease_version = 1
            else:
                patch += 1
        elif version_type == 'minor':
            minor += 1
            patch = 0
            prerelease_type = None
            prerelease_version = 1
        elif version_type == 'major':
            major += 1
            minor = 0
            patch = 0
            prerelease_type = None
            prerelease_version = 1
        elif version_type == 'alpha':
            if has_prerelease:
                if prerelease_type == 'a':
                    prerelease_version += 1
                else:
                    # Switch to alpha, increment prerelease version
                    prerelease_type = 'a'
                    prerelease_version = 1
            else:
                # Add alpha to current version
                prerelease_type = 'a'
                prerelease_version = 1
        elif version_type == 'beta':
            if has_prerelease:
                if prerelease_type == 'a':
                    # alpha → beta
                    prerelease_type = 'b'
                    prerelease_version = 1
                elif prerelease_type == 'b':
                    prerelease_version += 1
                else:
                    # rc → beta (unusual, but handle it)
                    prerelease_type = 'b'
                    prerelease_version = 1
            else:
                # Add beta to current version
                prerelease_type = 'b'
                prerelease_version = 1
        elif version_type == 'rc':
            if has_prerelease:
                if prerelease_type in ['a', 'b']:
                    # alpha/beta → rc
                    prerelease_type = 'rc'
                    prerelease_version = 1
                elif prerelease_type == 'rc':
                    prerelease_version += 1
            else:
                # Add rc to current version
                prerelease_type = 'rc'
                prerelease_version = 1
        else:
            raise ValueError(f"Invalid version type: {version_type}")

        # Build new version string
        if prerelease_type:
            new_version = f"{major}.{minor}.{patch}{prerelease_type}{prerelease_version}"
        else:
            new_version = f"{major}.{minor}.{patch}"

        self.config['project']['version'] = new_version
        self._save_config()

        logger.info(f"Version bumped from {current_version} to {new_version}")
        return new_version
