from core import bot, dp
from aiogram import types
import os
from datetime import datetime
from aiogram.dispatcher.handler import CancelHandler
import requests
from core import authorized_users
from detect_links_whitelist import lien_non_autorise
from collections import defaultdict
from datetime import datetime, timedelta
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ban_storage import ban_list
from middlewares.payment_filter import PaymentFilterMiddleware, reset_free_quota



dp.middleware.setup(PaymentFilterMiddleware(authorized_users))


# Dictionnaire temporaire pour stocker les derniers messages de chaque client
last_messages = {}
ADMIN_ID = 7973689658
authorized_admin_ids = [ADMIN_ID]

# Constantes pour le bouton VIP et la vidéo de bienvenue (défaut)
VIP_URL = "https://buy.stripe.com/3cIdR860JcftfUV4Dr7AI0X"
WELCOME_VIDEO_FILE_ID = "BAACAgQAAxkBAAMlaQs2G6IJCml5_CaJz70fbfjbsmMAAmoYAALUCVlQOuaVvRH37Ag2BA"



pending_mass_message = {}
admin_modes = {}  # Clé = admin_id, Valeur = "en_attente_message"

# Mapping entre ID Telegram des admins et leur email dans Airtable 19juillet 2025 debut
ADMIN_EMAILS = {
    int(os.getenv("ADMIN_TELEGRAM_ID")): os.getenv("SELLER_EMAIL"),
}
# Mapping entre ID Telegram des admins et leur email dans Airtable 19juillet 2025 fin


# Paiements validés par Stripe, stockés temporairement
paiements_recents = defaultdict(list)  # ex : {14: [datetime1, datetime2]}


# 1.=== Variables globales ===
DEFAULT_FLOU_IMAGE_FILE_ID = "AgACAgQAAxkBAAMoaQs52KNAvKpLbRRMFw5TPIZnErEAAq0LaxvUCVlQMpk5Gjnw34UBAAMCAAN4AAM2BA" # Remplace par le vrai file_id Telegram


# Fonction de détection de lien non autorisé
ALLOWED_DOMAINS = os.getenv("ALLOWED_DOMAINS", "").split(",")

# --- CONFIGURATION AIRTABLE ---
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("BASE_ID")
TABLE_NAME = os.getenv("TABLE_NAME")
SELLER_EMAIL = os.getenv("SELLER_EMAIL")  # ✅ ici



# ADMIN ID
ADMIN_ID = 7973689658 # 22
DIRECTEUR_ID = 7334072965  # ID personnel au ceo pour avertir des fraudeurs

# === MEDIA EN ATTENTE ===
contenus_en_attente = {}  # { user_id: {"file_id": ..., "type": ..., "caption": ...} }
paiements_en_attente_par_user = set()  # Set de user_id qui ont payé
# === FIN MEDIA EN ATTENTE ===

# === 221097 DEBUT

def initialize_authorized_users():
    try:
        SELLER_EMAIL = os.getenv("SELLER_EMAIL")
        url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
        params = {
            "filterByFormula": f"AND({{Type acces}}='VIP', {{Email}}='{SELLER_EMAIL}')"
        }
        headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        for record in data.get("records", []):
            telegram_id = record.get("fields", {}).get("ID Telegram")
            if telegram_id:
                try:
                    authorized_users.add(int(telegram_id))
                except ValueError:
                    print(f"[WARN] ID Telegram invalide : {telegram_id}")
        print(f"[INFO] {len(authorized_users)} utilisateurs VIP chargés depuis Airtable pour {SELLER_EMAIL}.")
    except Exception as e:
        print(f"[ERROR] Impossible de charger les VIP depuis Airtable : {e}")

# === 221097 FIN


# === Statistiques ===
@dp.message_handler(commands=["stat"])
async def handle_stat(message: types.Message):
    await bot.send_message(message.chat.id, "📥 Traitement de tes statistiques de vente en cours...")

    try:
        SELLER_EMAIL = os.getenv("SELLER_EMAIL")  # ✅ Email vendeur depuis le .env
        url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
        headers = {
            "Authorization": f"Bearer {AIRTABLE_API_KEY}"
        }

        response = requests.get(url, headers=headers)
        data = response.json()

        ventes_totales = 0
        ventes_jour = 0
        contenus_vendus = 0
        vip_ids = set()

        today = datetime.now().date().isoformat()
        mois_courant = datetime.now().strftime("%Y-%m")

        for record in data.get("records", []):
            fields = record.get("fields", {})
            email = fields.get("Email", "")

            # ✅ Filtre pour n’inclure que les ventes du vendeur courant
            if email != SELLER_EMAIL:
                continue

            user_id = fields.get("ID Telegram", "")
            type_acces = fields.get("Type acces", "").lower()
            date_str = fields.get("Date", "")
            mois = fields.get("Mois", "")
            montant = float(fields.get("Montant", 0))

            if type_acces == "vip":
                vip_ids.add(user_id)

            if mois == mois_courant:
                ventes_totales += montant

            if date_str.startswith(today):
                ventes_jour += montant
                if type_acces != "vip":
                    contenus_vendus += 1

        clients_vip = len(vip_ids)
        benefice_net = round(ventes_totales * 0.88, 2)

        message_final = (
            f"📊 Tes statistiques de vente :\n\n"
            f"💰 Ventes du jour : {ventes_jour}€\n"
            f"💶 Ventes totales : {ventes_totales}€\n"
            f"📦 Contenus vendus total : {contenus_vendus}\n"
            f"🌟 Clients VIP : {clients_vip}\n"
            f"📈 Bénéfice estimé net : {benefice_net}€\n\n"
            f"_Le bénéfice tient compte d’une commission de 12 %._"
        )
        vip_button = InlineKeyboardMarkup().add(
            InlineKeyboardButton("📋 Voir mes VIPs", callback_data="voir_mes_vips")
        )
        await bot.send_message(message.chat.id, message_final, parse_mode="Markdown", reply_markup=vip_button)

    except Exception as e:
        print(f"Erreur dans /stat : {e}")
        await bot.send_message(message.chat.id, "❌ Une erreur est survenue lors de la récupération des statistiques.")


# DEBUT de la fonction du proprietaire ! Ne pas toucher

@dp.message_handler(commands=["nath"])
async def handle_nath_global_stats(message: types.Message):
    if message.from_user.id != int(ADMIN_ID):
        await bot.send_message(message.chat.id, "❌ Tu n'as pas la permission d'utiliser cette commande.")
        return

    await bot.send_message(message.chat.id, "🕓 Récupération des statistiques globales en cours...")

    try:
        url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
        headers = {
            "Authorization": f"Bearer {AIRTABLE_API_KEY}"
        }

        response = requests.get(url, headers=headers)
        data = response.json()

        ventes_par_email = {}

        for record in data.get("records", []):
            fields = record.get("fields", {})
            email = fields.get("Email", "")
            montant = float(fields.get("Montant", 0))

            if not email:
                continue

            if email not in ventes_par_email:
                ventes_par_email[email] = 0
            ventes_par_email[email] += montant

        if not ventes_par_email:
            await bot.send_message(message.chat.id, "Aucune donnée trouvée dans Airtable.")
            return

        lignes = [f"📊 Récapitulatif global :\n"]

        for email, total in ventes_par_email.items():
            benefice = round(total * 0.88, 2)
            lignes.append(f"• {email} → {total:.2f} € (bénéfice : {benefice:.2f} €)")

        lignes.append("\n_Le bénéfice net tient compte d’une commission de 12 %._")

        await bot.send_message(message.chat.id, "\n".join(lignes), parse_mode="Markdown")

    except Exception as e:
        print(f"Erreur dans /nath : {e}")
        await bot.send_message(message.chat.id, "❌ Une erreur est survenue lors du traitement des statistiques.")

# FIN de la fonction du propriétaire 



# Liste des clients bannis par admin
@dp.message_handler(commands=['supp'])
async def bannir_client(message: types.Message):
    if not message.reply_to_message:
        await message.reply("❌ Utilisez cette commande en réponse au message du client à retirer.")
        return

    user_id = None
    if message.reply_to_message.forward_from:
        user_id = message.reply_to_message.forward_from.id
    else:
        user_id = pending_replies.get((message.chat.id, message.reply_to_message.message_id))

    if not user_id:
        await message.reply("❌ Impossible d’identifier le client. Réponds bien à un message transféré par le bot.")
        return

    admin_id = message.from_user.id

    if admin_id not in ban_list:
        ban_list[admin_id] = []

    if user_id not in ban_list[admin_id]:
        ban_list[admin_id].append(user_id)

        await message.reply("✅ Le client a été retiré avec succès.")
        try:
            await bot.send_message(user_id, "❌ Désolé, tu as été banni du VIP.")
        except Exception as e:
            print(f"Erreur lors de l'envoi du message au client banni : {e}")
            await message.reply("ℹ️ Le client est bien banni, mais je n’ai pas pu lui envoyer le message (permissions Telegram).")
    else:
        await message.reply("ℹ️ Ce client est déjà retiré.")


@dp.message_handler(commands=['unsupp'])
async def reintegrer_client(message: types.Message):
    if not message.reply_to_message:
        await message.reply("❌ Utilisez cette commande en réponse au message du client à réintégrer.")
        return

    user_id = None
    if message.reply_to_message.forward_from:
        user_id = message.reply_to_message.forward_from.id
    else:
        user_id = pending_replies.get((message.chat.id, message.reply_to_message.message_id))

    if not user_id:
        await message.reply("❌ Impossible d’identifier le client. Réponds bien à un message transféré par le bot.")
        return

    admin_id = message.from_user.id

    if admin_id in ban_list and user_id in ban_list[admin_id]:
        ban_list[admin_id].remove(user_id)

        await message.reply("✅ Le client a été réintégré avec succès.")
        try:
            await bot.send_message(user_id, "✅ Tu as été réadmis dans le VIP !")
        except Exception as e:
            print(f"Erreur lors de l'envoi du message au client réintégré : {e}")
            await message.reply("ℹ️ Réintégré, mais le message n’a pas pu être envoyé (permissions Telegram).")

    else:
        await message.reply("ℹ️ Ce client n’était pas retiré.")

# Mise sous forme de boutons : bannissement

@dp.message_handler(lambda message: message.text == "❌ Bannir le client" and message.reply_to_message and message.from_user.id == ADMIN_ID)
async def bouton_bannir(message: types.Message):
    forwarded = message.reply_to_message.forward_from
    if not forwarded:
        await message.reply("❌ Tu dois répondre à un message transféré du client.")
        return

    user_id = forwarded.id
    ban_list.setdefault(message.from_user.id, set()).add(user_id)
    await message.reply(f"🚫 Le client a été banni avec succès.")
    try:
        await bot.send_message(user_id, "❌ You have been removed. You can no longer contact me.")
    except Exception as e:
        print(f"Erreur d'envoi au client banni : {e}")
        await message.reply("ℹ️ Le client est banni, mais je n’ai pas pu lui envoyer le message.")


@dp.message_handler(lambda message: message.text == "✅ Réintégrer le client" and message.reply_to_message and message.from_user.id == ADMIN_ID)
async def bouton_reintegrer(message: types.Message):
    forwarded = message.reply_to_message.forward_from
    if not forwarded:
        await message.reply("❌ Tu dois répondre à un message transféré du client.")
        return

    user_id = forwarded.id
    if user_id in ban_list.get(message.from_user.id, set()):
        ban_list[message.from_user.id].remove(user_id)
        await message.reply(f"✅ Le client a été réintégré.")
        try:
            await bot.send_message(user_id, "✅ Tu as été réadmis, tu peux de nouveau m'écrire.")
        except Exception as e:
            print(f"Erreur d'envoi au client réintégré : {e}")
            await message.reply("ℹ️ Réintégré, mais je n’ai pas pu lui envoyer le message.")
    else:
        await message.reply("ℹ️ Ce client n’était pas retiré.")

# Liste des prix autorisés
prix_list = [1, 2, 3, 9, 14, 19, 24, 29, 34, 39, 44, 49, 59, 69, 79, 89, 99]

# Liste blanche des liens autorisés
WHITELIST_LINKS = [
    "https://novapulseonline.wixsite.com/",
    "https://buy.stripe.com/",
    "https://t.me/mini_jessie_bot?start=cdan"
    "https://t.me/Maevaofbot?start=cdan"
     "https://t.me/SweetAnaelleBot?start=cdan" # 22 Rajouter  le lien propre de l'admin
]

def lien_non_autorise(text):
    words = text.split()
    for word in words:
        if word.startswith("http://") or word.startswith("https://"):
            if not any(domain.strip() in word for domain in ALLOWED_DOMAINS):
                return True
    return False

@dp.message_handler(lambda message: (message.text and ("http://" in message.text or "https://" in message.text)) or (message.caption and ("http://" in message.caption or "https://" in message.caption)), content_types=types.ContentType.ANY)
async def verifier_les_liens_uniquement(message: types.Message):
    text_to_check = message.text or message.caption or ""
    if lien_non_autorise(text_to_check):
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
            await bot.send_message(chat_id=message.chat.id, text="🚫 Les liens extérieurs sont interdits.")
            
            # Message perso au CEO pour avertir des fraudeurs
            await bot.send_message(DIRECTEUR_ID,
                                   f"🚨 Tentative de lien interdit détectée !\n\n"
            f"👤 User: {message.from_user.username or message.from_user.first_name}\n"
            f"🆔 ID: {message.from_user.id}\n"
            f"🔗 Lien envoyé : {text_to_check}")

            print(f"🔴 Lien interdit supprimé : {text_to_check}")
        except Exception as e:
            print(f"Erreur lors de la suppression du lien interdit : {e}")
        raise CancelHandler()

# Fonction pour ajouter un paiement à Airtable 22 Changer l'adresse mail par celui de l'admin

def log_to_airtable(pseudo, user_id, type_acces, montant, contenu="Paiement Telegram", email=None,):
    if not type_acces:
        type_acces = "Paiement"
    if email is None:
        email= SELLER_EMAIL  # Par défaut pour éviter erreurs

    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }

    now = datetime.now()

    fields = {
        "Pseudo Telegram": pseudo or "-",
        "ID Telegram": str(user_id),
        "Type acces": str(type_acces),
        "Montant": float(montant),
        "Contenu": contenu,
        "Email": email,
        "Date": now.isoformat(),
        "Mois": now.strftime("%Y-%m")
    }

    data = {
        "fields": fields
    }

    try:
        response = requests.post(url, json=data, headers=headers)
        if response.status_code != 200:
            print(f"❌ Erreur Airtable : {response.text}")
        else:
            print("✅ Paiement ajouté dans Airtable avec succès !")
    except Exception as e:
        print(f"Erreur lors de l'envoi à Airtable : {e}")


# Création du clavier

keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(
    
    types.KeyboardButton("✨Discuter en tant que VIP"),
)
keyboard_admin = types.ReplyKeyboardMarkup(resize_keyboard=True)
keyboard_admin.add(
    types.KeyboardButton("📖 Commandes"),
    types.KeyboardButton("📊 Statistiques")
)
keyboard_admin.add(# TEST bouton admin
    types.KeyboardButton("❌ Bannir le client"),
    types.KeyboardButton("✅ Réintégrer le client")
)
keyboard_admin.add(
    types.KeyboardButton("✉️ Message à tous les VIPs")
)

keyboard.add(
    types.KeyboardButton("🔞 Voir le contenu du jour... tout en jouant 🎰")
)

# =======================
# Ajouts en haut du fichier (près des imports/vars)
# =======================
import asyncio  # si pas déjà importé
import time     # ⬅️ ajout pour le cooldown 24h
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

DICE_WAIT_SECONDS = 2.0  # laisse l’animation 🎰 se terminer avant d’envoyer la réponse
COOLDOWN_SECONDS = 24 * 3600  # ⬅️ cooldown 24h
last_played = {}  # ⬅️ user_id -> timestamp du dernier lancement
trigger_message = {}     # user_id -> (chat_id, message_id) du message "Voir le contenu du jour"

# NOTE: tu as déjà:
# - bot, dp
# - authorized_users (set)
# - ADMIN_ID (int)
# - pending_replies: Dict[(chat_id, msg_id), user_chat_id]


# =======================
# 1) Message "Voir le contenu du jour" -> propose "Lancer la roulette"
# =======================
@dp.message_handler(lambda message: message.text == "🔞 Voir le contenu du jour... tout en jouant 🎰")
async def demande_contenu_jour(message: types.Message):
    user_id = message.from_user.id

    # Non-VIP -> propose d'acheter (inchangé)
    if user_id not in authorized_users:
        bouton_vip = InlineKeyboardMarkup().add(
            InlineKeyboardButton(
                text="🔥 Rejoins le VIP pour 2 €",
                url="https://buy.stripe.com/3cIdR860JcftfUV4Dr7AI0X"
            )
        )
        await message.reply(
            "Tu veux tenter ta chance mon coeur ? 🍀\n\n"
"🚨 Mais pour jouer et essayer d'obtenir le contenu d'aujourd'hui, tu dois être un VIP.\n\n"
" Mais c'est ton jour de chance : aujourd'hui, il ne coûte que 2 € 🎁 ! Avec 2 photos nues et 1 vidéo très hard de ma chatte. 🔞\n\n"
"C'est simple : clique sur le bouton ci-dessous 👇 et tente ta chance dès maintenant\n\n"
"<i>🔐 Paiement sécurisé via Stripe</i>\n"

            "https://buy.stripe.com/3cIdR860JcftfUV4Dr7AI0X\n",
            reply_markup=bouton_vip,
            parse_mode="HTML"
        )
        return  # stop ici si ce n'est pas un VIP

    # VIP -> mémoriser le message déclencheur d’origine (pour le forward répondable côté admin)
    trigger_message[user_id] = (message.chat.id, message.message_id)

    # Au lieu d'envoyer direct, on propose la roulette
    bouton_roulette = InlineKeyboardMarkup().add(
        InlineKeyboardButton("⚡Fais tourner la roulette", callback_data="Fais tourner la roulette")
    )
    await message.reply(
        "Prépare-toi à tenter ta chance avec le contenu d'aujourd'hui... Je croise les doigts pour toi, mon chérie 🤞 \n\n"
        "Clique sur le bouton ci-dessous pour lancer la roulette 🎰",
        reply_markup=bouton_roulette
    )


# =======================
# 2) Callback "Lancer la roulette" -> roulette + attente + réponses + forward répondable
# =======================
@dp.callback_query_handler(lambda c: c.data == "Fais tourner la roulette")
async def lancer_roulette(cb: types.CallbackQuery):
    user_id = cb.from_user.id

    # ----- Cooldown 24h -----
    now = time.time()
    last = last_played.get(user_id)
    if last and (now - last) < COOLDOWN_SECONDS:
        remaining = COOLDOWN_SECONDS - (now - last)
        heures = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        await cb.answer(
            f"⚠️ Tu as déjà tourné la roue aujourd'hui ! Reviens plus tard. {heures}h{minutes:02d}.",
            show_alert=True
        )
        return
    # Marquer le lancement maintenant (évite le double-clic)
    last_played[user_id] = now

    # Lancer l’animation officielle Telegram
    dice_msg = await bot.send_dice(chat_id=user_id, emoji="🎰")

    # Attendre la fin de l’animation avant d'envoyer la réponse (crédibilité)
    await asyncio.sleep(DICE_WAIT_SECONDS)

    dice_value = dice_msg.dice.value

    # Récupérer le message déclencheur d’origine (comme ton code d’avant)
    src_info = trigger_message.get(user_id)  # (chat_id_src, msg_id_src)
    chat_id_src, msg_id_src = (src_info if src_info else (user_id, None))

    # Message côté client + notif admin (sans changer ton flow de réponse admin)
    if dice_value >= 60:  # JACKPOT => -50% (tu envoies ensuite manuellement)
        user_msg = await bot.send_message(
            chat_id=user_id,
            text="🎉 Bravo, mon chérie ! Je t'offre 50 % de réduction sur la vidéo d'aujourd'hui. 🔥\n"
                 "Je t'envoie ta vidéo dans quelques instants 💕"
        )

        await bot.send_message(
            chat_id=ADMIN_ID,
            text="📥 JACKPOT (-50%) — un VIP vient de gagner. Envoie-lui son média."
        )
    else:
        user_msg = await bot.send_message(
            chat_id=user_id,
            text="😅 Pas de chance cette fois-ci mon coeur…\n\n"
                 "Mais tu sais quoi ? Je ne vais pas te laisser les mains vides... Je offre quand même 50 %  de réduction sur ma vidéo du jour. 🔥\n"
                 "Je te l'envoie dans quelques instants💕"
        )

        await bot.send_message(
            chat_id=ADMIN_ID,
            text="📥 Raté, mais demande de contenu du jour ( -50% offert ). Envoie-lui son média."
        )

    # 👉 Forward du message déclencheur d’origine (ton ancien comportement EXACT)
    if msg_id_src is not None:
        forwarded = await bot.forward_message(
            chat_id=ADMIN_ID,
            from_chat_id=chat_id_src,
            message_id=msg_id_src
        )
        # Répondre à CE message côté admin => ça part directement chez l’utilisateur
        pending_replies[(forwarded.chat.id, forwarded.message_id)] = chat_id_src


    # Fermer le spinner du bouton inline côté client
    await cb.answer()




#fin de l'envoi du bouton du contenu du jour



from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta

@dp.message_handler(commands=["start"])
async def handle_start(message: types.Message):
    user_id = message.from_user.id
    param = (message.get_args() or "").strip()

    # === Cas A : /start=cdanXX (paiement Stripe) ===
    if param.startswith("cdan") and param[4:].isdigit():
        montant = int(param[4:])
        if montant in prix_list:
            now = datetime.now()
            paiements_valides = [
                t for t in paiements_recents.get(montant, [])
                if now - t < timedelta(minutes=3)
            ]
            if not paiements_valides:
                await bot.send_message(user_id, "❌ Paiement invalide ! Stripe a refusé votre paiement en raison d'un solde insuffisant ou d'un refus général. Veuillez vérifier vos capacités de paiement.")
                await bot.send_message(ADMIN_ID, f"⚠️ Problème ! Stripe a refusé le paiement de ton client {message.from_user.username or message.from_user.first_name}.")
                return

            # Paiement validé
            paiements_recents[montant].remove(paiements_valides[0])
            authorized_users.add(user_id)
            reset_free_quota(user_id)

            if user_id in contenus_en_attente:
                contenu = contenus_en_attente[user_id]
                if contenu["type"] == types.ContentType.PHOTO:
                    await bot.send_photo(chat_id=user_id, photo=contenu["file_id"], caption=contenu.get("caption"))
                elif contenu["type"] == types.ContentType.VIDEO:
                    await bot.send_video(chat_id=user_id, video=contenu["file_id"], caption=contenu.get("caption"))
                elif contenu["type"] == types.ContentType.DOCUMENT:
                    await bot.send_document(chat_id=user_id, document=contenu["file_id"], caption=contenu.get("caption"))
                del contenus_en_attente[user_id]
            else:
                paiements_en_attente_par_user.add(user_id)

            await bot.send_message(
                user_id,
                f"✅ Merci pour ton paiement de {montant}€ 💖 ! Voici ton contenu...\n\n"
                f"_❗️Si tu as le moindre soucis avec ta commande, contacte-nous à novapulse.online@gmail.com_",
                parse_mode="Markdown"
            )
            await bot.send_message(ADMIN_ID, f"💰 Nouveau paiement de {montant}€ de {message.from_user.username or message.from_user.first_name}.")
            log_to_airtable(
                pseudo=message.from_user.username or message.from_user.first_name,
                user_id=user_id,
                type_acces="Paiement",
                montant=float(montant),
                contenu="Paiement validé via Stripe webhook + redirection"
            )
            await bot.send_message(ADMIN_ID, "✅ Paiement enregistré dans ton Dashboard.")
            return
        else:
            await bot.send_message(user_id, "❌ Le montant indiqué n’est pas valide.")
            return

    # === Cas B : /start=vipcdan (retour après paiement VIP) ===
    if param == "vipcdan":
        authorized_users.add(user_id)
        reset_free_quota(user_id)

        await bot.send_message(
            user_id,
            "✨ Bienvenue dans le VIP mon coeur 💕! Et voici ton cadeau 🎁:"
        )

        # 2 photos VIP
        await bot.send_photo(chat_id=user_id, photo="AgACAgQAAxkBAAMqaQs6QwrJuFB153dt22R1c1lIJKoAAtYLaxug8VhQkqY3q-LYq7gBAAMCAAN4AAM2BA")
        await bot.send_photo(chat_id=user_id, photo="AgACAgQAAxkBAAMsaQs6dCgDpa7x7qSmObmLd2Cw9vMAAq4LaxvUCVlQIroWslmkpzABAAMCAAN4AAM2BA")

        # 1 vidéo VIP
        await bot.send_video(chat_id=user_id, video="BAACAgQAAxkBAAMuaQs60rPcYXyWg45ys1NRCusIny8AAmwYAALUCVlQm-qesDvLT1Y2BA")

        # Logs
        await bot.send_message(ADMIN_ID, f"🌟 Nouveau VIP : {message.from_user.username or message.from_user.first_name}.")
        log_to_airtable(
            pseudo=message.from_user.username or message.from_user.first_name,
            user_id=user_id,
            type_acces="VIP",
            montant=2.0,
            contenu="Pack 2 photos + 1 vidéo + accès VIP"
        )
        await bot.send_message(ADMIN_ID, "✅ VIP Access enregistré dans ton dashboard.")
        return  # on sort ici pour ne pas passer à l’accueil normal

    # === Cas C : /start simple (accueil normal) ===
    if user_id == ADMIN_ID:
        await bot.send_message(
            user_id,
            "👋 Bonjour admin ! Tu peux voir le listing des commandes et consulter tes statistiques !",
            reply_markup=keyboard_admin
        )
        return

    # 1) Texte d’accueil
    await bot.send_message(
        user_id,
        "🟢 Annaelle est en ligne",
        reply_markup=keyboard
    )

    # 2) Vidéo de présentation + bouton VIP
    vip_kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("💎 Deviens un VIP", url=VIP_URL)
    )
    await bot.send_video(
        chat_id=user_id,
        video=WELCOME_VIDEO_FILE_ID,
        reply_markup=vip_kb
    )

    # 3) Image floutée + offre €9
    vip_offer_kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("💎 Accès immédiat pour 2 €", url=VIP_URL)
    )
    await bot.send_photo(
        chat_id=user_id,
        photo=DEFAULT_FLOU_IMAGE_FILE_ID,
        caption="🔥 Offre spéciale valable uniquement aujourd'hui !\n - 2 nudes 🔞\n - 1 vidéo hard où je mouille 💦\n- Accès VIP à vie ⚡\n Pour seulement 2 € \n👉 Cliquez ci-dessous pour y accéder immédiatement !",
        reply_markup=vip_offer_kb
    )



 # TEST
@dp.message_handler(lambda message: message.text == "❗ Problème d'achat")
async def probleme_achat(message: types.Message):
    texte_client = (
        "❗ *Un problème avec ton achat ?*\n\n"
        "Pas de panique ! Je traite chaque cas avec le plus grand sérieux. "
        "Tu peux m'écrire à *novapulse.online@gmail.com* avec ton nom de telegram, "
        "et je vais traiter ta demande maintenant !\n\n"
        "_Je m'en charge._"
    )
    await bot.send_message(message.chat.id, texte_client, parse_mode="Markdown")

    pseudo = message.from_user.username or message.from_user.first_name or "Inconnu"
    user_id = message.from_user.id

    # 🔔 Alerte pour le vendeur (admin)
    await bot.send_message(ADMIN_ID,
        f"⚠️ *ALERTE LITIGE CLIENT* :\n\n"
        f"Le client {pseudo} (ID: {user_id}) a cliqué sur *'Problème achat'*.\n"
        f"Pense à vérifier si tout est OK.",
        parse_mode="Markdown"
    )

    # 🔔 Alerte pour le directeur
    await bot.send_message(DIRECTEUR_ID,
        f"🔔 *Problème achat détecté*\n\n"
        f"👤 Client : {pseudo} (ID: {user_id})\n"
        f"👨‍💼 Admin concerné : {ADMIN_ID}",
        parse_mode="Markdown"
    )

    print(f"✅ Alertes envoyées à ADMIN_ID ({ADMIN_ID}) et DIRECTEUR_ID ({DIRECTEUR_ID})")

# TEST FIN


    # Envoi à l'admin (vendeur)
    try:
        await bot.send_message(ADMIN_ID, texte_alerte_admin, parse_mode="Markdown")
    except Exception as e:
        print(f"Erreur envoi admin : {e}")

    # Envoi au directeur (toi)
    try:
        await bot.send_message(DIRECTEUR_ID, texte_alerte_directeur, parse_mode="Markdown")
    except Exception as e:
        print(f"Erreur envoi directeur : {e}")


# Message avec lien

import re

@dp.message_handler(
    lambda message: message.from_user.id == ADMIN_ID and (
        (message.text and "/env" in message.text.lower()) or 
        (message.caption and "/env" in message.caption.lower())
    ),
    content_types=[types.ContentType.TEXT, types.ContentType.PHOTO, types.ContentType.VIDEO, types.ContentType.DOCUMENT]
)
async def envoyer_contenu_payant(message: types.Message):
    if not message.reply_to_message:
        await bot.send_message(chat_id=ADMIN_ID, text="❗ Utilise cette commande en réponse à un message du client.")
        return

    user_id = None
    if message.reply_to_message.forward_from:
        user_id = message.reply_to_message.forward_from.id
    else:
        user_id = pending_replies.get((message.chat.id, message.reply_to_message.message_id))

    if not user_id:
        await bot.send_message(chat_id=ADMIN_ID, text="❗ Impossible d'identifier le destinataire.")
        return
    
# 22 Mettre les liens propres à l'admin
    liens_paiement = {
        "1": "https://buy.stripe.com/cNiaEWbl3a7l9wx3zn7AI0r",
        "2": "https://buy.stripe.com/3cIdR860JcftfUV4Dr7AI0X",
        "9": "https://buy.stripe.com/00wdR83SB4N12457PD7AI0H",
        "14": "https://buy.stripe.com/7sY5kC60JenB5ghee17AI0I",
        "19": "https://buy.stripe.com/9B6fZgdtb2ETaAB0nb7AI0J",
        "24": "https://buy.stripe.com/aFafZgexf2ET9wx0nb7AI0K",
        "29": "https://buy.stripe.com/00w8wO1Kt5R53895Hv7AI0",
        "34": "https://buy.stripe.com/00w00i3SBdjxfUVb1P7AI0M",
        "39": "https://buy.stripe.com/aFabJ074N0wLaAB9XL7AI0N",
        "49": "https://buy.stripe.com/9B6cN4agZenBcIJc5T7AI0O",
        "59": "https://buy.stripe.com/9B66oG0GpenBeQR4Dr7AI0P",
        "69": "https://buy.stripe.com/14A6oG0GpdjxcIJ2vj7AI0Q",
        "79": "https://buy.stripe.com/eVqeVcfBj0wL389ee17AI0R",
        "89": "https://buy.stripe.com/bJebJ09cV4N12452vj7AI0S",
        "99": "https://buy.stripe.com/00w3cu2Ox2ET4cd8TH7AI0T",

        
    }

    texte = message.caption or message.text or ""
    match = re.search(r"/env(\d+|vip)", texte.lower())
    if not match:
        await bot.send_message(chat_id=ADMIN_ID, text="❗ Aucun code /envXX valide détecté.")
        return

    code = match.group(1)
    lien = liens_paiement.get(code)
    if not lien:
        await bot.send_message(chat_id=ADMIN_ID, text="❗ Ce montant n'est pas reconnu dans les liens disponibles.")
        return

    nouvelle_legende = re.sub(r"/env(\d+|vip)", lien, texte)

    if message.photo or message.video or message.document:
        if message.photo:
            file_id = message.photo[-1].file_id
            content_type = types.ContentType.PHOTO
        elif message.video:
            file_id = message.video.file_id
            content_type = types.ContentType.VIDEO
        else:
            file_id = message.document.file_id
            content_type = types.ContentType.DOCUMENT

        contenus_en_attente[user_id] = {
            "file_id": file_id,
            "type": content_type,
            "caption": re.sub(r"/env(\d+|vip)", "", texte, flags=re.IGNORECASE).strip()
        }

        await bot.send_message(chat_id=ADMIN_ID, text=f"✅ Contenu prêt pour l'utilisateur {user_id}.")

        if user_id in paiements_en_attente_par_user:
            contenu = contenus_en_attente[user_id]
            if contenu["type"] == types.ContentType.PHOTO:
                await bot.send_photo(chat_id=user_id, photo=contenu["file_id"], caption=contenu.get("caption"))
            elif contenu["type"] == types.ContentType.VIDEO:
                await bot.send_video(chat_id=user_id, video=contenu["file_id"], caption=contenu.get("caption"))
            elif contenu["type"] == types.ContentType.DOCUMENT:
                await bot.send_document(chat_id=user_id, document=contenu["file_id"], caption=contenu.get("caption"))
            paiements_en_attente_par_user.discard(user_id)
            contenus_en_attente.pop(user_id, None)
            return

    await bot.send_photo(chat_id=user_id, photo=DEFAULT_FLOU_IMAGE_FILE_ID, caption=nouvelle_legende)
    await bot.send_message(
        chat_id=user_id,
        text=f"_🔒 Ce contenu {code} € est verrouillé. Clique sur le lien ci-dessus pour le déverrouiller._",
        parse_mode="Markdown"
    )   

# TEST VF debut
@dp.message_handler(lambda message: message.text == "📖 Commandes" and message.from_user.id == ADMIN_ID)
async def show_commandes_admin(message: types.Message):
    commandes = (
        "📖 *Liste des commandes disponibles :*\n\n"
        "🔒 */envxx* – Envoyer un contenu payant €\n"
        "_Tape cette commande avec le bon montant (ex. /env14) pour envoyer un contenu flouté avec lien de paiement de 14 €. Ton client recevra directement une image floutée avec le lien de paiement._\n\n"
        "⚠️ ** – N'oublies pas de sélectionner le message du client à qui tu veux répondre\n\n"
        "⚠️ ** – Voici la liste des prix : 9, 14, 19, 24, 29, 34, 39, 44, 49, 59, 69, 79, 89, 99\n\n"
        "📬 *Besoin d’aide ?* Écris-moi par mail : novapulse.online@gmail.com"
    )

    # Création du bouton inline "Mise à jour"
    inline_keyboard = InlineKeyboardMarkup()
    inline_keyboard.add(InlineKeyboardButton("🛠️ Mise à jour", callback_data="maj_bot"))

    await message.reply(commandes, parse_mode="Markdown", reply_markup=inline_keyboard)


# Callback quand on clique sur le bouton inline
@dp.callback_query_handler(lambda call: call.data == "maj_bot")
async def handle_maj_bot(call: types.CallbackQuery):
    await bot.answer_callback_query(call.id)
    await bot.send_message(call.message.chat.id, "🔄 Clique pour lancer la MAJ ➡️ : /start")

@dp.message_handler(lambda message: message.text == "📊 Statistiques" and message.from_user.id == ADMIN_ID)
async def show_stats_direct(message: types.Message):
    await handle_stat(message)

# test du résume du dernier message recu 


import asyncio
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

annotations = {}   # {user_id: "texte note"}
assignations = {}  # {user_id: "nom admin en charge"}

@dp.message_handler(lambda message: message.chat.id not in authorized_admin_ids)
async def handle_admin_message(message: types.Message):
    user_id = message.from_user.id

    def escape_html(text):
        if not text:
            return "[Message vide]"
        return (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
        )

    new_msg = escape_html(message.text)
    old_msg = escape_html(last_messages.get(user_id, "Aucun message"))
    note_admin = annotations.get(user_id, "Aucune note")
    admin_en_charge = assignations.get(user_id, "Aucun")

    last_messages[user_id] = message.text or "[Message vide]"

    await bot.forward_message(ADMIN_ID, user_id, message.message_id)

    # Boutons Annoter et Prendre en charge
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Prendre en charge", callback_data=f"prendre_{user_id}"),
        InlineKeyboardButton("📝 Annoter", callback_data=f"annoter_{user_id}")
    )

    response = (
        "╭───── 🧠 RÉSUMÉ RAPIDE ─────\n"
        f"📌 Ancien : {old_msg}\n"
        f"➡️ Nouveau : {new_msg}\n"
        f"👤 Admin en charge : {admin_en_charge}\n"
        f"📒 Notes :\n{note_admin}\n"
        "╰──────────────────────────\n"
        "<i>Ce message sera supprimé automatiquement dans moins de 10 secondes.</i>"
    )

    sent_msg = await bot.send_message(ADMIN_ID, response, parse_mode="HTML", reply_markup=keyboard)

    await asyncio.sleep(10)
    try:
        await bot.delete_message(chat_id=ADMIN_ID, message_id=sent_msg.message_id)
    except Exception as e:
        print(f"❌ Erreur suppression message : {e}")


# Handler bouton Prendre en charge
@dp.callback_query_handler(lambda c: c.data.startswith("prendre_"))
async def prendre_en_charge(call: types.CallbackQuery):
    user_id = int(call.data.split("_")[1])
    nom_admin = call.from_user.first_name or f"Admin {call.from_user.id}"
    
    assignations[user_id] = nom_admin
    await call.message.answer(f"✅ {nom_admin} est maintenant en charge du client {user_id}.")

    # Supprimer confirmation après 10s
    await asyncio.sleep(10)
    try:
        await bot.delete_message(chat_id=ADMIN_ID, message_id=call.message.message_id + 1)
    except:
        pass


# Handler bouton Annoter
@dp.callback_query_handler(lambda c: c.data.startswith("annoter_"))
async def annoter_client(call: types.CallbackQuery):
    user_id = int(call.data.split("_")[1])
    await call.message.answer(f"✍️ Écris la note pour ce client (ID: {user_id}).")
    
    admin_modes["annoter"] = user_id


# Handler pour réception de la note
@dp.message_handler(lambda message: ADMIN_ID == message.from_user.id and admin_modes.get("annoter"))
async def enregistrer_annotation(message: types.Message):
    user_id_cible = admin_modes.pop("annoter")
    
    ancienne_note = annotations.get(user_id_cible, "")
    nouvelle_note = message.text.strip()
    
    nouvelle_ligne = f"- {nouvelle_note}"

    if ancienne_note != "Aucune note" and ancienne_note:
        annotations[user_id_cible] = ancienne_note + "\n" + nouvelle_ligne
    else:
        annotations[user_id_cible] = nouvelle_ligne

    confirmation_msg = await message.answer(
        f"✅ Note ajoutée pour le client {user_id_cible}.\n📒 Notes actuelles :\n{annotations[user_id_cible]}"
    )

    await asyncio.sleep(10)
    try:
        await bot.delete_message(chat_id=ADMIN_ID, message_id=confirmation_msg.message_id)
    except Exception as e:
        print(f"❌ Erreur suppression confirmation : {e}")





# fin du resume du dernier message recu 

# ======================== IMPORTS & VARIABLES ========================

# ========== IMPORTS ESSENTIELS ==========
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ========== HANDLER CLIENT : transfert vers admin ==========

from ban_storage import ban_list  # à ajouter tout en haut si pas déjà fait

@dp.message_handler(lambda message: message.from_user.id != ADMIN_ID, content_types=types.ContentType.ANY)
async def relay_from_client(message: types.Message):
    user_id = message.from_user.id

    # 🔒 Vérifier si le client est banni par un admin
    for admin_id, clients_bannis in ban_list.items():
        if user_id in clients_bannis:
            try:
                await message.delete()
            except:
                pass
            try:
                await bot.send_message(user_id, "🚫 Tu as été banni, tu ne peux plus m'envoyer de message.")
            except:
                pass
            return  # ⛔ STOP : on n'envoie rien à l'admin

    # ✅ Si pas banni → transfert normal
    try:
        sent_msg = await bot.forward_message(chat_id=ADMIN_ID, from_chat_id=message.chat.id, message_id=message.message_id)
        pending_replies[(sent_msg.chat.id, sent_msg.message_id)] = message.chat.id
        print(f"✅ Message reçu de {message.chat.id} et transféré à l'admin")
    except Exception as e:
        print(f"❌ Erreur transfert message client : {e}")



# ========== HANDLER ADMIN : réponses privées + messages groupés ==========

@dp.message_handler(lambda message: message.from_user.id == ADMIN_ID, content_types=types.ContentType.ANY)
async def handle_admin_message(message: types.Message):
    mode = admin_modes.get(ADMIN_ID)

    # ✅ Si l'admin clique sur "Message à tous les VIPs"
    if message.text == "✉️ Message à tous les VIPs":
        admin_modes[ADMIN_ID] = "en_attente_message"
        await bot.send_message(chat_id=ADMIN_ID, text="✍️ Quel message veux-tu envoyer à tous les VIPs ?")
        return

    # ✅ Si l'admin est en mode groupé, on traite le contenu du message
    if mode == "en_attente_message":
        admin_modes[ADMIN_ID] = None
        await traiter_message_groupé(message)
        return

    # ✅ Sinon, on attend un reply pour une réponse privée
    if not message.reply_to_message:
        print("❌ Pas de reply détecté (et pas en mode groupé)")
        return

    # 🔍 Identification du destinataire
    user_id = None
    if message.reply_to_message.forward_from:
        user_id = message.reply_to_message.forward_from.id
    else:
        user_id = pending_replies.get((message.chat.id, message.reply_to_message.message_id))

    if not user_id:
        await bot.send_message(chat_id=ADMIN_ID, text="❗Impossible d'identifier le destinataire.")
        return

    # ✅ Envoi de la réponse
    try:
        if message.text:
            await bot.send_message(chat_id=user_id, text=message.text)
        elif message.photo:
            await bot.send_photo(chat_id=user_id, photo=message.photo[-1].file_id, caption=message.caption or "")
        elif message.video:
            await bot.send_video(chat_id=user_id, video=message.video.file_id, caption=message.caption or "")
        elif message.document:
            await bot.send_document(chat_id=user_id, document=message.document.file_id, caption=message.caption or "")
        elif message.voice:
            await bot.send_voice(chat_id=user_id, voice=message.voice.file_id)
        elif message.audio:
            await bot.send_audio(chat_id=user_id, audio=message.audio.file_id, caption=message.caption or "")
        else:
            await bot.send_message(chat_id=ADMIN_ID, text="📂 Type de message non supporté.")
    except Exception as e:
        await bot.send_message(chat_id=ADMIN_ID, text=f"❗Erreur admin -> client : {e}")

# ========== TRAITEMENT MESSAGE GROUPÉ VIPs ==========

async def traiter_message_groupé(message: types.Message):
    if message.text:
        pending_mass_message[ADMIN_ID] = {"type": "text", "content": message.text}
        preview = message.text
    elif message.photo:
        pending_mass_message[ADMIN_ID] = {"type": "photo", "content": message.photo[-1].file_id, "caption": message.caption or ""}
        preview = f"[Photo] {message.caption or ''}"
    elif message.video:
        pending_mass_message[ADMIN_ID] = {"type": "video", "content": message.video.file_id, "caption": message.caption or ""}
        preview = f"[Vidéo] {message.caption or ''}"
    elif message.audio:
        pending_mass_message[ADMIN_ID] = {"type": "audio", "content": message.audio.file_id, "caption": message.caption or ""}
        preview = f"[Audio] {message.caption or ''}"
    elif message.voice:
        pending_mass_message[ADMIN_ID] = {"type": "voice", "content": message.voice.file_id}
        preview = "[Note vocale]"
    else:
        await message.reply("❌ Message non supporté.")
        return

    confirmation = InlineKeyboardMarkup(row_width=2)
    confirmation.add(
        InlineKeyboardButton("✅ Confirmer l’envoi", callback_data="confirmer_envoi_groupé"),
        InlineKeyboardButton("❌ Annuler l’envoi", callback_data="annuler_envoi_groupé")
    )

    await message.reply(f"Prévisualisation :\n\n{preview}", reply_markup=confirmation)

# ========== CALLBACKS ENVOI / ANNULATION GROUPÉ ==========

@dp.callback_query_handler(lambda call: call.data == "confirmer_envoi_groupé")
async def confirmer_envoi_groupé(call: types.CallbackQuery):
    await call.answer()
    message_data = pending_mass_message.get(ADMIN_ID)
    if not message_data:
        await call.message.edit_text("❌ Aucun message en attente à envoyer.")
        return

    await call.message.edit_text("⏳ Envoi du message à tous les VIPs...")
    envoyes = 0
    erreurs = 0

    for vip_id in authorized_users:
        try:
            if message_data["type"] == "text":
                await bot.send_message(chat_id=int(vip_id), text=message_data["content"])
            elif message_data["type"] == "photo":
                await bot.send_photo(chat_id=int(vip_id), photo=message_data["content"], caption=message_data.get("caption", ""))
            elif message_data["type"] == "video":
                await bot.send_video(chat_id=int(vip_id), video=message_data["content"], caption=message_data.get("caption", ""))
            elif message_data["type"] == "audio":
                await bot.send_audio(chat_id=int(vip_id), audio=message_data["content"], caption=message_data.get("caption", ""))
            elif message_data["type"] == "voice":
                await bot.send_voice(chat_id=int(vip_id), voice=message_data["content"])
            envoyes += 1
        except Exception as e:
            print(f"❌ Erreur envoi à {vip_id} : {e}")
            erreurs += 1

    await bot.send_message(chat_id=ADMIN_ID, text=f"✅ Envoyé à {envoyes} VIP(s).\n⚠️ Échecs : {erreurs}")
    pending_mass_message.pop(ADMIN_ID, None)

@dp.callback_query_handler(lambda call: call.data == "annuler_envoi_groupé")
async def annuler_envoi_groupé(call: types.CallbackQuery):
    await call.answer("❌ Envoi annulé.")
    pending_mass_message.pop(ADMIN_ID, None)
    await call.message.edit_text("❌ Envoi annulé.")

#debut du 19 juillet 2025 mettre le tableau de vips
@dp.callback_query_handler(lambda c: c.data == "voir_mes_vips")
async def voir_mes_vips(callback_query: types.CallbackQuery):
    telegram_id = callback_query.from_user.id
    email = ADMIN_EMAILS.get(telegram_id)

    if not email:
        await bot.send_message(telegram_id, "❌ Ton e-mail admin n’est pas reconnu.")
        return

    await callback_query.answer("Chargement de tes VIPs...")

    headers = {
        "Authorization": f"Bearer {os.getenv('AIRTABLE_API_KEY')}"
    }

    url = "https://api.airtable.com/v0/appdA5tvdjXiktFzq/tblwdps52XKMk43xo"
    params = {
        "filterByFormula": f"{{Email}} = '{email}'"
    }

    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        await bot.send_message(telegram_id, f"❌ Erreur Airtable : {response.status_code}\n\n{response.text}")
        return

    records = response.json().get("records", [])
    if not records:
        await bot.send_message(telegram_id, "📭 Aucun enregistrement trouvé pour toi.")
        return

    # Étape 1 : repérer les pseudos ayant AU MOINS une ligne Type acces = VIP
    pseudos_vip = set()
    for r in records:
        f = r.get("fields", {})
        pseudo = f.get("Pseudo Telegram", "").strip()
        type_acces = f.get("Type acces", "").strip().lower()
        if pseudo and type_acces == "vip":
            pseudos_vip.add(pseudo)

    # Étape 2 : additionner TOUS les montants (Paiement + VIP) de ces pseudos uniquement
    montants_par_pseudo = {}
    for r in records:
        f = r.get("fields", {})
        pseudo = f.get("Pseudo Telegram", "").strip()
        montant = f.get("Montant")

        if not pseudo or pseudo not in pseudos_vip:
            continue

        try:
            montant_float = float(montant)
        except:
            montant_float = 0.0

        if pseudo not in montants_par_pseudo:
            montants_par_pseudo[pseudo] = 0.0

        montants_par_pseudo[pseudo] += montant_float

    try:
        # Construction du message final avec tri et top 3
        message = "📋 Voici tes clients VIP (avec tous leurs paiements) :\n\n"
        sorted_vips = sorted(montants_par_pseudo.items(), key=lambda x: x[1], reverse=True)

        for pseudo, total in sorted_vips:
            message += f"👤 @{pseudo} — {round(total)} €\n"

        # 🏆 Top 3
        top3 = sorted_vips[:3]
        if top3:
            message += "\n🏆 *Top 3 clients :*\n"
            for i, (pseudo, total) in enumerate(top3):
                place = ["🥇", "🥈", "🥉"]
                emoji = place[i] if i < len(place) else f"#{i+1}"
                message += f"{emoji} @{pseudo} — {round(total)} €\n"

        await bot.send_message(telegram_id, message)

    except Exception as e:
        import traceback
        error_text = traceback.format_exc()
        print("❌ ERREUR DANS VIPS + TOP 3 :\n", error_text)
        await bot.send_message(telegram_id, "❌ Une erreur est survenue lors de l'affichage des VIPs.")

#fin du 19 juillet 2025 mettre le tableau de vips
