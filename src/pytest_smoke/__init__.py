from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pytest-smoke")
except PackageNotFoundError:
    pass


class PytestSmoke:
    def __init__(self):
        try:
            from xdist import __version__ as __xdist_version__

            self._is_xdist_installed = __xdist_version__ >= "2.3.0"
        except ImportError:
            self._is_xdist_installed = False

    @property
    def is_xdist_installed(self) -> bool:
        return self._is_xdist_installed

    @is_xdist_installed.setter
    def is_xdist_installed(self, v: bool):
        self._is_xdist_installed = v


smoke = PytestSmoke()
