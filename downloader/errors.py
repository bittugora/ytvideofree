"""Error normalization helpers shared by the JSON API views."""

NETWORK_BLOCKED_MESSAGE = (
    "The web server process cannot reach YouTube over HTTPS. "
    "Restart the app from a normal terminal, or deploy it on a host that allows outbound HTTPS to youtube.com. "
    "This same network block affects video, MP3, and transcript requests."
)

BOT_CHECK_MESSAGE = (
    "YouTube blocked this request with a bot check (“Sign in to confirm you’re not a bot”). "
    "This is not a problem with the link you pasted. Please try again in a little while."
)


def clean_error(exc: Exception) -> str:
    message = str(exc).strip()
    message = message.replace("ERROR:", "").strip()
    if is_network_permission_error(message):
        return NETWORK_BLOCKED_MESSAGE
    if is_bot_check_error(message):
        return BOT_CHECK_MESSAGE
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


def is_bot_check_error(message: str) -> bool:
    """Detect yt-dlp's YouTube bot-check rejection."""
    normalized = message.lower()
    return (
        "confirm you're not a bot" in normalized
        or "confirm you are not a bot" in normalized
        or ("cookies-from-browser" in normalized and "cookies" in normalized)
    )
