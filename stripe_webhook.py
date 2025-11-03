# stripe_webhook.py

from fastapi import APIRouter, Request, Header
import stripe
import os
from bott_webhook import paiements_recents  # nécessaire
from datetime import datetime

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

@router.get("/stripe/test")
async def test_stripe_route():
    return {"status": "ok"}

@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        print(f"❌ Webhook Stripe invalide : {e}")
        return {"status": "invalid"}

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        montant = int(session["amount_total"] / 100)
        paiements_recents[montant].append(datetime.now())
        print(f"✅ Paiement webhook : {montant}€ enregistré à {datetime.now().isoformat()}")

    return {"status": "ok"}
