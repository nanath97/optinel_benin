from fastapi import FastAPI, Request
from aiogram import types
from dotenv import load_dotenv
import os

from core import bot, dp
import bott_webhook
from stripe_webhook import router as stripe_router
from vip_topics import load_vip_topics_from_airtable, load_vip_topics_from_disk, restore_missing_panels, load_annotations_from_airtable 


load_dotenv()

app = FastAPI()


@app.post(f"/bot/{os.getenv('BOT_TOKEN')}")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        update = types.Update(**data)
        await dp.process_update(update)
    except Exception as e:
        print("Erreur dans webhook :", e)
        return {"ok": False, "error": str(e)}
    return {"ok": True}
# 🔁 Alias : compatibilité avec ancienne URL Telegram
@app.post("/webhook")
async def webhook_alias(request: Request):
    return await telegram_webhook(request)


@app.on_event("startup")
async def startup_event():
    try:
        # 1) Recharge les VIP dans authorized_users
        try:
            bott_webhook.initialize_authorized_users()
        except Exception as e:
            print(f"[STARTUP] Warning: initialize_authorized_users a échoué : {e}")

        # 2) Recharge les Topic IDs depuis Airtable (source de vérité)
        await load_vip_topics_from_airtable()

        # 3) Recharge les annotations + panneaux locaux depuis disque (fallback local)
        load_vip_topics_from_disk()

        # 4) Recharge les annotations depuis la nouvelle table Airtable (AnnotationsVIP)
        #    → merge automatiquement note + admin vers _user_topics
        try:
            load_annotations_from_airtable()
        except Exception as e:
            print(f"[ANNOTATION] Échec chargement Airtable : {e}")

        # 5) Recrée les panneaux manquants, avec note/admin si présents
        await restore_missing_panels()

        print("[STARTUP] VIP + topics + annotations initialisés.")
    except Exception as e:
        print(f"[STARTUP ERROR] Erreur pendant le chargement des VIP : {e}")




# Stripe webhook
app.include_router(stripe_router)

print("🔥 >>> FICHIER MAIN.PY BIEN LANCÉ <<< 🔥")
