"""Template context processors for the downloader app."""


def site_context(request):
    """Expose the absolute origin (scheme + host) for canonical/OG URLs."""
    return {
        "site_url": f"{request.scheme}://{request.get_host()}",
    }
