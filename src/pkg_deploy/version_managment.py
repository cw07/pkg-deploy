import logging
from pathlib import Path
from typing import Optional

from tomlkit import TOMLDocument

from .utils import parse_prerelease, load_config, save_config


logger = logging.getLogger(__name__)


class VersionManager:
    """Version Manager"""

    def __init__(self, pyproject_path: Path, toml_config: TOMLDocument):
        self.pyproject_path = pyproject_path
        self.toml_config = toml_config

    def get_current_version(self) -> str:
        return str(self.toml_config['project']['version'])

    # Pre-release stages in ascending order. A bump may only move forward through them.
    _PRERELEASE_STAGES = {'alpha': 'a', 'beta': 'b', 'rc': 'rc'}
    _STAGE_ORDER = ['a', 'b', 'rc']

    @staticmethod
    def resolve_new_version(current_version: str, version_type: str) -> str:
        """Compute the next version.

        Rules:
          final   + patch/minor/major -> ordinary bump            1.2.4    -> 1.2.5
          final   + alpha/beta/rc     -> next patch, new cycle    1.2.4    -> 1.2.5a1
          pre     + same stage        -> increment                1.2.5a1  -> 1.2.5a2
          pre     + later stage       -> switch, reset to 1       1.2.5a2  -> 1.2.5b1
          pre     + earlier stage     -> error                    1.2.5rc1 -> alpha: refused
          pre     + patch             -> finalise (drop suffix)   1.2.5rc1 -> 1.2.5
          pre     + minor/major       -> abandon cycle, bump      1.2.5rc1 -> 1.3.0
        A pre-release must sit on a version that has not shipped yet, because PEP 440
        sorts 1.2.4a1 BEFORE 1.2.4 - publishing it after 1.2.4 would be invisible to pip.
        """
        info = parse_prerelease(current_version)
        major, minor, patch = info['major'], info['minor'], info['patch']
        stage, number = info['prerelease_type'], info['prerelease_version']

        if version_type == 'patch':
            if stage is None:
                patch += 1
            stage = None
        elif version_type == 'minor':
            minor, patch, stage = minor + 1, 0, None
        elif version_type == 'major':
            major, minor, patch, stage = major + 1, 0, 0, None
        elif version_type in VersionManager._PRERELEASE_STAGES:
            wanted = VersionManager._PRERELEASE_STAGES[version_type]
            order = VersionManager._STAGE_ORDER
            if stage is None:
                patch += 1
                stage, number = wanted, 1
            elif stage == wanted:
                number += 1
            elif order.index(wanted) > order.index(stage):
                stage, number = wanted, 1
            else:
                raise ValueError(
                    f"Cannot go from {current_version} to {version_type}: pre-release stages "
                    f"only move forward (alpha -> beta -> rc). Use --new-version to force a value."
                )
        else:
            raise ValueError(f"Invalid version type: {version_type}")

        return f"{major}.{minor}.{patch}" + (f"{stage}{number}" if stage else "")

    def bump_version(self, version_type: str, new_version: Optional[str]=None, dry_run: bool = False) -> str:
        current_version = self.get_current_version()
        if new_version is None:
            new_version = self.resolve_new_version(current_version, version_type)
        
        if not dry_run:
            # Update pyproject.toml
            self.toml_config['project']['version'] = new_version
            save_config(self.toml_config, self.pyproject_path)
            # Update files configured under [tool.bumpversion.file]
            self.update_bumpversion_files(current_version, new_version)

        logger.info(f"Version bumped from {current_version} to {new_version}")
        return new_version

    def update_bumpversion_files(self, current_version: str, new_version: str) -> None:
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