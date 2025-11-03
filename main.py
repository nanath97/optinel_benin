from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
import os
from dotenv import load_dotenv
from core import bot, dp
import bott_webhook
from stripe_webhook import router as stripe_router

load_dotenv()

app = FastAPI()

# === Route Webhook Telegram ===
@app.post("/webhook")   # ✅ URL simple, sans token
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        update = types.Update(**data)
        await dp.process_update(update)
    except Exception as e:
        print("Erreur dans webhook :", e)
        return {"ok": False, "error": str(e)}
    return {"ok": True}


# === Au démarrage de l'app ===
@app.on_event("startup")
async def startup_event():
    try:
        # Initialisation des utilisateurs
        bott_webhook.initialize_authorized_users()
        print(f"[STARTUP] Initialisation des utilisateurs VIP terminée.")

        # Définition du webhook Telegram avec une URL propre
        webhook_url = f"{os.getenv('RENDER_EXTERNAL_URL')}/webhook"
        await bot.set_webhook(webhook_url)
        print(f"✅ Webhook configuré : {webhook_url}")

    except Exception as e:
        print(f"[STARTUP ERROR] Erreur pendant le chargement des VIP ou webhook : {e}")


# === Stripe Webhook ===
app.include_router(stripe_router)

print("🔥 >>> FICHIER MAIN.PY BIEN LANCÉ <<< 🔥")
