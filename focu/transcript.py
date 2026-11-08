"""Normalize actual Open Notebook transcript shapes for all podcast QC paths.

Only extract spoken content. Unknown structures yield empty text; the existing
strict section/headline/figure QC fails closed. Do not infer missing words or
repair provider omissions.
"""

def transcript_text(value):
    """Flatten strings, legacy segments/text and nested dialogue-style episodes.

    Supported real provider response: {"transcript": [
        {"speaker": "...", "dialogue": "..."}, ...
    ]}
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if isinstance(value.get("segments"), list):
            return "\n".join(transcript_text(x) for x in value["segments"])
        for key in ("text", "transcript", "script", "dialogue"):
            if key in value:
                text = transcript_text(value[key])
                if text:
                    return text
        return ""
    if isinstance(value, list):
        return "\n".join(transcript_text(x) for x in value)
    return ""
