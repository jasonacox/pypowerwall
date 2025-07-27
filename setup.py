import setuptools

from pypowerwall import __version__

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="pypowerwall",
    version=__version__,
    author="Jason Cox",
    author_email="jason@jasonacox.com",
    description="Python module to access Tesla Energy Gateway for Powerwall and solar power data",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://github.com/jasonacox/pypowerwall',
    packages=setuptools.find_packages(),
    install_requires=[
        'requests',
        'protobuf>=3.20.0',
        'python-dotenv',
        'pyroute2',
        'bs4',
        'python-dateutil',
        # TeslaPy is installed via dependency_links below
    ],
    dependency_links=[
        'git+https://github.com/tdorssers/TeslaPy.git@0ac92964d9d0b4fe4764288f483e892b879d9ace#egg=teslapy',
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
