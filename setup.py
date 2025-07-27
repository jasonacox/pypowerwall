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
        'requests-oauthlib',
        'websocket-client>=0.59.0',
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
