from __future__ import annotations

from typing import TYPE_CHECKING

from pytest import hookspec

if TYPE_CHECKING:
    from pytest import Item


@hookspec(firstresult=True)
def pytest_smoke_generate_group_id(item: Item, scope: str):
    """Return a smoke scope group ID for the predefined or custom scopes

    Use this hook to either override the logic of the predefined scopes or to implement logic for your own scopes
    NOTE: Any custom scopes given to the --smoke-scope option must be handled in this hook
    """


@hookspec(firstresult=True)
def pytest_smoke_include(item: Item, scope: str):
    """Return True for tests that should be included as "additional" smoke tests

    NOTE: These items will not be counted towards the calculation of N
    """


@hookspec(firstresult=True)
def pytest_smoke_exclude(item: Item, scope: str):
    """Return True for tests that should not be selected

    NOTE:
        - These items will not be included in the total number of tests to which N% is applied
        - This hook takes precedence over any other options provided by the plugin
    """


@hookspec(firstresult=True)
def pytest_smoke_sort_by_select_mode(items: list[Item], scope: str, select_mode: str):
    """Return sorted items to implement a test selection logic for the custom select mode.
    The plugin will pick N tests from each scope group based on the sorted items, meaning that an item appearing
    earlier in the same scope group has a higher chance of being selected.

    NOTE:
        - The hook is called only for custom select modes
        - This hook does not affect the test execution order
    """
