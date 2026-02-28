from setuptools import setup, find_packages

setup(
    name="eigentrace",
    version="0.1.0",
    description="LLM output quality filter: stance detection and generation physics",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="remvelchio",
    license="MIT",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "numpy>=1.21",
        "nltk>=3.7",
    ],
    extras_require={
        "signal": ["torch>=2.0"],
    },
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
)
