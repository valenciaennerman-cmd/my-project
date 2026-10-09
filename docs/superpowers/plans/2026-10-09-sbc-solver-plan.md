# SBC Solver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a robust SBC completion system supporting both Normal and Streamlined SBCs with chemistry, exact EA rating math, multi-completion, and same-rating swap features.

**Architecture:** A layered approach with explicit normalizers, deterministic CP-SAT/MILP solvers, independent verification, and modular swap/repair engines.

**Tech Stack:** Python 3.11+, Google OR-Tools (cp-model).

**Spec:** docs/superpowers/specs/SBC-REQUIREMENTS.md

## Global Constraints
- Do not use an LLM for solving the players; use OR-Tools CP-SAT.
- Ensure mathematically valid exact rating formula.
- Do not reuse owned items within or across multi-completions.
- Every valid squad must pass the independent verifier.

## Review Focus
- Float precision and threshold behavior in rating math.
- Same-rating requirement enforced exactly during swaps.
- Locked/protected players skipped securely.
- Streamlined mode correctly handled separate from Normal 11-player logic.
- Verifier catches duplicate players.

---

### Task 1: Chemistry Mathematics
**Files:**
- Create: `app/services/sbc/chemistry.py`
- Create: `tests/test_sbc_chemistry.py`

**Interfaces:**
- Produces: `calculate_chemistry(squad: List[CanonicalPlayer]) -> int`

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement chemistry calculation logic**
- [ ] **Step 4: Run test to verify it passes**
- [ ] **Step 5: Commit**

---

### Task 2: Rating Mathematics and Normalizer Validation
**Files:**
- Create: `app/services/sbc/rating.py`
- Create: `tests/test_sbc_rating.py`

**Interfaces:**
- Produces: `calculate_team_rating(squad: List[CanonicalPlayer]) -> int`

- [ ] **Step 1: Write the failing tests (including thresholds)**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement exact rating calculation logic**
- [ ] **Step 4: Run test to verify it passes**
- [ ] **Step 5: Commit**

---

### Task 3: Normal Solver Extensions
**Files:**
- Modify: `app/services/sbc/solver_normal.py`
- Create: `tests/test_sbc_solver_normal.py`

**Interfaces:**
- Consumes: Rating and Chemistry logic
- Produces: `CPNormalSolver.solve(...)` with league, nation, club, rarities, etc.

- [ ] **Step 1: Write the failing test for new constraints**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement constraints (league/nation/club/rarity/chemistry)**
- [ ] **Step 4: Run test to verify it passes**
- [ ] **Step 5: Commit**

---

### Task 4: Streamlined Solver Polish
**Files:**
- Modify: `app/services/sbc/solver_streamlined.py`
- Create: `tests/test_sbc_solver_streamlined.py`

- [ ] **Step 1: Write failing tests for overshoot logic and item lock**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Fix Streamlined solver objectives and locks**
- [ ] **Step 4: Run test to verify it passes**
- [ ] **Step 5: Commit**

---

### Task 5: Multi-completion Solver
**Files:**
- Create: `app/services/sbc/multi_completion.py`
- Create: `tests/test_sbc_multi_completion.py`

- [ ] **Step 1: Write the failing tests for N completions**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement multi-completion generation logic**
- [ ] **Step 4: Run test to verify it passes**
- [ ] **Step 5: Commit**

---

### Task 6: Same-Rating Swap and Repair
**Files:**
- Create: `app/services/sbc/swap.py`
- Create: `tests/test_sbc_swap.py`

- [ ] **Step 1: Write failing tests for exact rating swap & repair**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement swap candidate generator and repair logic**
- [ ] **Step 4: Run test to verify it passes**
- [ ] **Step 5: Commit**

---

### Task 7: Independent Verifier Update
**Files:**
- Modify: `app/services/sbc/verifier.py`
- Create: `tests/test_sbc_verifier.py`

- [ ] **Step 1: Write failing tests (adversarial: wrong chemistry, wrong league, duplicate)**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Extend verifier to check all constraint rules**
- [ ] **Step 4: Run test to verify it passes**
- [ ] **Step 5: Commit**

