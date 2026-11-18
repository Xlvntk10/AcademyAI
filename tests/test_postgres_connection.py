from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from scripts import check_postgres as probe

URI = "postgresql://postgres.project:[YOUR-PASSWORD]@aws-0-region.pooler.supabase.com:5432/postgres"


def test_password_is_separate_and_url_encoding_roundtrips(tmp_path):
    ca = tmp_path / "certificate.crt"
    ca.write_text("test certificate")
    secret = "p@ss:/?#%with spaces"
    result = probe.database_url(URI, secret, ca)
    assert result.drivername == 'postgresql+psycopg'
    assert result.password == secret
    assert secret not in str(result)
    assert probe.make_url(result.render_as_string(hide_password=False)).password == secret
    assert result.query['sslmode'] == 'verify-full'


@pytest.mark.parametrize('uri', ['sqlite:///database.db', URI.replace(':5432', ':6543'), URI+'?sslmode=disable', URI+'?options=SECRET', 'not-a-uri-SECRET'])
def test_unsafe_config_rejected_without_echo(uri, tmp_path):
    ca = tmp_path / 'ca.crt'; ca.write_text('test')
    with pytest.raises(probe.ConfigurationError) as error:
        probe.database_url(uri, 'SECRET', ca)
    assert 'SECRET' not in str(error.value)
    assert 'postgresql://' not in str(error.value)


@pytest.mark.parametrize('tls', [True, False])
def test_probe_is_tls_readonly_and_rollback_only(monkeypatch, tmp_path, tls):
    ca = tmp_path / 'ca.crt'; ca.write_text('test')
    url = probe.database_url(URI, 'SECRET', ca)
    cursor = Mock(); cursor.fetchone.return_value = (1,)
    cursor_context = Mock(); cursor_context.__enter__ = Mock(return_value=cursor); cursor_context.__exit__ = Mock(return_value=False)
    connection = Mock(pgconn=SimpleNamespace(ssl_in_use=tls))
    connection.cursor.return_value = cursor_context
    connect = Mock(return_value=connection)
    monkeypatch.setattr(probe.psycopg, 'connect', connect)
    if tls:
        probe.check_connection(url)
        assert connection.read_only is True
        cursor.execute.assert_called_once_with('SELECT 1')
        connection.rollback.assert_called_once()
    else:
        with pytest.raises(RuntimeError): probe.check_connection(url)
        cursor.execute.assert_not_called()
    connection.commit.assert_not_called()
    connection.close.assert_called_once()
    assert connect.call_args.kwargs['sslmode'] == 'verify-full'
    assert connect.call_args.kwargs['options'] == ''
    assert connect.call_args.kwargs['prepare_threshold'] is None


def test_cli_hides_driver_exception_and_leaves_environment_unchanged(monkeypatch, tmp_path, capsys):
    ca = tmp_path/'ca.crt'; ca.write_text('test')
    value = URI.replace('[YOUR-PASSWORD]', 'TOP_SECRET')
    monkeypatch.setenv('DATABASE_URL', value)
    monkeypatch.setenv('ACADEMY_DATABASE_URL', 'sqlite:///database.db')
    monkeypatch.setattr(probe, 'check_connection', Mock(side_effect=RuntimeError(value)))
    assert probe.main(['--from-env', '--ca-file', str(ca)]) == 1
    output = capsys.readouterr()
    assert 'TOP_SECRET' not in output.err + output.out
    assert 'Traceback' not in output.err
    assert probe.os.environ['DATABASE_URL'] == value
    assert probe.os.environ['ACADEMY_DATABASE_URL'] == 'sqlite:///database.db'


def test_hidden_prompt_does_not_allow_echoing_fallback(monkeypatch):
    def fallback(prompt):
        probe.warnings.warn('password could echo', probe.getpass.GetPassWarning)
        raise AssertionError('must not reach echoing input')
    monkeypatch.setattr(probe.getpass, 'getpass', fallback)
    with pytest.raises(probe.getpass.GetPassWarning): probe.hidden('password:')


def test_cli_success_is_readable_and_contains_no_credentials(monkeypatch, tmp_path, capsys):
    ca = tmp_path/'ca.crt'; ca.write_text('test')
    inputs = iter([URI, 'TOP_SECRET'])
    monkeypatch.setattr(probe, 'hidden', lambda prompt: next(inputs))
    monkeypatch.setattr(probe, 'check_connection', Mock())
    assert probe.main(['--ca-file', str(ca)]) == 0
    output = capsys.readouterr().out
    assert 'TLS включён' in output and 'SELECT 1 = 1' in output
    assert 'TOP_SECRET' not in output and 'postgresql://' not in output
