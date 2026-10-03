"""Entry-point tests: bad config exits 2 without network or secrets."""

import labguard_agent.__main__ as entry


def test_main_rejects_missing_config(monkeypatch, capsys) -> None:
    monkeypatch.delenv("LABGUARD_API_BASE_URL", raising=False)
    monkeypatch.delenv("LABGUARD_AGENT_TOKEN", raising=False)
    code = entry.main([])
    assert code == 2
    assert "LABGUARD_API_BASE_URL" in capsys.readouterr().err
