import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
import pytest


@pytest.fixture
def ctx(tmp_path):
    from dlauncher.core.ctx import Ctx
    c = Ctx(user_data=str(tmp_path / "ud"))
    c.settings["rootDir"] = str(tmp_path / "root")
    os.makedirs(c.settings["rootDir"], exist_ok=True)
    return c


@pytest.fixture
def srv():
    from mockserver import MockServer
    s = MockServer()
    yield s
    s.stop()


def pytest_collection_modifyitems(config, items):
    """На Windows-сборке (CI) тесты пропускаем: они рассчитаны на Linux, а проверку интерфейса делает --selftest."""
    if sys.platform == "win32":
        skip = pytest.mark.skip(reason="только Linux")
        for it in items:
            it.add_marker(skip)
