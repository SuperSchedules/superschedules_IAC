"""Setup script for deployment manager."""
from setuptools import setup, find_packages

setup(
    name="deploy-manager",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "boto3>=1.34.0",
        "click>=8.1.0",
        "rich>=13.7.0",
        "python-dateutil>=2.8.2",
    ],
    entry_points={
        "console_scripts": [
            "deploy-manager=deploy_manager.cli:cli",
        ],
    },
    python_requires=">=3.8",
)
