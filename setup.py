import setuptools
import os
import re

version_file = os.path.join(os.path.dirname(__file__), 'pypowerwall', '__init__.py')
with open(version_file, 'r') as f:
    version_content = f.read()
match = re.search(r"^version_tuple\s*=\s*\(([^)]*)\)", version_content, re.MULTILINE)
if match:
    version_tuple = tuple(int(x.strip()) for x in match.group(1).split(','))
    __version__ = '%d.%d.%d' % version_tuple
else:
    raise RuntimeError('Unable to find version_tuple string in pypowerwall/__init__.py')

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
        'teslapy',
        'setuptools>=42',
        'wheel',
        'urllib3'
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
