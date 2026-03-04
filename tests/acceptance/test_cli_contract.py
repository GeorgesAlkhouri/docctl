from typer.testing import CliRunner

from docctl.cli import app


def test_commands_exist() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "ingest" in result.output
    assert "search" in result.output
    assert "show" in result.output
    assert "stats" in result.output
    assert "catalog" in result.output
    assert "doctor" in result.output
    assert "session" in result.output
