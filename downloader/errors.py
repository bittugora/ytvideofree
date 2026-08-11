"""Error normalization helpers shared by the JSON API views."""

NETWORK_BLOCKED_MESSAGE = (
    "The web server process cannot reach YouTube over HTTPS. "
    "Restart the app from a normal terminal, or deploy it on a host that allows outbound HTTPS to youtube.com. "
    "This same network block affects video, MP3, and transcript requests."
)


def clean_error(exc: Exception) -> str:
    message = str(exc).strip()
    message = message.replace("ERROR:", "").strip()
    if is_network_permission_error(message):
        return NETWORK_BLOCKED_MESSAGE
    return message or "The request could not be completed."


def is_network_permission_error(message: str) -> bool:
    normalized = message.lower()
    return (
        "winerror 10013" in normalized
        or (
            "failed to establish a new connection" in normalized
            and "access permissions" in normalized
        )
    )
