"""Plain-language display copies; never modify source evidence, thresholds or scores."""

import re


def display_reason(value: str) -> str:
    # Confidence describes the detector, not the probability that an annotation is wrong.
    # Keep it in the raw reason for diagnostics instead of putting it before reviewers.
    text = re.sub(r"\s*\(conf\b[^)]*\)", "", value)
    text = re.sub(r"\s*\(model\s+0\.\d+\)", "", text)
    text = re.sub(r"(model\s+\w+)\s*\(0\.\d+\)", r"\1", text)

    def overlap(match):
        first, comparison, second = match.groups()
        result = f"độ khớp {float(first) * 100:g}%"
        if comparison:
            relation = {"<": "dưới", ">": "trên", "<=": "không quá", ">=": "ít nhất"}[comparison]
            result += f" {relation} {float(second) * 100:g}%"
        return result

    text = re.sub(r"IoU\s*([01](?:\.\d+)?)(?:\s*(<=|>=|<|>)\s*([01](?:\.\d+)?))?", overlap, text)
    text = re.sub(r"\bmodel thấy\b", "máy gợi ý", text, flags=re.IGNORECASE)
    text = re.sub(r"\bModel\b", "Máy", text)
    text = re.sub(r"\bmodel\b", "máy", text)
    text = text.replace("chỗ khác", "vị trí khác")
    return text
