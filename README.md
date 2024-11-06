pytest-smoke
======================

[![PyPI](https://img.shields.io/pypi/v/pytest-smoke)](https://pypi.org/project/pytest-smoke/)
[![Supported Python
versions](https://img.shields.io/pypi/pyversions/pytest-smoke.svg)](https://pypi.org/project/pytest-smoke/)
[![test](https://github.com/yugokato/pytest-smoke/actions/workflows/test.yml/badge.svg)](https://github.com/yugokato/pytest-smoke/actions/workflows/test.yml)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/yugokato/pytest-smoke/main.svg)](https://results.pre-commit.ci/latest/github/yugokato/pytest-smoke/main)
[![Code style ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://docs.astral.sh/ruff/)

A small `pytest` plugin that enables a quick smoke testing against a large test suite by limiting the number of tests 
from each parametrized test function to up to `N`.

## Installation

```
pip install pytest-smoke
```


## Usage

The plugin provides the `--smoke` and `--smoke-random` options, each accepting an optional positive number `N`:
```
$ pytest -h

<snip>

Smoke testing:
  --smoke=[N]           Run the first N tests (default=1) from each test function
  --smoke-random=[N]    Run N randomly selected tests (default=1) from each test function
```

## Examples

Given you have the following test code:

```python
import pytest


def test_something1():
    pass
    
@pytest.mark.parametrize("p", range(10))
def test_something2(p):
    pass
    
@pytest.mark.parametrize("p", range(20))
def test_something3(p):
    pass
```

You can run smoke tests with either the `--smoke` or `--smoke-random` option:

1. `--smoke` option
- Run only the first test from each test function (`N`= default 1)
```
$ pytest -v --smoke
======================== test session starts =========================
<snip>
collected 31 items                                                   

tests/test_something.py::test_something1 PASSED                 [ 33%]
tests/test_something.py::test_something2[0] PASSED              [ 66%]
tests/test_something.py::test_something3[0] PASSED              [100%]

========================= 3 passed in 0.02s ==========================
```

- Run up to 3 tests from each test function (`N`=3)
```
$ pytest -v --smoke 3
======================== test session starts =========================
<snip>
collected 31 items                                                   

tests/test_something.py::test_something1 PASSED                 [ 14%]
tests/test_something.py::test_something2[0] PASSED              [ 28%]
tests/test_something.py::test_something2[1] PASSED              [ 42%]
tests/test_something.py::test_something2[2] PASSED              [ 57%]
tests/test_something.py::test_something3[0] PASSED              [ 71%]
tests/test_something.py::test_something3[1] PASSED              [ 85%]
tests/test_something.py::test_something3[2] PASSED              [100%]

========================= 7 passed in 0.02s ==========================
```

2. `--smoke-random` option
- Run randomly selected one test from each test function (`N`= default 1)
```
$ pytest -v --smoke-random
======================== test session starts =========================
<snip>
collected 31 items                                                   

tests/test_something.py::test_something1 PASSED                 [ 33%]
tests/test_something.py::test_something2[4] PASSED              [ 66%]
tests/test_something.py::test_something3[8] PASSED              [100%]

========================= 3 passed in 0.02s ==========================
```

- Run up to 3 randomly selected tests from each test function (`N`=3)
```
$ pytest -v --smoke-random 3
======================== test session starts =========================
<snip>
collected 31 items                                                   

tests/test_something.py::test_something1 PASSED                 [ 14%]
tests/test_something.py::test_something2[1] PASSED              [ 28%]
tests/test_something.py::test_something2[3] PASSED              [ 42%]
tests/test_something.py::test_something2[8] PASSED              [ 57%]
tests/test_something.py::test_something3[2] PASSED              [ 71%]
tests/test_something.py::test_something3[4] PASSED              [ 85%]
tests/test_something.py::test_something3[14] PASSED             [100%]

========================= 7 passed in 0.02s ==========================
```
