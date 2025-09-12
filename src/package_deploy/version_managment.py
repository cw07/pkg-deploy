import re
import logging
from pathlib import Path

from package_deploy.utils import parse_prerelease, load_config, save_config


logger = logging.getLogger(__name__)


class VersionManager:
    """Version Manager"""

    def __init__(self, pyproject_path: Path):
        self.pyproject_path = pyproject_path
        self.toml_config = load_config(pyproject_path)

    def get_current_version(self) -> str:
        return self.toml_config['project']['version']

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
            prerelease_type = None
            patch += 1
        elif version_type == 'minor':
            minor += 1
            patch = 0
            prerelease_type = None
        elif version_type == 'major':
            major += 1
            minor = 0
            patch = 0
            prerelease_type = None
        elif version_type == 'alpha':
            if has_prerelease:
                if prerelease_type == 'a':
                    prerelease_version += 1
                else:
                    prerelease_type = 'a'
                    prerelease_version = 1
            else:
                prerelease_type = 'a'
                prerelease_version = 1
        elif version_type == 'beta':
            if has_prerelease:
                if prerelease_type == 'a':
                    prerelease_type = 'b'
                    prerelease_version = 1
                elif prerelease_type == 'b':
                    prerelease_version += 1
                else:
                    prerelease_type = 'b'
                    prerelease_version = 1
            else:
                prerelease_type = 'b'
                prerelease_version = 1
        elif version_type == 'rc':
            if has_prerelease:
                if prerelease_type in ['a', 'b']:
                    prerelease_type = 'rc'
                    prerelease_version = 1
                elif prerelease_type == 'rc':
                    prerelease_version += 1
            else:
                prerelease_type = 'rc'
                prerelease_version = 1
        else:
            raise ValueError(f"Invalid version type: {version_type}")

        # Build new version string
        if prerelease_type:
            new_version = f"{major}.{minor}.{patch}{prerelease_type}{prerelease_version}"
        else:
            new_version = f"{major}.{minor}.{patch}"

        # Update pyproject.toml
        self.toml_config['project']['version'] = new_version
        save_config(self.toml_config, self.pyproject_path)

        # ALSO update files configured under [tool.bumpversion.file]
        self._update_bumpversion_files(current_version, new_version)

        logger.info(f"Version bumped from {current_version} to {new_version}")
        return new_version

    def _update_bumpversion_files(self, current_version: str, new_version: str):
        """Update files configured in [tool.bumpversion.file] section."""
        bumpversion_config = self.toml_config.get('tool', {}).get('bumpversion', {})
        files = bumpversion_config.get('file', [])

        # If 'file' is a single dict, make it a list
        if isinstance(files, dict):
            files = [files]

        for file_config in files:
            filename = file_config.get('filename')
            if filename == "pyproject.toml":
                continue
            search = file_config.get('search', '{current_version}')
            replace = file_config.get('replace', '{new_version}')

            if not filename:
                logger.warning("Skipping bumpversion file entry with no 'filename'")
                continue

            file_path = Path(filename)
            if not file_path.exists():
                logger.warning(f"File {filename} not found, skipping.")
                continue

            # Read file content
            content = file_path.read_text(encoding='utf-8')

            # Replace placeholders
            old_str = search.format(current_version=current_version)
            new_str = replace.format(new_version=new_version)

            # Escape for literal string replacement (not regex)
            if old_str not in content:
                logger.warning(f"Search pattern '{old_str}' not found in {filename}, skipping.")
                continue

            new_content = content.replace(old_str, new_str)

            # Write back only if changed
            if new_content != content:
                file_path.write_text(new_content, encoding='utf-8')
                logger.info(f"Updated {filename}: '{old_str}' → '{new_str}'")
            else:
                logger.debug(f"No changes needed in {filename}")