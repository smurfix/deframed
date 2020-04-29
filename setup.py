from setuptools import setup, find_packages

LONG_DESC = open("README.rst").read()

setup(
    name="deframed",
    use_scm_version={"version_scheme": "guess-next-dev", "local_scheme": "dirty-tag"},
    description="A minimal web non-framework",
    url="https://github.com/smurfix/deframed",
    long_description=LONG_DESC,
    author="Matthias Urlichs",
    author_email="matthias@urlichs.de",
    license="GPL3",
    packages=find_packages(),
    setup_requires=["setuptools_scm", "pytest_runner"],
    install_requires=[
        "trio >= 0.12",
        "attrs >= 18.2",
        "chevron",
        "quart-trio >= 0.5",
    ],
    tests_require=[
        "pytest",
        "pytest-trio",
        "flake8 >= 3.7"
    ],
    keywords=["async", "web", "framework"],
    python_requires=">=3.7",
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "Framework :: Trio",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: Implementation :: CPython",
        "Topic :: Communications :: Telephony",
        "Topic :: Software Development :: Testing",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
    ],
    zip_safe=False,
)
