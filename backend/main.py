"""CFG2PDA: educational CFG parser, validator, converter, and PDA simulator."""
from collections import deque
from typing import Any
import re
import json
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

EPSILON = "ε"
BOTTOM = "Z0"
MAX_STEPS = 5000
MAX_CONFIGURATIONS = 10000
MAX_STACK_DEPTH = 200
MAX_INPUT_LENGTH = 10000
MAX_SIMULATION_SECONDS = 2.0

app = FastAPI(title="CFG2PDA API", version="1.0.0", description="Convert context-free grammars to PDAs and simulate strings.")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class Production(BaseModel):
    left: str
    right: list[str]

class GrammarRequest(BaseModel):
    variables: list[str] = Field(default_factory=list)
    terminals: list[str] = Field(default_factory=list)
    production_text: str = ""
    start_symbol: str = "S"

class Grammar(BaseModel):
    variables: list[str]
    terminals: list[str]
    productions: list[Production]
    start_symbol: str

class ValidationRequest(Grammar):
    pass

class ConvertRequest(Grammar):
    pass

class SimulateRequest(BaseModel):
    pda: dict[str, Any]
    input_string: str = ""
    max_steps: int = Field(default=MAX_STEPS, ge=1, le=100000)
    max_configurations: int = Field(default=MAX_CONFIGURATIONS, ge=1, le=100000)
    max_stack_depth: int = Field(default=MAX_STACK_DEPTH, ge=1, le=2000)


class ApiValidationRequest(BaseModel):
    request_text: str
    grammar: Grammar | None = None
    check_structure: bool = True
    max_input_size: int = Field(default=100000, ge=1, le=1000000)


SHOPPING_GRAMMAR = Grammar(
    variables=["S", "L"],
    terminals=["o", "i", "a", "x", "c"],
    productions=[
        Production(left="S", right=["o", "i", "a", "L", "c"]),
        Production(left="L", right=["x", "L"]),
        Production(left="L", right=[EPSILON]),
    ],
    start_symbol="S",
)


def shopping_structure_tokens(value: Any) -> str:
    """Encode validated shopping-order structure for the CFG/PDA pipeline."""
    if not isinstance(value, dict) or set(value) != {"order"}:
        return ""
    order = value["order"]
    if not isinstance(order, dict) or set(order) != {"items"} or not isinstance(order["items"], list):
        return ""
    tokens = "oia"
    for item in order["items"]:
        if not isinstance(item, dict) or set(item) != {"product", "quantity"}:
            return ""
        if not isinstance(item["product"], str) or not isinstance(item["quantity"], int) or isinstance(item["quantity"], bool) or item["quantity"] < 1:
            return ""
        tokens += "x"
    return tokens + "c"


def validate_api_request(request_text: str, grammar: Grammar | None = None, max_input_size: int = 100000, check_structure: bool = True) -> dict[str, Any]:
    if len(request_text.encode("utf-8")) > max_input_size:
        return {"syntax": {"valid": False, "status": "limit_reached", "message": "Request exceeds the maximum input size."}, "structure": None}
    try:
        parsed = json.loads(request_text)
    except (json.JSONDecodeError, TypeError, RecursionError) as exc:
        return {"syntax": {"valid": False, "status": "invalid_json", "message": f"Invalid JSON: {exc}"}, "structure": None}
    if not check_structure:
        return {"syntax": {"valid": True, "status": "valid_json", "message": "JSON syntax is valid."}, "structure": None}

    selected = SHOPPING_GRAMMAR
    structural_input = shopping_structure_tokens(parsed)
    if not structural_input:
        return {
            "syntax": {"valid": True, "status": "valid_json", "message": "JSON syntax is valid."},
            "structure": {"status": "rejected", "message": "JSON does not match the shopping-order structure.", "input": ""},
        }
    validation = validate_grammar(selected)
    if not validation["valid"]:
        return {"syntax": {"valid": True, "status": "valid_json", "message": "JSON syntax is valid."}, "structure": {"status": "invalid_grammar", "message": validation["message"], "validation": validation}}
    pda = build_pda(selected)
    simulation = simulate(pda, structural_input)
    return {
        "syntax": {"valid": True, "status": "valid_json", "message": "JSON syntax is valid."},
        "structure": {"status": simulation["status"], "message": simulation["message"], "input": structural_input, "trace": simulation["trace"], "configurations_explored": simulation["configurations_explored"]},
    }


def boundary_test_case(case_id: str, category: str, expected: str, callback) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        actual = callback()
        status = "PASS" if actual == expected else "FAIL"
        return {"id": case_id, "category": category, "expected": expected, "actual": actual, "status": status, "duration_ms": round((time.perf_counter() - started) * 1000, 2)}
    except Exception as exc:
        return {"id": case_id, "category": category, "expected": expected, "actual": None, "status": "ERROR", "error": str(exc), "duration_ms": round((time.perf_counter() - started) * 1000, 2)}


def run_boundary_tests() -> dict[str, Any]:
    cases = []
    valid = Grammar(variables=["S"], terminals=["a", "b"], productions=parse_productions("S → aSb | ε"), start_symbol="S")
    def parse_status(text: str) -> str:
        try:
            parse_productions(text)
            return "PASS"
        except ValueError:
            return "ERROR"
    pda = build_pda(valid)
    cases.extend([
        boundary_test_case("grammar-empty", "Grammar Validation", "ERROR", lambda: parse_status("")),
        boundary_test_case("grammar-missing-start", "Grammar Validation", False, lambda: validate_grammar(Grammar(variables=["S"], terminals=["a"], productions=parse_productions("S → a"), start_symbol=""))["valid"]),
        boundary_test_case("grammar-undefined-start", "Grammar Validation", False, lambda: validate_grammar(Grammar(variables=["S"], terminals=["a"], productions=parse_productions("S → a"), start_symbol="A"))["valid"]),
        boundary_test_case("grammar-invalid-rule", "Grammar Validation", "ERROR", lambda: parse_status("S a")),
        boundary_test_case("grammar-epsilon", "Grammar Validation", True, lambda: validate_grammar(valid)["valid"]),
        boundary_test_case("grammar-unreachable-warning", "Grammar Validation", True, lambda: validate_grammar(Grammar(variables=["S", "A"], terminals=["a"], productions=parse_productions("S → a"), start_symbol="S"))["valid"]),
        boundary_test_case("input-empty", "Input Recognition", "accepted", lambda: simulate(pda, "")["status"]),
        boundary_test_case("input-ab", "Input Recognition", "accepted", lambda: simulate(pda, "ab")["status"]),
        boundary_test_case("input-aabb", "Input Recognition", "accepted", lambda: simulate(pda, "aabb")["status"]),
        boundary_test_case("input-aaabbb", "Input Recognition", "accepted", lambda: simulate(pda, "aaabbb")["status"]),
        boundary_test_case("input-aab", "Input Recognition", "rejected", lambda: simulate(pda, "aab")["status"]),
        boundary_test_case("input-abb", "Input Recognition", "rejected", lambda: simulate(pda, "abb")["status"]),
        boundary_test_case("pda-step-limit", "Resource Limits", "limit_reached", lambda: simulate(pda, "aabb", max_steps=1)["status"]),
        boundary_test_case("pda-invalid-symbol", "PDA Simulation", "invalid_input", lambda: simulate(pda, "abc")["status"]),
        boundary_test_case("api-valid-order", "API Structure Validation", "accepted", lambda: validate_api_request(json.dumps({"order": {"items": [{"product": "Laptop", "quantity": 1}]}}))["structure"]["status"]),
        boundary_test_case("api-missing-field", "API Structure Validation", "rejected", lambda: validate_api_request('{"order":{"items":[{"product":"Laptop"}]}}')["structure"]["status"]),
        boundary_test_case("api-invalid-json", "API Structure Validation", "invalid_json", lambda: validate_api_request('{"order":')["syntax"]["status"]),
    ])
    summary = {status: sum(1 for case in cases if case["status"] == status) for status in ("PASS", "FAIL", "ERROR")}
    summary["not_run"] = 0
    return {"executed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "tests": cases, "summary": {"total": len(cases), **summary}, "duration_ms": round(sum(case["duration_ms"] for case in cases), 2)}


def tokenize_symbols(value: str) -> list[str]:
    """Read whitespace-separated symbols, or compact single-character symbols."""
    value = value.strip()
    if not value:
        return []
    if any(ch.isspace() for ch in value):
        return value.split()
    return list(value)


def normalize_epsilon(value: str) -> str:
    return EPSILON if value.strip().lower() in {"ε", "eps", "epsilon", "λ", "lambda"} else value.strip()


def parse_productions(text: str) -> list[Production]:
    productions: list[Production] = []
    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        arrows = re.findall(r"->|→", line)
        if len(arrows) != 1:
            raise ValueError(f"Line {line_no}: use exactly one production arrow (→ or ->).")
        left, rhs_text = re.split(r"->|→", line, maxsplit=1)
        left = left.strip()
        if not left or not rhs_text.strip():
            raise ValueError(f"Line {line_no}: production left and right sides cannot be empty.")
        if any(ch in left for ch in " |→-") or len(left) != 1:
            raise ValueError(f"Line {line_no}: the left side must be one uppercase variable, such as S.")
        for alternative in rhs_text.split("|"):
            alternative = alternative.strip()
            if not alternative:
                raise ValueError(f"Line {line_no}: empty alternative; write ε explicitly for the empty string.")
            compact = alternative.replace(" ", "")
            if compact.lower() in {"ε", "eps", "epsilon", "λ", "lambda"}:
                rhs = [EPSILON]
            else:
                if any(alias in compact.lower() for alias in ("epsilon", "lambda", "eps")) or EPSILON in compact or "λ" in compact:
                    raise ValueError(f"Line {line_no}: epsilon must appear alone on the right-hand side.")
                rhs = list(compact)
            productions.append(Production(left=left, right=rhs))
    if not productions:
        raise ValueError("Enter at least one production rule.")
    return productions


def production_text(grammar: Grammar) -> str:
    grouped: dict[str, list[str]] = {}
    for p in grammar.productions:
        rhs = EPSILON if p.right == [EPSILON] or not p.right else "".join(p.right)
        grouped.setdefault(p.left, []).append(rhs)
    return "\n".join(f"{left} → {' | '.join(alts)}" for left, alts in grouped.items())


def validate_grammar(grammar: Grammar) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    info: list[dict[str, str]] = []
    vars_, terms = grammar.variables, grammar.terminals
    def error(code: str, message: str): errors.append({"type": code, "message": message})
    if not vars_: error("MISSING_VARIABLES", "Declare at least one variable.")
    if len(vars_) != len(set(vars_)): error("DUPLICATE_VARIABLE", "Variables must be unique.")
    if len(terms) != len(set(terms)): error("DUPLICATE_TERMINAL", "Terminals must be unique.")
    for v in vars_:
        if len(v) != 1 or not v.isupper() or not v.isalpha(): error("INVALID_VARIABLE", f"Variable '{v}' must be one uppercase letter.")
    for t in terms:
        if len(t) != 1 or t in {EPSILON, "λ", "|", "→"} or t.isspace() or t.isupper(): error("INVALID_TERMINAL", f"Terminal '{t}' must be one non-uppercase, non-epsilon symbol.")
    overlap = set(vars_) & set(terms)
    if overlap: error("ALPHABET_OVERLAP", f"Variables and terminals overlap: {', '.join(sorted(overlap))}.")
    if grammar.start_symbol not in vars_: error("INVALID_START_SYMBOL", f"Start symbol '{grammar.start_symbol}' is not a declared variable.")
    if not grammar.productions: error("MISSING_PRODUCTIONS", "At least one production is required.")
    seen: set[tuple[str, tuple[str, ...]]] = set()
    lefts: set[str] = set()
    for p in grammar.productions:
        if p.left not in vars_: error("INVALID_LHS", f"Left side '{p.left}' is not a declared variable.")
        lefts.add(p.left)
        key = (p.left, tuple(p.right))
        if key in seen: warnings.append({"type": "DUPLICATE_PRODUCTION", "message": f"Duplicate production detected: {p.left} → {''.join(p.right)}"})
        seen.add(key)
        if not p.right: error("EMPTY_RHS", f"Production {p.left} has an empty right side; use ε.")
        if EPSILON in p.right and p.right != [EPSILON]: error("EPSILON_PLACEMENT", "Epsilon must appear alone on the right-hand side.")
        for symbol in p.right:
            if symbol == EPSILON: continue
            if symbol not in vars_ and symbol not in terms: error("UNDECLARED_SYMBOL", f"Symbol '{symbol}' in production {p.left} → {''.join(p.right)} is not declared.")
    for v in vars_:
        if v not in lefts: warnings.append({"type": "NO_PRODUCTION", "message": f"Variable '{v}' has no production."})
    if not errors: info.append({"type": "VALID", "message": "Grammar is structurally valid."})
    return {"valid": not errors, "message": "Grammar is valid" if not errors else "Grammar has validation errors", "errors": errors, "warnings": warnings, "info": info}


def build_pda(grammar: Grammar) -> dict[str, Any]:
    transitions = [{"from_state": "q0", "input_symbol": EPSILON, "stack_top": BOTTOM, "to_state": "q1", "push_symbols": [grammar.start_symbol, BOTTOM], "description": f"Push start symbol {grammar.start_symbol}"}]
    for p in grammar.productions:
        push = [] if p.right == [EPSILON] else p.right
        rhs = EPSILON if not push else "".join(push)
        transitions.append({"from_state": "q1", "input_symbol": EPSILON, "stack_top": p.left, "to_state": "q1", "push_symbols": push, "description": f"Apply production {p.left} → {rhs}"})
    for terminal in grammar.terminals:
        transitions.append({"from_state": "q1", "input_symbol": terminal, "stack_top": terminal, "to_state": "q1", "push_symbols": [], "description": f"Match terminal {terminal}"})
    transitions.append({"from_state": "q1", "input_symbol": EPSILON, "stack_top": BOTTOM, "to_state": "qf", "push_symbols": [], "description": "Accept after the input is consumed and the bottom marker is reached"})
    return {"states": ["q0", "q1", "qf"], "input_alphabet": grammar.terminals, "stack_alphabet": list(dict.fromkeys(grammar.variables + grammar.terminals + [BOTTOM])), "start_state": "q0", "start_stack_symbol": BOTTOM, "accept_states": ["qf"], "acceptance_mode": "final_state", "stack_convention": "TOP_TO_BOTTOM", "transitions": transitions}


def conversion_steps(grammar: Grammar) -> list[str]:
    steps = ["Create states q0 (initialization), q1 (processing), and qf (accepting).", f"Initialize the stack by replacing {BOTTOM} with {grammar.start_symbol} {BOTTOM}."]
    for p in grammar.productions:
        rhs = EPSILON if p.right == [EPSILON] else "".join(p.right)
        steps.append(f"For production {p.left} → {rhs}, add an ε-transition that replaces stack-top {p.left} with {rhs}.")
    for t in grammar.terminals: steps.append(f"Add a transition that consumes '{t}' and pops the matching terminal '{t}' from the stack.")
    steps.append(f"When all input is consumed and {BOTTOM} is on top, pop it and enter qf. Acceptance is by final state.")
    return steps


def simulate(
    pda: dict[str, Any],
    input_string: str,
    max_steps: int = MAX_STEPS,
    max_configurations: int = MAX_CONFIGURATIONS,
    max_stack_depth: int = MAX_STACK_DEPTH,
) -> dict[str, Any]:
    """Explore PDA configurations with BFS and return an accepting path if one exists.

    Each queue item carries its own trace. This is important: using a shared
    'best trace' while exploring branches can accidentally mix two paths.
    """
    alphabet = set(pda.get("input_alphabet", []))
    normalized_input = "" if input_string.strip().lower() in {"ε", "eps", "epsilon", "λ", "lambda"} else input_string
    if len(normalized_input) > MAX_INPUT_LENGTH:
        return {"status": "limit_reached", "message": f"Input exceeds the maximum length of {MAX_INPUT_LENGTH} symbols.", "steps": 0, "trace": [], "configurations_explored": 0}
    for symbol in normalized_input:
        if symbol not in alphabet:
            return {
                "status": "invalid_input",
                "message": f"Invalid input: symbol '{symbol}' is not part of the grammar's terminal alphabet.",
                "steps": 0,
                "trace": [],
                "configurations_explored": 0,
            }

    transitions = pda.get("transitions", [])
    start = (pda.get("start_state", "q0"), 0, (pda.get("start_stack_symbol", BOTTOM),))
    initial_trace = [{
        "step": 0,
        "state": start[0],
        "input_position": 0,
        "remaining_input": normalized_input,
        "consumed_input": "",
        "stack": list(start[2]),
        "action": "Initialize PDA",
        "transition": None,
    }]
    queue = deque([(start, initial_trace)])
    visited = {start}
    explored = 0
    limit_reached = False
    longest_trace = initial_trace
    accept_states = set(pda.get("accept_states", []))
    started_at = time.perf_counter()

    while queue:
        if time.perf_counter() - started_at >= MAX_SIMULATION_SECONDS:
            limit_reached = True
            break
        (state, pos, stack), trace = queue.popleft()
        if len(trace) > len(longest_trace):
            longest_trace = trace

        # Acceptance requires BOTH a final state and fully consumed input.
        if state in accept_states and pos == len(normalized_input):
            return {
                "status": "accepted",
                "message": "String accepted by the PDA.",
                "steps": len(trace) - 1,
                "trace": trace,
                "configurations_explored": explored,
            }

        if explored >= max_configurations:
            limit_reached = True
            break
        explored += 1

        if len(trace) - 1 >= max_steps:
            # Mark a limit only if at least one transition is actually applicable.
            # A dead-end at the depth boundary is still a genuine dead-end.
            can_continue = False
            for tr in transitions:
                if tr.get("from_state") != state or not stack or tr.get("stack_top") != stack[0]:
                    continue
                symbol = tr.get("input_symbol", EPSILON)
                if symbol == EPSILON or (pos < len(normalized_input) and normalized_input[pos] == symbol):
                    can_continue = True
                    break
            if can_continue:
                limit_reached = True
            continue

        for tr in transitions:
            if tr.get("from_state") != state or not stack or tr.get("stack_top") != stack[0]:
                continue
            symbol = tr.get("input_symbol", EPSILON)
            if symbol == EPSILON:
                new_pos = pos
            elif pos < len(normalized_input) and normalized_input[pos] == symbol:
                new_pos = pos + 1
            else:
                continue

            pushed = tr.get("push_symbols", [])
            new_stack = tuple(pushed + list(stack[1:]))
            if len(new_stack) > max_stack_depth:
                limit_reached = True
                continue

            new_cfg = (tr.get("to_state"), new_pos, new_stack)
            if new_cfg in visited:
                continue
            visited.add(new_cfg)
            action = tr.get("description", "Apply transition")
            new_trace = trace + [{
                "step": len(trace),
                "state": new_cfg[0],
                "input_position": new_pos,
                "remaining_input": normalized_input[new_pos:],
                "consumed_input": normalized_input[:new_pos],
                "stack": list(new_stack),
                "action": action,
                "transition": tr,
            }]
            queue.append((new_cfg, new_trace))

    if limit_reached:
        message = "Simulation stopped at a configured safety limit; rejection cannot be confirmed."
        status = "limit_reached"
    else:
        message = "No accepting PDA path was found for this input."
        status = "rejected"
    return {
        "status": status,
        "message": message,
        "steps": len(longest_trace) - 1,
        "trace": longest_trace,
        "configurations_explored": explored,
    }

EXAMPLES = [
    {"id": "anbn", "name": "aⁿbⁿ", "variables": ["S"], "terminals": ["a", "b"], "start_symbol": "S", "production_text": "S → aSb | ε", "default_input": "aabb", "accepted": ["ε", "ab", "aabb", "aaabbb"], "rejected": ["a", "abb", "aab", "abab"]},
    {"id": "parentheses", "name": "Balanced parentheses", "variables": ["S"], "terminals": ["(", ")"], "start_symbol": "S", "production_text": "S → (S)S | ε", "default_input": "()()", "accepted": ["ε", "()", "(())", "()()", "(()())"], "rejected": ["(", ")(", "(()", "())"]},
    {"id": "endsb", "name": "Strings ending in b", "variables": ["S"], "terminals": ["a", "b"], "start_symbol": "S", "production_text": "S → aS | b", "default_input": "aab", "accepted": ["b", "ab", "aab", "aaab"], "rejected": ["ε", "a", "ba", "abb"]},
    {"id": "palindrome", "name": "Palindromes over {a, b}", "variables": ["S"], "terminals": ["a", "b"], "start_symbol": "S", "production_text": "S → aSa | bSb | a | b | ε", "default_input": "abba", "accepted": ["ε", "a", "b", "aba", "abba", "baab"], "rejected": ["ab", "aab", "abb", "abab"]},
    {"id": "anbn-positive", "name": "aⁿbⁿ (n ≥ 1)", "variables": ["S"], "terminals": ["a", "b"], "start_symbol": "S", "production_text": "S → aSb | ab", "default_input": "aabb", "accepted": ["ab", "aabb", "aaabbb"], "rejected": ["ε", "a", "abb", "abab"]},
    {"id": "only-a", "name": "Only a's", "variables": ["S"], "terminals": ["a"], "start_symbol": "S", "production_text": "S → aS | ε", "default_input": "aaa", "accepted": ["ε", "a", "aa", "aaa"], "rejected": ["b", "ab", "ba"]},
    {"id": "even-a", "name": "Even number of a's", "variables": ["S", "A"], "terminals": ["a", "b"], "start_symbol": "S", "production_text": "S → bS | aA | ε\nA → bA | aS", "default_input": "aba", "accepted": ["ε", "b", "bb", "aa", "aba", "aabb", "abab", "baa"], "rejected": ["a", "ab", "aaa"]},
    {"id": "a-plus-b-plus", "name": "One or more a's then b's", "variables": ["S", "A"], "terminals": ["a", "b"], "start_symbol": "S", "production_text": "S → aS | aA\nA → bA | b", "default_input": "aabb", "accepted": ["ab", "aab", "abb", "aabb", "aaabbb"], "rejected": ["ε", "a", "b", "ba", "abab"]},
]

@app.get("/health")
def health(): return {"status": "ok", "service": "CFG2PDA API"}

@app.get("/api/examples")
def get_examples(): return EXAMPLES

@app.post("/api/grammar/parse")
def parse_api(request: GrammarRequest):
    try:
        grammar = Grammar(variables=request.variables, terminals=request.terminals, productions=parse_productions(request.production_text), start_symbol=request.start_symbol.strip())
        result = grammar.model_dump()
        result["normalized_text"] = production_text(grammar)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@app.post("/api/grammar/validate")
def validate_api(grammar: ValidationRequest): return validate_grammar(grammar)

@app.post("/api/grammar/summary")
def summary_api(grammar: ValidationRequest):
    validation = validate_grammar(grammar)
    return {"validation": validation, "variables_count": len(grammar.variables), "terminals_count": len(grammar.terminals), "productions_count": len(grammar.productions), "start_symbol": grammar.start_symbol, "contains_epsilon": any(p.right == [EPSILON] for p in grammar.productions), "normalized_productions": [f"{p.left} → {EPSILON if p.right == [EPSILON] else ''.join(p.right)}" for p in grammar.productions]}

@app.post("/api/pda/convert")
def convert_api(grammar: ConvertRequest):
    validation = validate_grammar(grammar)
    if not validation["valid"]: raise HTTPException(status_code=422, detail={"message":"Cannot convert an invalid grammar.", **validation})
    return {"pda": build_pda(grammar), "conversion_steps": conversion_steps(grammar)}

@app.post("/api/pda/simulate")
def simulate_api(request: SimulateRequest):
    try:
        return simulate(request.pda, request.input_string, request.max_steps, request.max_configurations, request.max_stack_depth)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Invalid PDA data supplied for simulation.") from exc

@app.post("/api/api-validator")
def api_validator(request: ApiValidationRequest):
    return validate_api_request(request.request_text, request.grammar, request.max_input_size, request.check_structure)

@app.post("/api/boundary-tests")
def boundary_tests():
    return run_boundary_tests()
