import pytest

pytest_plugins = "pytester"


@pytest.hookimpl(trylast=True)
def pytest_make_parametrize_id(val, argname):
    return f"{argname}={repr(val)}"
