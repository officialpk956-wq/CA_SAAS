import pytest
from backend.gst_copilot import auth

def test_password_hash_roundtrip_is_salted_and_rejects_wrong_or_missing():
    h1, h2 = auth.hash_password('correct horse battery'), auth.hash_password('correct horse battery')
    assert h1 != h2 and h1.startswith('scrypt$')
    assert auth.verify_password('correct horse battery', h1)
    assert not auth.verify_password('correct horse batterx', h1)
    assert not auth.verify_password('anything at all', None)
    assert not auth.verify_password('x', 'not-a-hash')

def test_short_passwords_are_refused():
    with pytest.raises(ValueError): auth.hash_password('short')

def test_session_tokens_are_random_and_only_hashes_are_comparable():
    a, b = auth.new_session_token(), auth.new_session_token()
    assert a != b and len(a) >= 40
    assert auth.token_hash(a) == auth.token_hash(a) != auth.token_hash(b) and a not in auth.token_hash(a)

def test_throttle_locks_after_limit_and_unlocks_after_window():
    now = [0.0]
    t = auth.LoginThrottle(attempts=5, lockout_seconds=900, clock=lambda: now[0])
    for _ in range(4): t.fail('a@x.test')
    assert t.locked_for('a@x.test') == 0
    t.fail('a@x.test')
    assert t.locked_for('a@x.test') > 0 and t.locked_for('b@x.test') == 0
    now[0] = 901
    assert t.locked_for('a@x.test') == 0
    t.fail('a@x.test'); t.succeed('a@x.test')
    assert t.locked_for('a@x.test') == 0
