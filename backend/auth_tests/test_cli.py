"""Small, isolated checks for the packaged launcher."""

import pytest

from carole_ai.cli import _parser


@pytest.mark.parametrize("port", ["0", "65536", "not-a-port"])
def test_invalid_cli_port_is_rejected(port, capsys):
    with pytest.raises(SystemExit) as exc:
        _parser().parse_args(["--port", port])
    assert exc.value.code == 2
    assert "port must be an integer from 1 to 65535" in capsys.readouterr().err


def test_invalid_port_environment_is_rejected(monkeypatch, capsys):
    monkeypatch.setenv("PORT", "not-a-port")
    with pytest.raises(SystemExit) as exc:
        _parser().parse_args([])
    assert exc.value.code == 2
    assert "port must be an integer from 1 to 65535" in capsys.readouterr().err


def test_valid_port_environment_and_override(monkeypatch):
    monkeypatch.setenv("PORT", "9000")
    assert _parser().parse_args([]).port == 9000
    assert _parser().parse_args(["--port", "8001"]).port == 8001
