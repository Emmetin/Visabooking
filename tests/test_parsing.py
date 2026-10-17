from vfs_monitor.parsing import PageState, SlotStatus, classify_page, classify_slots, slot_snippet


def test_no_slots_english():
    assert classify_slots("No appointment slots are currently available") is SlotStatus.NONE


def test_no_slots_russian_contains_available_word():
    assert classify_slots("К сожалению, нет доступных слотов для записи") is SlotStatus.NONE


def test_available_english():
    text = "Earliest available slot for Short stay is : 24-11-2026"
    assert classify_slots(text) is SlotStatus.AVAILABLE


def test_available_russian():
    assert classify_slots("Ближайшая доступная дата: 24.11.2026") is SlotStatus.AVAILABLE


def test_unknown():
    assert classify_slots("Пожалуйста, выберите визовый центр") is SlotStatus.UNKNOWN


def test_page_states():
    base = "https://visa.vfsglobal.com/rus/ru/fra"
    assert classify_page(f"{base}/login", "Email Password") is PageState.LOGIN
    assert classify_page(f"{base}/dashboard", "Just a moment...") is PageState.CHALLENGE
    assert classify_page(f"{base}/dashboard", "Error code: 429") is PageState.BLOCKED
    assert classify_page(f"{base}/dashboard", "Start New Booking") is PageState.OK


def test_snippet_is_the_matching_line():
    text = "Header\nEarliest available slot for Tourism is : 24-11-2026\nFooter"
    assert slot_snippet(text) == "Earliest available slot for Tourism is : 24-11-2026"
