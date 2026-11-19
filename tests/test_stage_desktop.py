import json
import pytest
from scripts import run_stage, stage_desktop


@pytest.mark.parametrize('inspection_code,state,create,expected_calls', [
    (1, 'absent', True, 1),
    (0, 'objects_present_review_required', True, 1),
    (0, 'absent', False, 1),
    (0, 'absent', True, 2),
])
def test_desktop_inspection_gate(tmp_path, monkeypatch, inspection_code, state, create, expected_calls):
    monkeypatch.setattr(run_stage, 'ROOT', tmp_path)
    directory = tmp_path/'.test-artifacts'
    directory.mkdir()
    (directory/'supabase-stage-inspection.json').write_text(json.dumps({'state':state}))
    calls = []
    def fake_main(argv, *, credential_provider):
        assert credential_provider() == ('placeholder', 'SYNTHETIC_SECRET')
        calls.append(argv)
        return inspection_code if '--inspect' in argv else 0
    monkeypatch.setattr(run_stage, 'main', fake_main)
    result = stage_desktop.execute('ca.pem', ('placeholder', 'SYNTHETIC_SECRET'), create=create)
    assert len(calls) == expected_calls
    assert '--inspect' in calls[0]
    if expected_calls == 2:
        assert '--allow-creator-set' in calls[1]
    assert 'SYNTHETIC_SECRET' not in result


def test_desktop_rejects_embedded_secret_without_echo(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(run_stage, 'ROOT', tmp_path)
    monkeypatch.setattr(run_stage, 'visible_uri', lambda: pytest.fail('Desktop must not prompt in console'))
    credentials = ('postgresql://name:EMBEDDED_SECRET@private-host/postgres', 'FIELD_SECRET')
    assert run_stage.main(['--inspect','--ca-file','unused'], credential_provider=lambda: credentials) == 1
    report = (tmp_path/'.test-artifacts/supabase-stage-inspection.json').read_text()
    output = capsys.readouterr()
    for secret in ('EMBEDDED_SECRET', 'FIELD_SECRET', 'private-host', 'postgresql://'):
        assert secret not in report + output.out + output.err
    assert 'URI_PLACEHOLDER' in report
