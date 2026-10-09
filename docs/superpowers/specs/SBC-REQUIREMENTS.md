# SBC Solver Requirements Matrix

| ID | Description | Location | Tests | Status |
|---|---|---|---|---|
| SBC-N-001 | Exact item count | `solver_normal.py` | `test_sbc_normal.py` | IN_PROGRESS |
| SBC-N-002 | Team rating | `solver_normal.py` | `test_sbc_normal.py` | IN_PROGRESS |
| SBC-N-003 | Chemistry | `chemistry.py` | `test_chemistry.py` | NOT_STARTED |
| SBC-N-004 | League/Nation/Club constraints | `solver_normal.py` | `test_sbc_normal.py` | NOT_STARTED |
| SBC-N-005 | Rarity/Special/TOTW constraints | `solver_normal.py` | `test_sbc_normal.py` | IN_PROGRESS |
| SBC-S-001 | Streamlined Item Score mode detection | `normalizer.py` | `test_sbc_streamlined.py` | NOT_STARTED |
| SBC-S-002 | Explicit Item Score | `models.py` | N/A | IMPLEMENTED |
| SBC-S-003 | Item Score target solver | `solver_streamlined.py` | `test_sbc_streamlined.py` | IN_PROGRESS |
| SBC-S-004 | Low-overshoot optimization | `solver_streamlined.py` | `test_sbc_streamlined.py` | IN_PROGRESS |
| SBC-S-005 | Variable item count | `solver_streamlined.py` | `test_sbc_streamlined.py` | IN_PROGRESS |
| SBC-M-001 | Multi completion | `multi_completion.py` | `test_sbc_multi.py` | NOT_STARTED |
| SBC-M-002 | No item reuse across completions | `multi_completion.py` | `test_sbc_multi.py` | NOT_STARTED |
| SBC-W-001 | Strict same-rating swap | `swap.py` | `test_sbc_swap.py` | NOT_STARTED |
| SBC-W-002 | Swap repair | `repair.py` | `test_sbc_swap.py` | NOT_STARTED |
| SBC-V-001 | Independent verification | `verifier.py` | `test_verifier.py` | IN_PROGRESS |
| SBC-V-002 | Diagnostic failures | `verifier.py` | `test_verifier.py` | IN_PROGRESS |
| SBC-G-001 | Lock/protect/exclude | `solver_*.py` | `test_sbc_*.py` | NOT_STARTED |
| SBC-G-002 | Duplicate awareness | `solver_*.py` | `test_sbc_*.py` | NOT_STARTED |
| SBC-U-001 | Settings integration | `sbc.js` | N/A | NOT_STARTED |
| SBC-U-002 | Undo/reverification | `sbc.js` | N/A | NOT_STARTED |
