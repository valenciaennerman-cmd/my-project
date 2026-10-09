import pytest
from app.services.sbc.models import CanonicalPlayer, NormalizedChallenge
from app.services.sbc.multi_completion import MultiCompletionEngine

def test_adversarial_streamlined_multi_completion():
    pool = [
        CanonicalPlayer(definition_id="A", name="A", rating=80, item_score=90, market_price=10, tradeable=True),
        CanonicalPlayer(definition_id="B", name="B", rating=80, item_score=60, market_price=15, tradeable=True),
        CanonicalPlayer(definition_id="C", name="C", rating=80, item_score=40, market_price=100, tradeable=True),
        CanonicalPlayer(definition_id="D", name="D", rating=80, item_score=10, market_price=100, tradeable=True)
    ]

    challenge = NormalizedChallenge(
        challenge_id="adv_1",
        name="Adversarial Streamlined",
        type="STREAMLINED",
        required_player_count=2,
        score_requirement=100
    )

    engine = MultiCompletionEngine(pool)
    completions = engine.solve(challenge, num_completions=2)

    assert len(completions) == 2, f"Expected 2 completions, got {len(completions)}"
