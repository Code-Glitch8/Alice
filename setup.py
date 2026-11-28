#!/usr/bin/env python3
"""
Setup script for ALICE.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

with open("requirements.txt", "r", encoding="utf-8") as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

setup(
    name="alice",
    version="0.1.0",
    author="ALICE Team",
    author_email="alice@example.com",
    description="Autonomous Local Intelligence & Computer Engine - A local voice-controlled Windows AI assistant",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/alice",
    packages=find_packages(include=["alice", "alice.*"]),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Microsoft :: Windows :: Windows 11",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Desktop Environment",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.11",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "alice=alice.cli:main",
        ],
        "gui_scripts": [
            "alice-desktop=alice.main:main",
        ],
    },
    include_package_data=True,
    package_data={
        "alice": ["*.py", "**/*.py"],
    },
)