from pytest import Config, Item, Session, hookimpl

from pytest_smoke import smoke
from pytest_smoke.types import SmokeIniOption
from pytest_smoke.utils import generate_group_id, get_scope, parse_ini_option

if smoke.is_xdist_installed:
    from xdist import is_xdist_controller
    from xdist.scheduler import LoadScopeScheduling

    class PytestSmokeXdist:
        """A plugin that extends pytest-smoke to seamlesslly support pytest-xdist"""

        name = "smoke-xdist"

        def __init__(self):
            self._nodes = None

        @hookimpl(tryfirst=True)
        def pytest_collection(self, session: Session):
            if is_xdist_controller(session):
                self._nodes = {item.nodeid: item for item in session.perform_collect()}
                return True

        def pytest_xdist_make_scheduler(self, config: Config, log):
            if parse_ini_option(config, SmokeIniOption.SMOKE_XDIST_DIST_BY_SCOPE):
                return SmokeScopeScheduling(config, log, nodes=self._nodes)

    class SmokeScopeScheduling(LoadScopeScheduling):
        """A custom pytest-xdist scheduler that distributes workloads by smoke scope groups"""

        def __init__(self, config: Config, log, *, nodes: dict[str, Item]):
            super().__init__(config, log)
            self._scope = get_scope(self.config)
            self._nodes = nodes

        def _split_scope(self, nodeid: str) -> str:
            item = self._nodes[nodeid]
            return generate_group_id(item, self._scope) or super()._split_scope(nodeid)
