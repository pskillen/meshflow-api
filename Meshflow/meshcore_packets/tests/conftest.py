FEEDER_MC_PUBKEY = "a" * 64
FEEDER_MC_PUBKEY_PREFIX = "a" * 12
FEEDER_B_MC_PUBKEY = "c" * 64
FEEDER_B_MC_PUBKEY_PREFIX = "c" * 12


def feeder_url(name: str, prefix: str) -> str:
    """Reverse feeder-scoped meshcore URL."""
    from django.urls import reverse

    return reverse(name, kwargs={"feeder_pubkey_prefix": prefix})
