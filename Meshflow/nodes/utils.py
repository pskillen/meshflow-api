import random

from mnemonic import Mnemonic


def generate_claim_key():
    mnemo = Mnemonic("english")
    # Generate 12-word phrase, then pick 3 random words from it for more entropy
    words = mnemo.generate(strength=128).split()
    selected_words = random.sample(words, 2)
    number = random.randint(10, 99)
    # Join with spaces, append number
    return f"{' '.join(selected_words)} {number}".lower()
