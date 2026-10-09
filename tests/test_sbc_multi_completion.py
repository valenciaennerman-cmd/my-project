import pytest
from app.services.sbc.models import CanonicalPlayer, NormalizedChallenge, Requirement
from app.services.sbc.multi_completion import MultiCompletionEngine

def test_single_completion():
    pool = [
        CanonicalPlayer(item_id="1", name="A", rating=80, market_price=1000),
        CanonicalPlayer(item_id="2", name="B", rating=80, market_price=1000)
    ]
    challenge = NormalizedChallenge(challenge_id="c1", name="Test", type="NORMAL", required_player_count=1)
    
    engine = MultiCompletionEngine(pool)
    completions = engine.solve(challenge, num_completions=1)
    
    assert len(completions) == 1
    assert len(completions[0]) == 1

def test_two_completions_no_reuse():
    pool = [
        CanonicalPlayer(item_id="1", name="A", rating=80, market_price=1000),
        CanonicalPlayer(item_id="2", name="B", rating=80, market_price=1000)
    ]
    challenge = NormalizedChallenge(challenge_id="c1", name="Test", type="NORMAL", required_player_count=1)
    
    engine = MultiCompletionEngine(pool)
    completions = engine.solve(challenge, num_completions=2)
    
    assert len(completions) == 2
    assert len(completions[0]) == 1
    assert len(completions[1]) == 1
    assert completions[0][0].item_id != completions[1][0].item_id

def test_n_completions_not_enough_players():
    pool = [
        CanonicalPlayer(item_id="1", name="A", rating=80, market_price=1000)
    ]
    challenge = NormalizedChallenge(challenge_id="c1", name="Test", type="NORMAL", required_player_count=1)
    
    engine = MultiCompletionEngine(pool)
    completions = engine.solve(challenge, num_completions=2)
    
    assert len(completions) == 1 # Only one possible because pool is exhausted
    
def test_streamlined_multi_completion():
    pool = [
        CanonicalPlayer(item_id="1", name="A", rating=80, item_score=50, market_price=1000),
        CanonicalPlayer(item_id="2", name="B", rating=80, item_score=50, market_price=1000)
    ]
    challenge = NormalizedChallenge(
        challenge_id="c2", 
        name="Test Streamlined", 
        type="STREAMLINED", 
        required_player_count=1,
        score_requirement=50
    )
    
    engine = MultiCompletionEngine(pool)
    completions = engine.solve(challenge, num_completions=2)
    
    assert len(completions) == 2
    assert len(completions[0]) == 1
    assert len(completions[1]) == 1
    assert completions[0][0].item_id != completions[1][0].item_id
