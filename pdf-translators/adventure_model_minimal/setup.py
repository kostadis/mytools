from setuptools import setup

setup(
    name="adventure-model-minimal",
    version="0.1.0",
    description="Rust parser for 5etools adventure JSON format",
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author="Kostadis Roussos",
    author_email="kroussos@gmail.com",
    url="https://github.com/kroussos/mytools",
    packages=["adventure_model_minimal"],
    package_data={"adventure_model_minimal": ["*.so", "*.pyd", "*.dll"]},
    include_package_data=True,
    install_requires=[
        "pyo3>=0.21",
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.8",
)