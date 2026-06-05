from setuptools import setup, find_packages

setup(
    name="ipad-optimizer",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "click>=8.1",
        "rich>=13.0",
        "google-api-python-client>=2.0",
        "google-auth-httplib2>=0.2",
        "google-auth-oauthlib>=1.0",
        "schedule>=1.2",
        "tqdm>=4.65",
    ],
    entry_points={
        "console_scripts": [
            "ipad-optimizer=ipad_optimizer.cli:main",
        ],
    },
    python_requires=">=3.11",
)
