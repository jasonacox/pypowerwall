import setuptools
import os
import re

# Read version from pypowerwall/VERSION - single source of truth
# (pypowerwall/__init__.py reads the same file at runtime)
version_file = os.path.join(os.path.dirname(__file__), 'pypowerwall', 'VERSION')
try:
    with open(version_file, 'r') as f:
        __version__ = f.read().strip()
except OSError:
    raise RuntimeError('Unable to read version from pypowerwall/VERSION')
if not re.match(r'^\d+\.\d+\.\d+$', __version__):
    raise RuntimeError('Invalid version %r in pypowerwall/VERSION' % __version__)

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
        'httpx[http2]>=0.27.0',
        'protobuf>=4.25.1',
        'python-dotenv',
        'pyroute2',
        'bs4',
        'python-dateutil',
        'requests-oauthlib',
        'websocket-client>=0.59.0',
        'cryptography',
    ],
    package_data={
        'pypowerwall': ['VERSION'],
        'pypowerwall.cloud.teslapy': ['endpoints.json', 'option_codes.json'],
        # TEDAPI query sets are loaded from JSON at runtime — must ship in the wheel.
        'pypowerwall.tedapi.queries': ['*.json'],
    },
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'pypowerwall=pypowerwall.__main__:main',
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
