from tradingcat.services.ai_researcher import AIFeature, AIResearcher


def test_journal_prompt_restricts_ai_to_structured_facts(tmp_path):
    prompt = AIResearcher(api_key="", data_dir=tmp_path)._system_prompt(AIFeature.JOURNAL)

    assert "daily_data.structured_report" in prompt
    assert "do not invent missing facts" in prompt
    assert "do not generate buy/sell/hold" in prompt
