from app.services.rate_limit import RateLimiter


def test_rate_limiter_blocks_after_limit():
    limiter = RateLimiter()
    ok1, _ = limiter.hit("k", limit=2, window_seconds=60)
    ok2, _ = limiter.hit("k", limit=2, window_seconds=60)
    ok3, retry = limiter.hit("k", limit=2, window_seconds=60)
    assert ok1 is True
    assert ok2 is True
    assert ok3 is False
    assert retry >= 1
