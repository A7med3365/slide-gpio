from setuptools import setup, find_packages

setup(
    name="atc-engine",
    version="0.1.0",
    description="GPIO-based button input handling with support for combinations and actions",
    author="Olimex",
    packages=find_packages(),
    install_requires=[
        "pyA64",  # GPIO library for A64 boards
    ],
    extras_require={
        "dev": [
            "pytest",
            "pytest-cov",
            "black",
            "isort",
            "mypy",
        ]
    },
    python_requires=">=3.6",
    entry_points={
        "console_scripts": [
            "atc-engine=atc_engine.main:main",
        ]
    },
)