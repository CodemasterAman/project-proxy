from subject import add, is_positive


def test_add():
    assert add(2, 3) == 5


def test_positive():
    assert is_positive(5) is True


def test_one_is_positive():
    assert is_positive(1) is True


def test_zero_is_not_positive():
    assert is_positive(0) is False


def test_negative():
    assert is_positive(-3) is False
