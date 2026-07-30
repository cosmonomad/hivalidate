from pathlib import Path

from hivalidate.cli import check_connectivity
from hivalidate.config import Config
from hivalidate.cutouts.base import CutoutBackend

FIXTURES = Path(__file__).parent / "fixtures"


class _StubBackend(CutoutBackend):
    def __init__(self, name, ok):
        self.name = name
        self._ok = ok

    def fetch(self, position, size_arcsec):
        raise NotImplementedError

    def is_available(self):
        return self._ok, "stub ok" if self._ok else "stub failure"


def _config(tmp_path):
    config = Config.from_yaml(FIXTURES / "config_mini.yaml")
    config.paths.work_dir = tmp_path / "work"
    return config


def test_run_returns_true_when_every_backend_is_available(monkeypatch, tmp_path):
    monkeypatch.setattr(
        check_connectivity, "build_optical_chain", lambda cfg: [_StubBackend("a", True)]
    )
    monkeypatch.setattr(
        check_connectivity, "build_continuum_chain", lambda cfg: [_StubBackend("b", True)]
    )
    assert check_connectivity.run(_config(tmp_path)) is True


def test_run_returns_false_if_any_backend_is_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(
        check_connectivity, "build_optical_chain", lambda cfg: [_StubBackend("a", True)]
    )
    monkeypatch.setattr(
        check_connectivity, "build_continuum_chain", lambda cfg: [_StubBackend("b", False)]
    )
    assert check_connectivity.run(_config(tmp_path)) is False


def test_main_exits_nonzero_when_a_backend_fails(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        check_connectivity, "build_optical_chain", lambda cfg: [_StubBackend("a", False)]
    )
    monkeypatch.setattr(check_connectivity, "build_continuum_chain", lambda cfg: [])
    config_path = FIXTURES / "config_mini.yaml"
    try:
        check_connectivity.main(["--config", str(config_path)])
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert exc.code == 1
