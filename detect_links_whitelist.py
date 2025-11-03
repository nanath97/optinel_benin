import os

# Lire les domaines autorisés depuis .env
allowed_domains = os.getenv("ALLOWED_DOMAINS", "")
DOMAINS_AUTORISES = [d.strip().lower() for d in allowed_domains.split(",") if d.strip()]

def lien_non_autorise(text):
    if not text:
        return False

    words = text.split()
    for word in words:
        if word.startswith("http://") or word.startswith("https://"):
            if not any(domain in word.lower() for domain in DOMAINS_AUTORISES):
                return True
    return False
