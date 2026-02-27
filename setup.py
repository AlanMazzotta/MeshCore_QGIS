from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="meshcore-qgis",
    version="0.1.0",
    author="Alan M",
    description="MeshCore network analysis toolkit for QGIS repeater placement",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/MeshCore_QGIS",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=[
        "meshcore>=0.1.0",
        "paho-mqtt>=1.6.1",
        "geojson>=2.5.0",
        "requests>=2.28.0",
        "python-dotenv>=0.21.0",
    ],
)
