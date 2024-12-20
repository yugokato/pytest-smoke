from pytest import Item, hookspec


@hookspec(firstresult=True)
def pytest_smoke_generate_group_id(item: Item, scope: str):
    """Return a smoke scope group ID for the predefined or custom scopes

    Use this hook to either override the logic of the predefined scopes or to implement logic for your own scopes
    NOTE: Any custom scopes given to the --smoke-scope option must be handled in this hook
    """


@hookspec(firstresult=True)
def pytest_smoke_always_run(item: Item, scope: str):
    """Return True for tests that will always be executed regardless of what options are specified

    NOTE: These items will not be counted towards the calculation of N
    """


@hookspec(firstresult=True)
def pytest_smoke_exclude(item: Item, scope: str):
    """Return True for tests that should not be selected

    NOTE: These items will not be included in the total number of tests to which N% is applied
    """
