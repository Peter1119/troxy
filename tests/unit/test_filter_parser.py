from troxy.core.filter_parser import parse_filter


def test_parse_host():
    result = parse_filter("host:api.example.com")
    assert result == {"domain": "api.example.com"}


def test_parse_status_exact():
    result = parse_filter("status:401")
    assert result == {"status": 401}


def test_parse_status_range():
    result = parse_filter("status:4xx")
    assert result == {"status_range": (400, 499)}


def test_parse_method():
    result = parse_filter("method:POST")
    assert result == {"method": "POST"}


def test_parse_path():
    result = parse_filter("path:/api/users/*")
    assert result == {"path": "/api/users/*"}


def test_parse_multiple():
    result = parse_filter("host:api.example.com status:4xx")
    assert result == {"domain": "api.example.com", "status_range": (400, 499)}


def test_parse_freetext():
    result = parse_filter("unauthorized")
    assert result == {"query": "unauthorized"}


def test_parse_mixed():
    result = parse_filter("host:api.example.com token_expired")
    assert result == {"domain": "api.example.com", "query": "token_expired"}


def test_parse_empty():
    result = parse_filter("")
    assert result == {}
