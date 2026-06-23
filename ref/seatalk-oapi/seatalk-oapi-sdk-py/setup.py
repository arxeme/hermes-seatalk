from setuptools import find_packages, setup


setup(
    name="seatalk-oapi-sdk-py",
    version="0.1.0",
    description="Pure-stdlib Python SDK for the seatalk open platform developer bot WebSocket protocol.",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    python_requires=">=3.8",
    packages=find_packages(include=["seatalk_oapi_sdk", "seatalk_oapi_sdk.*"]),
    install_requires=[],
    author="SeaTalk Open Platform",
)
