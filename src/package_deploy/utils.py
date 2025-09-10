import os
import re
import sys
import toml
import tomlkit
import logging
import getpass
import configparser
from pathlib import Path
from typing import Dict, Any, Optional


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def is_uv_venv() -> bool:
    """Detect if the current virtual environment was created by uv (supports versioned marker)."""
    if not hasattr(sys, 'prefix') or not sys.prefix:
        return False
    pyvenv_cfg = Path(sys.prefix) / "pyvenv.cfg"
    if not pyvenv_cfg.exists():
        return False
    try:
        with open(pyvenv_cfg, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.lower().startswith("uv ="):
                    logger.info("Detected uv-managed Python.")
                    return True
    except Exception:
        pass
    return False

def setup_uv_compatibility():
    if is_uv_venv():
        logger.info("Setting PIP_USE_VIRTUALENV=1 for build compatibility.")
        os.environ["PIP_USE_VIRTUALENV"] = "1"
        return True
    else:
        return False


def create_sample_pyproject_toml():
    """创建示例 pyproject.toml 文件"""
    sample_config = {
        "build-system": {
            "requires": ["setuptools>=45", "wheel", "setuptools_scm[toml]>=6.2"],
            "build-backend": "setuptools.build_meta"
        },
        "project": {
            "name": "my-awesome-package",
            "version": "0.1.0",
            "description": "An awesome Python package",
            "authors": [{"name": "Your Name", "email": "your.email@example.com"}],
            "dependencies": [],
            "requires-python": ">=3.8",
            "classifiers": [
                "Development Status :: 3 - Alpha",
                "Intended Audience :: Developers",
                "License :: OSI Approved :: MIT License",
                "Programming Language :: Python :: 3.8",
                "Programming Language :: Python :: 3.9",
                "Programming Language :: Python :: 3.10",
                "Programming Language :: Python :: 3.11",
            ]
        },
        "tool": {
            "setuptools": {
                "package-dir": {"": "src"},
                "packages": {"find": {"where": ["src"]}}
            }
        }
    }

    with open("pyproject.toml", "w", encoding="utf-8") as f:
        toml.dump(sample_config, f)
    print("Created sample pyproject.toml")


def get_credentials(args) -> tuple[Optional[str], Optional[str]]:
    """
    获取认证凭据，优先级：命令行参数 > 环境变量 > .pypirc 文件 > 交互输入

    Args:
        args: 命令行参数对象

    Returns:
        tuple: (username, password/token) 元组

    Raises:
        ValueError: 当密码为空且需要部署时
    """
    username = args.username
    password = args.password
    is_pypi = args.repository_name and "pypi" in args.repository_name.lower()
    force_interactive = args.interactive

    # PyPI 和 TestPyPI 现在主要使用 API Token
    if is_pypi:
        logger.info(" Detected PyPI repository - API tokens are recommended over passwords")

    # 如果强制交互模式，直接进入交互输入
    if not args.dry_run and (force_interactive or (not username and not password)):
        logger.info(f"\n Repository Authentication Required")
        if is_pypi:
            logger.info(f"PyPI Repository: https://pypi.org/")
            logger.info(" Tip: Use API tokens instead of passwords for better security")
        else:
            logger.info(f"Repository: {args.repository_url}")
        logger.info("-" * 60)

    # 用户名输入
    if is_pypi:
        logger.info("For PyPI API tokens, use '__token__' as username")
        username_input = input("Username (default: __token__): ").strip()
        username = username_input if username_input else "__token__"
    else:
        username_input = input("Username (default: admin): ").strip()
        username = username_input if username_input else "admin"

    if username:
        logger.info(f"Using username: {username}")

    # 密码/Token 输入
    if username == "__token__":
        password = getpass.getpass("API Token (pypi-...): ")
    else:
        password = getpass.getpass("Password: ")

    if not password:
        logger.info(f"Password/Token cannot be empty")
        raise ValueError("Password/Token cannot be empty")

    return username, password


def parse_prerelease(version: str):
    # Match the pattern: numbers.numbers.numbers + optional prerelease type + optional version
    pattern = r'^(\d+)\.(\d+)\.(\d+)([abc]|rc)?(\d*)$'
    match = re.match(pattern, version)

    if match:
        major = int(match.group(1))
        minor = int(match.group(2))
        patch = int(match.group(3))
        prerelease_type = match.group(4)  # None if no prerelease

        if prerelease_type and match.group(5):
            prerelease_version = int(match.group(5))
        elif prerelease_type:
            prerelease_version = 1
        else:
            prerelease_version = None

        return {
            'major': major,
            'minor': minor,
            'patch': patch,
            'prerelease_type': prerelease_type,
            'prerelease_version': prerelease_version,
            'has_prerelease': prerelease_type is not None
        }
    else:
        raise ValueError(f"Invalid version format: {version}")


def get_pypirc_info():
    """
    Read and parse .pypirc file from user's home directory.
    Returns a dictionary with repository configurations.
    """
    # Get the path to .pypirc file
    home_dir = Path.home()
    pypirc_path = home_dir / '.pypirc'

    if not pypirc_path.exists():
        raise FileNotFoundError(f"No .pypirc file found at {pypirc_path}")

    # Parse the configuration file
    config = configparser.ConfigParser()

    try:
        config.read(pypirc_path)

        # Extract information
        pypirc_info = {}

        # Get index servers if available
        if config.has_section('distutils') and config.has_option('distutils', 'index-servers'):
            index_servers = config.get('distutils', 'index-servers').split()
            pypirc_info['index_servers'] = index_servers

        # Get repository configurations
        repositories = {}
        for section_name in config.sections():
            if section_name != 'distutils':
                repo_config = {}
                for option in config.options(section_name):
                    repo_config[option] = config.get(section_name, option)
                repositories[section_name] = repo_config
        if not repositories:
            raise ValueError(f"No repositories configuration found in {pypirc_path}")

        pypirc_info['repositories'] = repositories
        return pypirc_info
    except Exception as e:
        print(f"Error reading .pypirc file: {e}")
        return None


def load_config(pyproject_path: Path) -> Dict[str, Any]:
    """load pyproject.toml"""
    if not pyproject_path.exists():
        raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")

    with open(pyproject_path, "r", encoding="utf-8") as f:
        content = f.read()
    config = tomlkit.parse(content)
    return config


def save_config(config, pyproject_path: Path):
    with open(pyproject_path, 'w', encoding='utf-8') as f:
        f.write(tomlkit.dumps(config))
