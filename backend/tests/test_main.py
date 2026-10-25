import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import (
    EXAMPLES,
    Grammar,
    Production,
    parse_productions,
    validate_grammar,
    build_pda,
    simulate,
    validate_api_request,
)


def grammar(text="S → aSb | ε", variables=None, terminals=None, start="S"):
    return Grammar(
        variables=variables or ["S"],
        terminals=terminals or ["a", "b"],
        productions=parse_productions(text),
        start_symbol=start,
    )


def test_parser_aliases_and_alternatives():
    parsed = parse_productions("S -> aSb|epsilon\nA → lambda | b")
    assert [p.right for p in parsed] == [["a", "S", "b"], ["ε"], ["ε"], ["b"]]


def test_valid_grammar_and_epsilon_placement():
    assert validate_grammar(grammar())["valid"]
    invalid = Grammar(
        variables=["S"], terminals=["a"],
        productions=[Production(left="S", right=["a", "ε"])], start_symbol="S"
    )
    assert not validate_grammar(invalid)["valid"]


def test_converter_transition_values():
    pda = build_pda(grammar())
    assert pda["states"] == ["q0", "q1", "qf"]
    assert pda["start_stack_symbol"] == "Z0"
    assert any(t["from_state"] == "q1" and t["stack_top"] == "S" and t["push_symbols"] == ["a", "S", "b"] for t in pda["transitions"])
    assert any(t["input_symbol"] == "a" and t["stack_top"] == "a" and not t["push_symbols"] for t in pda["transitions"])
    assert any(t["to_state"] == "qf" and t["stack_top"] == "Z0" for t in pda["transitions"])


def test_anbn_accept_and_reject():
    pda = build_pda(grammar())
    for value in ["", "ab", "aabb", "aaabbb"]:
        result = simulate(pda, value)
        assert result["status"] == "accepted", (value, result)
        assert result["trace"][0]["step"] == 0
        assert result["trace"][-1]["state"] == "qf"
        assert result["trace"][-1]["remaining_input"] == ""
    for value in ["a", "aab", "abb", "abab"]:
        assert simulate(pda, value)["status"] == "rejected", value


def test_invalid_input_and_parentheses():
    pda = build_pda(grammar("S → (S)S | ε", terminals=["(", ")"]))
    assert simulate(pda, "abc")["status"] == "invalid_input"
    for value in ["", "()", "(())", "()()", "(()())"]:
        assert simulate(pda, value)["status"] == "accepted", value
    for value in ["(()", ")(", "())"]:
        assert simulate(pda, value)["status"] == "rejected", value


def test_built_in_examples_match_expected_strings():
    for example in EXAMPLES:
        g = Grammar(
            variables=example["variables"],
            terminals=example["terminals"],
            productions=parse_productions(example["production_text"]),
            start_symbol=example["start_symbol"],
        )
        validation = validate_grammar(g)
        assert validation["valid"], (example["name"], validation)
        pda = build_pda(g)
        for value in example["accepted"]:
            actual = simulate(pda, "" if value == "ε" else value)["status"]
            assert actual == "accepted", (example["name"], value, actual)
        for value in example["rejected"]:
            actual = simulate(pda, "" if value == "ε" else value)["status"]
            assert actual in {"rejected", "invalid_input"}, (example["name"], value, actual)


def test_safety_limit_is_not_reported_as_rejection():
    pda = build_pda(grammar())
    result = simulate(pda, "aabb", max_steps=1, max_configurations=100, max_stack_depth=200)
    assert result["status"] == "limit_reached"


def test_epsilon_alias_input_and_wrong_branch_trace():
    pda = build_pda(grammar())
    assert simulate(pda, "epsilon")["status"] == "accepted"
    result = simulate(pda, "aabb")
    # Every trace row is a valid consecutive step, not a trace borrowed from another BFS branch.
    for index, row in enumerate(result["trace"]):
        assert row["step"] == index
        if index:
            assert row["transition"] is not None
            assert row["transition"]["to_state"] == row["state"]


def test_api_validator_separates_syntax_from_structure():
    valid_json = '{"order":{"items":[{"product":"Laptop","quantity":1}]}}'
    syntax_only = validate_api_request(valid_json, check_structure=False)
    assert syntax_only["syntax"]["status"] == "valid_json"
    assert syntax_only["structure"] is None
    assert validate_api_request(valid_json)["structure"]["status"] == "accepted"
    assert validate_api_request('{"order":')["syntax"]["status"] == "invalid_json"
    assert validate_api_request('{"order":{"items":[{"product":"Laptop"}]}}')["structure"]["status"] == "rejected"


def test_common_ascii_grammar_forms_and_limits():
    grammar_value = Grammar(
        variables=["S"], terminals=["a", "b"],
        productions=parse_productions("S -> a S b | epsilon"), start_symbol="S"
    )
    assert simulate(build_pda(grammar_value), "aabb")["status"] == "accepted"
    limited = simulate(build_pda(grammar_value), "aabb", max_steps=1)
    assert limited["status"] == "limit_reached"
