from detect_links_whitelist import lien_non_autorise  # Pour filtrer les liens
from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ban_storage import ban_list  # Import de la ban_list

import time
import os

# IDs
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DIRECTEUR_ID = int(os.getenv("DIRECTEUR_ID", "0"))
STAFF_GROUP_ID = int(os.getenv("STAFF_GROUP_ID", "0"))

# Utilisateurs jamais limités
EXCLUDED_IDS = {
    ADMIN_ID,
    DIRECTEUR_ID,
    7973689658,   # Ton ID perso (Nathan)
    7334072965,   # ID admin vendeur
}

BOUTONS_AUTORISES = [
    "🔞 Voir le contenu du jour... tout en jouant 🎰",
    "✨Discuter en tant que VIP",
]

# Lien VIP (encore utilisé ailleurs éventuellement)
VIP_URL = "https://buy.stripe.com/7sYfZg2OxenB389gm97AI0G"

# Anti-doublon
_processed_keys = {}
_PROCESSED_TTL = 60


def _prune_processed(now: float):
    for k, ts in list(_processed_keys.items()):
        if now - ts > _PROCESSED_TTL:
            del _processed_keys[k]


class PaymentFilterMiddleware(BaseMiddleware):
    def __init__(self, authorized_users):
        # authorized_users est encore passé, mais NE SERT PLUS à bloquer les messages.
        super(PaymentFilterMiddleware, self).__init__()
        self.authorized_users = authorized_users

    async def on_pre_process_message(self, message: types.Message, data: dict):
        user_id = message.from_user.id
        chat = message.chat

        # Admins / staff jamais bloqués
        if user_id in EXCLUDED_IDS:
            return

        # Le blocage s'applique uniquement en privé
        if chat.type != "private":
            return

        now = time.time()
        _prune_processed(now)
        key = (chat.id, message.message_id)
        if key in _processed_keys:
            return
        _processed_keys[key] = now

        # Ban permanent
        for admin_id, clients_bannis in ban_list.items():
            if user_id in clients_bannis:
                try:
                    await message.delete()
                except:
                    pass
                await message.answer("🚫 Tu as été banni, tu ne peux plus envoyer de messages.")
                raise CancelHandler()

        text = (message.text or "").strip() if message.content_type == types.ContentType.TEXT else ""

        # Autoriser /start
        if text.startswith("/start"):
            return

        # Autoriser boutons ReplyKeyboard
        for b in BOUTONS_AUTORISES:
            if text.startswith(b):
                return

        # Autoriser liens admin (filtrés) quand c'est toi en privé
        if user_id == ADMIN_ID and message.text:
            if lien_non_autorise(message.text):
                try:
                    await message.delete()
                    await message.answer("🚫 Seuls les liens autorisés sont acceptés.")
                except:
                    pass
                raise CancelHandler()
            return

        # 🔁 Nouvelle règle finale :
        # On NE bloque plus les non-VIP ici.
        # Le message passe, et c'est bott_webhook + vip_topics qui gèrent la suite (topics, réponses, etc.).
        return
