from pypowerwall.pypowerwall_base import parse_version

def test_parse_version_basic():
    assert parse_version('1.2.3') == 3 + 2*100 + 1*10000

def test_parse_version_missing_parts():
    # Should pad with .0
    v = parse_version('2.5')
    # 2.5.0 -> components reversed [0,5,2] => 0*1 + 5*100 + 2*10000
    assert v == 5*100 + 2*10000

def test_parse_version_none():
    assert parse_version(None) is None

def test_parse_version_weird_chars():
    v = parse_version('v23.44.1-build')
    # 23.44.1 -> reversed [1,44,23] => 1 + 44*100 + 23*10000
    assert v == 1 + 44*100 + 23*10000
