from pytest import Config, Item, Session, hookimpl

from pytest_smoke import smoke
from pytest_smoke.types import SmokeIniOption, SmokeOption
from pytest_smoke.utils import generate_group_id, parse_ini_option

if smoke.is_xdist_installed:
    from xdist import is_xdist_controller
    from xdist.scheduler import LoadScopeScheduling

    class PytestSmokeXdist:
        """A plugin that extends pytest-smoke to seamlesslly support pytest-xdist

        This plugin will be dynamically registered when the -n/--numprocesses option is given
        """

        name = "smoke-xdist"

        def __init__(self):
            self._nodes = None

        @hookimpl(tryfirst=True)
        def pytest_collection(self, session: Session):
            if is_xdist_controller(session):
                self._nodes = {item.nodeid: item for item in session.perform_collect()}
                return True

        def pytest_xdist_make_scheduler(self, config: Config, log):
            """Replace the pytest-xdist default scheduler (load) with our custom scheduler (smoke scope) when the
            following conditions match:
            - The INI option value is set to true
            - No dist option (--dist or -d) is explicitly given
            """
            if (
                config.known_args_namespace.dist == "no"
                and not config.known_args_namespace.distload
                and parse_ini_option(config, SmokeIniOption.SMOKE_DEFAULT_XDIST_DIST_BY_SCOPE)
            ):
                return SmokeScopeScheduling(config, log, nodes=self._nodes)

    class SmokeScopeScheduling(LoadScopeScheduling):
        """A custom pytest-xdist scheduler that distributes workloads by smoke scope groups"""

        def __init__(self, config: Config, log, *, nodes: dict[str, Item]):
            super().__init__(config, log)
            self.smoke_option = SmokeOption(config)
            self._nodes = nodes

        def _split_scope(self, nodeid: str) -> str:
            item = self._nodes[nodeid]

            return generate_group_id(item, self.smoke_option.scope) or super()._split_scope(nodeid)
