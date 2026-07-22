from datetime import timedelta, date
from typing import Tuple

def calculate_sm2(q: int, ef_prev: float, rep_prev: int) -> Tuple[float, int, date]:
    """
    Modified SM-2 Algorithm
    q: 4 = Pass, 1 = Fail
    ef_prev: Previous Easiness Factor (float)
    rep_prev: Previous Repetition Count (int)
    
    Returns: (ef_new, rep_new, next_review_date)
    """
    # 1. Calculate New Easiness Factor
    ef_new = ef_prev + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    ef_new = max(1.30, round(ef_new, 2))  # Strict floor guardrail at 1.30

    # 2. Determine Repetition Count & Review Interval
    if q < 3:
        # Failure reset
        rep_new = 0
        interval_days = 1
    else:
        # Successful recall
        if rep_prev == 0:
            interval_days = 1
        elif rep_prev == 1:
            interval_days = 6
        else:
            interval_days = round(rep_prev * ef_new)
        rep_new = rep_prev + 1

    next_review_date = date.today() + timedelta(days=interval_days)
    return ef_new, rep_new, next_review_date