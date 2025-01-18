from setuptools import setup, find_packages

setup(
    name="devt",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=["typer", "GitPython"],
    entry_points={
        "console_scripts": [
            "devt=devt.cli:app",
        ],
    },
    author="Derk Kappelle",
    author_email="derk.kappelle@uw-api.com",
    description="Sharing Development Tools made easy",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/dkuwcreator/devt.git",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)
