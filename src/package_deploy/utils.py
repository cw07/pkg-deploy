import os
import re
import toml
import logging
from typing import Optional


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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
    import getpass
    import configparser
    from pathlib import Path

    username = args.username
    password = args.password
    is_nexus = args.repository_url and 'nexus' in args.repository_url.lower()
    is_pypi = not args.repository_url or 'pypi.org' in args.repository_url.lower()
    is_test_pypi = args.repository_url and 'test.pypi.org' in args.repository_url.lower()
    force_interactive = args.interactive

    # PyPI 和 TestPyPI 现在主要使用 API Token
    if is_pypi or is_test_pypi:
        logger.info("📦 Detected PyPI repository - API tokens are recommended over passwords")

    # 如果强制交互模式，直接进入交互输入
    if force_interactive and not args.dry_run:
        if not username and not password:
            logger.info(f"\n🔐 Repository Authentication Required")
            if is_pypi:
                logger.info(f"PyPI Repository: https://pypi.org/")
                logger.info("💡 Tip: Use API tokens instead of passwords for better security")
            elif is_test_pypi:
                logger.info(f"TestPyPI Repository: https://test.pypi.org/")
                logger.info("💡 Tip: Use API tokens instead of passwords for better security")
            elif is_nexus:
                logger.info(f"Nexus Repository: {args.repository_url}")
            else:
                logger.info(f"Repository: {args.repository_url}")
            logger.info("-" * 60)

            # 用户名输入
            if is_pypi or is_test_pypi:
                logger.info("For PyPI API tokens, use '__token__' as username")
                username_input = input("Username (default: __token__): ").strip()
                username = username_input if username_input else "__token__"
            elif is_nexus:
                username_input = input("Username (default: admin): ").strip()
                username = username_input if username_input else "admin"
            else:
                username = input("Username: ").strip()

            if username:
                logger.info(f"Using username: {username}")

            # 密码/Token 输入
            if username == "__token__":
                password = getpass.getpass("API Token (pypi-...): ")
            else:
                password = getpass.getpass("Password: ")

            if not password:
                logger.error("Password/Token cannot be empty")
                raise ValueError("Password/Token is required for deployment")

            logger.info("-" * 60)
            return username, password

    # 1. 检查环境变量
    if not username:
        if is_pypi or is_test_pypi:
            username = os.environ.get('TWINE_USERNAME') or os.environ.get('PYPI_USERNAME')
        else:
            username = os.environ.get('TWINE_USERNAME') or os.environ.get('NEXUS_USERNAME')

    if not password:
        if is_pypi or is_test_pypi:
            password = os.environ.get('TWINE_PASSWORD') or os.environ.get('PYPI_TOKEN')
        else:
            password = os.environ.get('TWINE_PASSWORD') or os.environ.get('NEXUS_PASSWORD')

    # 2. 检查 .pypirc 文件
    if not username or not password:
        pypirc_path = Path.home() / '.pypirc'
        if pypirc_path.exists():
            config = configparser.ConfigParser()
            config.read(pypirc_path)

            # 根据仓库 URL 确定配置节
            section_name = 'pypi'
            if args.repository_url:
                if 'nexus' in args.repository_url.lower():
                    section_name = 'nexus'
                elif 'test.pypi.org' in args.repository_url.lower():
                    section_name = 'testpypi'

            if config.has_section(section_name):
                if not username and config.has_option(section_name, 'username'):
                    username = config.get(section_name, 'username')
                if not password and config.has_option(section_name, 'password'):
                    password = config.get(section_name, 'password')

    # 3. 如果仍然缺少凭据且需要部署，交互式输入
    if args.repository_url and not args.dry_run and (not username or not password):
        if is_nexus:
            logger.info(f"\n🔐 Nexus Repository Authentication Required")
            logger.info(f"Repository: {args.repository_url}")
            logger.info("-" * 50)

            if not username:
                username_input = input("Username (default: admin): ").strip()
                username = username_input if username_input else "admin"
                logger.info(f"Using username: {username}")

            if not password:
                password = getpass.getpass("Password: ")
                if not password:
                    logger.error("Password cannot be empty for Nexus deployment")
                    raise ValueError("Password is required for Nexus deployment")

            logger.info("-" * 50)
        else:
            # PyPI 或其他仓库
            if not username or not password:
                logger.info(f"\n🔐 Repository Authentication Required")
                if is_pypi:
                    logger.info("PyPI Repository: https://pypi.org/")
                    logger.info("💡 Recommended: Use API tokens for better security")
                    logger.info("   Get your token at: https://pypi.org/manage/account/token/")
                elif is_test_pypi:
                    logger.info("TestPyPI Repository: https://test.pypi.org/")
                    logger.info("💡 Recommended: Use API tokens for better security")
                    logger.info("   Get your token at: https://test.pypi.org/manage/account/token/")
                else:
                    logger.info(f"Repository: {args.repository_url}")
                logger.info("-" * 60)

                if not username:
                    if is_pypi or is_test_pypi:
                        logger.info("For API tokens, use '__token__' as username")
                        username_input = input("Username (default: __token__): ").strip()
                        username = username_input if username_input else "__token__"
                    else:
                        username = input("Username: ").strip()

                if not password:
                    if username == "__token__":
                        password = getpass.getpass("API Token (pypi-...): ")
                    else:
                        password = getpass.getpass("Password: ")

                print("-" * 60)

    # 4. PyPI 默认处理 - 如果没有提供任何认证信息
    if (is_pypi or is_test_pypi) and not args.dry_run and not username and not password:
        logger.warning("No PyPI credentials provided!")
        logger.info("You can:")
        logger.info("   1. Set environment variables: TWINE_USERNAME, TWINE_PASSWORD")
        logger.info("   2. Configure ~/.pypirc file")
        logger.info("   3. Use --interactive flag for manual input")
        logger.info("   4. Get API token from: https://pypi.org/manage/account/token/")

        if not args.interactive:
            use_interactive = input("\nProceed with interactive input? (y/N): ").strip().lower()
            if use_interactive in ['y', 'yes']:
                # 递归调用交互模式
                args.interactive = True
                return get_credentials(args)
            else:
                raise ValueError("Authentication required for PyPI deployment")

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
        prerelease_version = int(match.group(5)) if match.group(5) else 1

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

