from app.api import routes


def test_should_queue_async_for_long_prompt():
    text = "x" * 300
    assert routes._should_queue_async(text) is True


def test_should_queue_async_for_detailed_hint():
    assert routes._should_queue_async("Give a detailed step-by-step explanation with many bullets.") is True


def test_should_not_queue_async_for_short_prompt():
    assert routes._should_queue_async("What is our PTO policy?") is False
