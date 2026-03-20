import json

from src.domain.news import PreferenceRules


def test_from_stored_valid_json():
    raw = json.dumps(
        {"skip": ["crypto", "sports"], "high_priority": ["AI research"]}
    )
    rules = PreferenceRules.from_stored(raw)
    assert rules.skip == ["crypto", "sports"]
    assert rules.high_priority == ["AI research"]
    assert rules.recently_deleted == []


def test_from_stored_none():
    rules = PreferenceRules.from_stored(None)
    assert rules.skip == []
    assert rules.high_priority == []
    assert rules.recently_deleted == []


def test_from_stored_empty_string():
    rules = PreferenceRules.from_stored("")
    assert rules.skip == []
    assert rules.high_priority == []


def test_from_stored_old_prose_fallback():
    rules = PreferenceRules.from_stored(
        "User likes AI topics and dislikes sports."
    )
    assert rules.skip == []
    assert rules.high_priority == []


def test_from_stored_partial_json():
    raw = json.dumps({"skip": ["crypto"]})
    rules = PreferenceRules.from_stored(raw)
    assert rules.skip == ["crypto"]
    assert rules.high_priority == []


def test_to_json_roundtrip():
    original = PreferenceRules(
        skip=["celebrity gossip", "sports scores"],
        high_priority=["Python releases"],
    )
    restored = PreferenceRules.from_stored(original.to_json())
    assert restored.skip == original.skip
    assert restored.high_priority == original.high_priority
    assert restored.recently_deleted == original.recently_deleted


def test_to_json_format():
    rules = PreferenceRules(skip=["a"], high_priority=["b"])
    parsed = json.loads(rules.to_json())
    assert parsed == {
        "skip": ["a"],
        "high_priority": ["b"],
        "recently_deleted": [],
    }


def test_recently_deleted_roundtrip():
    deleted = [
        {
            "title": "Python 3.14.0 alpha 2",
            "feedback": "Only major",
            "deleted_at": "2026-03-10",
        },
        {"title": "Go 1.23rc1", "feedback": None},
    ]
    original = PreferenceRules(
        skip=["crypto"],
        high_priority=["AI"],
        recently_deleted=deleted,
    )
    restored = PreferenceRules.from_stored(original.to_json())
    assert restored.recently_deleted == deleted
    assert restored.skip == ["crypto"]
    assert restored.high_priority == ["AI"]


def test_recently_deleted_to_json_format():
    deleted = [{"title": "Some article", "feedback": "not relevant"}]
    rules = PreferenceRules(recently_deleted=deleted)
    parsed = json.loads(rules.to_json())
    assert parsed["recently_deleted"] == deleted


def test_backward_compat_legacy_boost_and_deleted():
    """Old JSON with 'boost' and 'deleted' keys is read correctly."""
    raw = json.dumps(
        {
            "skip": ["sports"],
            "boost": ["tech"],
            "deleted": [{"title": "Old", "feedback": None}],
        }
    )
    rules = PreferenceRules.from_stored(raw)
    assert rules.skip == ["sports"]
    assert rules.high_priority == ["tech"]
    assert rules.recently_deleted == [{"title": "Old", "feedback": None}]


def test_backward_compat_no_deleted_key():
    """Old JSON without 'deleted' key defaults to empty list."""
    raw = json.dumps({"skip": ["sports"], "boost": ["tech"]})
    rules = PreferenceRules.from_stored(raw)
    assert rules.recently_deleted == []
    assert rules.skip == ["sports"]
    assert rules.high_priority == ["tech"]


def test_new_keys_take_precedence_over_legacy():
    """When both new and legacy keys exist, new keys win."""
    raw = json.dumps(
        {
            "skip": ["a"],
            "boost": ["legacy"],
            "high_priority": ["new"],
            "deleted": [{"title": "legacy"}],
            "recently_deleted": [{"title": "new"}],
        }
    )
    rules = PreferenceRules.from_stored(raw)
    assert rules.high_priority == ["new"]
    assert rules.recently_deleted == [{"title": "new"}]
