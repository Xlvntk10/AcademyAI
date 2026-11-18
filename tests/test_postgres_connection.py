from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from scripts import check_postgres as probe

CERTIFICATE = (Path(__file__).parent / "fixtures/connection-ca.pem").read_text()

URI = "postgresql://postgres.project:[YOUR-PASSWORD]@aws-0-region.pooler.supabase.com:5432/postgres"


def test_password_is_separate_and_url_encoding_roundtrips(tmp_path):
    ca = tmp_path / "certificate.crt"
    ca.write_text(CERTIFICATE)
    secret = "p@ss:/?#%with spaces"
    result = probe.database_url(URI, secret, ca)
    assert result.drivername == 'postgresql+psycopg'
    assert result.password == secret
    assert secret not in str(result)
    assert probe.make_url(result.render_as_string(hide_password=False)).password == secret
    assert result.query['sslmode'] == 'verify-full'


@pytest.mark.parametrize('uri', ['sqlite:///database.db', URI.replace(':5432', ':6543'), URI+'?sslmode=disable', URI+'?options=SECRET', 'not-a-uri-SECRET'])
def test_unsafe_config_rejected_without_echo(uri, tmp_path):
    ca = tmp_path / 'ca.crt'; ca.write_text(CERTIFICATE)
    with pytest.raises(probe.ConfigurationError) as error:
        probe.database_url(uri, 'SECRET', ca)
    assert 'SECRET' not in str(error.value)
    assert 'postgresql://' not in str(error.value)


@pytest.mark.parametrize('tls', [True, False])
def test_probe_is_tls_readonly_and_rollback_only(monkeypatch, tmp_path, tls):
    ca = tmp_path / 'ca.crt'; ca.write_text(CERTIFICATE)
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
    ca = tmp_path/'ca.crt'; ca.write_text(CERTIFICATE)
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
    ca = tmp_path/'ca.crt'; ca.write_text(CERTIFICATE)
    inputs = iter([URI, 'TOP_SECRET'])
    monkeypatch.setattr(probe, 'hidden', lambda prompt: next(inputs))
    monkeypatch.setattr(probe, 'check_connection', Mock())
    assert probe.main(['--ca-file', str(ca)]) == 0
    output = capsys.readouterr().out
    assert 'TLS включён' in output and 'SELECT 1 = 1' in output
    assert 'TOP_SECRET' not in output and 'postgresql://' not in output


@pytest.mark.parametrize('quotes', [('"','"'), ("'","'"), ('“','”'), ('','')])
def test_read_host_outer_quotes_and_spaces_are_removed(tmp_path, quotes):
    ca = tmp_path/'folder with spaces'/'ca.pem'
    ca.parent.mkdir(); ca.write_text(CERTIFICATE)
    entered = '  ' + quotes[0] + str(ca) + quotes[1] + '  '
    secret = ' "password with spaces" '
    result = probe.database_url('"' + URI + '"', secret, entered)
    assert Path(result.query['sslrootcert']) == ca.resolve()
    assert result.password == secret  # Never trim or unquote a real password.


@pytest.mark.parametrize('content', ['<html>download failed SECRET</html>', 'not a certificate SECRET'])
def test_existing_but_invalid_ca_fails_before_connection(tmp_path, monkeypatch, capsys, content):
    ca = tmp_path/'SECRET.pem'; ca.write_text(content)
    inputs = iter([URI, 'TOP_SECRET'])
    monkeypatch.setattr(probe, 'hidden', lambda prompt: next(inputs))
    connect = Mock(); monkeypatch.setattr(probe.psycopg, 'connect', connect)
    assert probe.main(['--ca-file', str(ca)]) == 1
    output = capsys.readouterr()
    assert '[CA_FORMAT]' in output.err
    assert 'SECRET' not in output.out + output.err
    connect.assert_not_called()


def test_missing_ca_has_its_own_safe_message(tmp_path):
    with pytest.raises(probe.ConfigurationError, match='CA_PATH') as error:
        probe.database_url(URI, 'PASSWORD', tmp_path/'PRIVATE.pem')
    assert 'PRIVATE' not in str(error.value)


@pytest.mark.parametrize('detail,expected', [
    ('password authentication failed for user', 'AUTH_REJECTED'),
    ('Tenant or user not found', 'POOLER_IDENTITY'),
    ('FATAL: (ENOTFOUND) tenant/user postgres.project not found', 'POOLER_IDENTITY'),
    ('SSL error: certificate verify failed', 'TLS_CERTIFICATE'),
    ('server certificate does not match host name', 'TLS_HOSTNAME'),
    ('root certificate file does not exist', 'TLS_CA_LOAD'),
    ('server does not support SSL, but SSL was required', 'TLS_REQUIRED'),
    ('SSL error: unsupported protocol', 'TLS_HANDSHAKE'),
    ('could not translate host name', 'DNS'),
    ('connection timeout expired', 'TIMEOUT'),
    ('connection refused', 'CONNECTION_REFUSED'),
    ('server closed the connection unexpectedly', 'NETWORK'),
    ('no pg_hba.conf entry', 'ACCESS_RULE'),
    ('MaxClientsInSessionMode: max clients reached', 'POOL_LIMIT'),
    ('SASL authentication failed', 'AUTH_PROTOCOL'),
    ('opaque unrecognized problem', 'UNKNOWN'),
])
def test_connection_errors_are_classified_without_echoing_secrets(tmp_path, monkeypatch, capsys, detail, expected):
    ca = tmp_path/'ca.pem'; ca.write_text(CERTIFICATE)
    uri = URI.replace('[YOUR-PASSWORD]', 'TOP_SECRET')
    monkeypatch.setenv('DATABASE_URL', uri)
    monkeypatch.setattr(probe.psycopg, 'connect', Mock(side_effect=probe.psycopg.OperationalError(detail + ' ' + uri + ' PRIVATE_DIAGNOSTIC')))
    assert probe.main(['--from-env', '--ca-file', str(ca)]) == 1
    output = capsys.readouterr()
    assert '[CONNECT/' + expected + ']' in output.err
    assert 'OK [CONFIG]' in output.out
    for secret in ('TOP_SECRET', 'PRIVATE_DIAGNOSTIC', 'postgresql://', 'aws-0-region', 'Traceback'):
        assert secret not in output.err + output.out


@pytest.mark.parametrize('state,expected', [('28P01','AUTH_REJECTED'), ('3D000','DATABASE'), ('42501','PERMISSION'), ('53300','POOL_LIMIT'), ('57P03','SERVER_UNAVAILABLE'), ('28000','ACCESS_RULE')])
def test_sqlstate_diagnosis_does_not_require_printing_server_message(state, expected):
    error = probe.psycopg.errors.lookup(state)('PRIVATE_MESSAGE')
    assert probe.diagnose(error) == expected


def test_query_failure_has_select_stage_and_no_commit(tmp_path, monkeypatch):
    ca = tmp_path/'ca.pem'; ca.write_text(CERTIFICATE)
    cursor = Mock(); cursor.execute.side_effect = probe.psycopg.errors.InsufficientPrivilege('PRIVATE')
    context = Mock(); context.__enter__ = Mock(return_value=cursor); context.__exit__ = Mock(return_value=False)
    connection = Mock(pgconn=SimpleNamespace(ssl_in_use=True)); connection.cursor.return_value = context
    monkeypatch.setattr(probe.psycopg,'connect',Mock(return_value=connection))
    with pytest.raises(probe.ProbeFailure) as error:
        probe.check_connection(probe.database_url(URI, 'SECRET', ca))
    assert (error.value.stage, error.value.code) == ('SELECT', 'PERMISSION')
    assert 'PRIVATE' not in str(error.value)
    cursor.execute.assert_called_once_with('SELECT 1')
    connection.commit.assert_not_called(); connection.close.assert_called_once()


@pytest.mark.skipif(probe.os.name != 'nt', reason='Windows libpq path compatibility')
def test_cyrillic_ca_is_copied_exactly_and_temporary_copy_is_removed(tmp_path):
    original = tmp_path/'сертификат с пробелами.pem'; original.write_text(CERTIFICATE)
    with probe.driver_certificate(str(original)) as prepared:
        assert prepared.isascii()
        assert Path(prepared).read_bytes() == original.read_bytes()
        assert Path(prepared) != original
    assert not Path(prepared).exists()
    assert original.read_text() == CERTIFICATE


@pytest.mark.skipif(probe.os.name != 'nt', reason='Windows libpq path compatibility')
def test_temporary_ca_removed_on_failed_handshake(tmp_path, monkeypatch):
    original = tmp_path/'сертификат.pem'; original.write_text(CERTIFICATE)
    paths = []
    def fail(**kwargs):
        paths.append(kwargs['sslrootcert'])
        assert Path(paths[0]).is_file()
        assert kwargs['sslmode'] == 'verify-full'
        raise probe.psycopg.OperationalError('SSL error: certificate verify failed')
    monkeypatch.setattr(probe.psycopg, 'connect', fail)
    with pytest.raises(probe.ProbeFailure, match='TLS_CERTIFICATE'):
        probe.check_connection(probe.database_url(URI, 'SECRET', original))
    assert not Path(paths[0]).exists()
    assert original.is_file()
