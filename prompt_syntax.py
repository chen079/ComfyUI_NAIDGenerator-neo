import re


def _parse_prompt(prompt):
    result = []
    text = ""
    stack = [{"weight": 1.0, "data": result}]

    for character in prompt:
        if character not in "()":
            text += character
            continue
        if character == "(":
            if text:
                stack[-1]["data"].append(text)
            group = {"weight": 1.0, "data": []}
            stack[-1]["data"].append(group)
            stack.append(group)
        else:
            match = re.search(r"^(.*):(-?[0-9.]+)$", text)
            text, weight = match.groups() if match else (text, 1.1)
            if text:
                stack[-1]["data"].append(text)
            stack[-1]["weight"] = float(weight)
            if stack[-1]["data"] is not result:
                stack.pop()
        text = ""

    if text:
        stack[-1]["data"].append(text)
    return result


def _render_prompt(items, weight_per_brace, syntax_mode):
    result = ""
    for item in items:
        if not isinstance(item, dict):
            result += item
            continue
        weight = item["weight"]
        prompt = _render_prompt(item["data"], weight_per_brace, syntax_mode)
        mode = "numeric" if weight < 0 else syntax_mode
        if mode == "brace":
            count = round((weight - 1.0) / weight_per_brace)
            result += "{" * count + "[" * -count + prompt + "}" * count + "]" * -count
        else:
            result += f"{weight:g}::{prompt} ::"
    return result


def prompt_to_nai(prompt, weight_per_brace=0.05, syntax_mode="brace"):
    escaped = prompt.replace(r"\(", "（").replace(r"\)", "）")
    converted = _render_prompt(_parse_prompt(escaped), weight_per_brace, syntax_mode)
    return converted.replace("（", "(").replace("）", ")")
