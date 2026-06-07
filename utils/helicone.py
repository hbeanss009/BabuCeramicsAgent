# utils/helicone.py

def helicone_headers(
    handler: str = "",
    intent:  str = ""
) -> dict:
    """
    Build Helicone custom property headers.
    Pass these into extra_headers on every Claude API call.

    Usage:
        response = client.messages.create(
            model=MODEL,
            system=system_prompt,
            messages=messages,
            extra_headers=helicone_headers(handler="recommendation", intent="recommendation")
        )
    """
    headers = {}

    if handler:
        headers["Helicone-Property-Handler"] = handler

    if intent:
        headers["Helicone-Property-Intent"] = intent

    return headers