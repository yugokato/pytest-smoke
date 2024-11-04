from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pytest-smoke")
except PackageNotFoundError:
    # package is not installed
    pass
