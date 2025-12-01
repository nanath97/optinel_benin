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
from middlewares.payment_filter import PaymentFilterMiddleware
from vip_topics import is_vip, get_user_id_by_topic_id, get_panel_message_id_by_user, update_vip_info, _user_topics


dp.middleware.setup(PaymentFilterMiddleware(authorized_users))


# map (chat_id, message_id) -> chat_id du client
pending_replies = {}


pending_notes = {}  # admin_id -> user_id

# Dictionnaire temporaire pour stocker les derniers messages de chaque client
last_messages = {}
# ADMIN / OWNER / ADMINS
ADMIN_ID = 7973689658  # propriétaire historique (conserve pour compatibilité)
OWNER_ID = ADMIN_ID
# ensemble des admins autorisés (modifie/add si besoin)
authorized_admin_ids = {7973689658, 6545079601}


def is_admin(user_id: int) -> bool:
    return user_id in authorized_admin_ids or user_id == OWNER_ID

# Constantes pour le bouton VIP et la vidéo de bienvenue (défaut)
VIP_URL = "https://buy.stripe.com/3cIdR860JcftfUV4Dr7AI0X"
WELCOME_VIDEO_FILE_ID = "BAACAgQAAxkBAAMlaQs2G6IJCml5_CaJz70fbfjbsmMAAmoYAALUCVlQOuaVvRH37Ag2BA"



pending_mass_message = {}
admin_modes = {}  # Clé = admin_id, Valeur = "en_attente_message"

# Mapping entre ID Telegram des admins et leur email dans Airtable 19juillet 2025 debut
ADMIN_EMAILS = {
    7973689658: "yehooptinel6@gmail.com",
}
# Mapping entre ID Telegram des admins et leur email dans Airtable 19juillet 2025 fin


# Paiements validés par Stripe, stockés temporairement
paiements_recents = defaultdict(list)  # ex : {14: [datetime1, datetime2]}

# ====== LIENS PAIEMENT GLOBALS (utilisés pour /env et pour l'envoi groupé payant) ======
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
DIRECTEUR_ID = 7973689658  # ID personnel au ceo pour avertir des fraudeurs

# === MEDIA EN ATTENTE ===
contenus_en_attente = {}  # { user_id: {"file_id": ..., "type": ..., "caption": ...} }
paiements_en_attente_par_user = set()  # Set de user_id qui ont payé
# === FIN MEDIA EN ATTENTE ===

# === 221097 DEBUT

def initialize_authorized_users():
    try:
        url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
        params = {"filterByFormula": "{Type acces}='VIP'"}
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
        print(f"[INFO] {len(authorized_users)} utilisateurs VIP chargés depuis Airtable.")
    except Exception as e:
        print(f"[ERROR] Impossible de charger les VIP depuis Airtable : {e}")
# === 221097 FIN

# === Statistiques ===

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

@dp.message_handler(commands=["stat"])
async def handle_stat(message: types.Message):
    admin_id = message.from_user.id
    email = ADMIN_EMAILS.get(admin_id)

    # Sécurité : on ne calcule des stats que pour un admin connu
    if not email:
        await bot.send_message(
            message.chat.id,
            "❌ Ton e-mail admin n’est pas configuré dans le bot. Parle à Nova Pulse pour le mettre à jour."
        )
        return

    await bot.send_message(message.chat.id, "📥 Traitement de tes statistiques de vente en cours...")

    try:
        url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
        headers = {
            "Authorization": f"Bearer {AIRTABLE_API_KEY}"
        }

        # 🔑 On filtre uniquement les lignes qui appartiennent à CET admin
        params = {
            "filterByFormula": f"{{Email}} = '{email}'"
        }

        response = requests.get(url, headers=headers, params=params)
        data = response.json()

        ventes_totales = 0.0
        ventes_jour = 0.0
        contenus_vendus = 0
        vip_ids = set()

        today = datetime.now().date().isoformat()
        mois_courant = datetime.now().strftime("%Y-%m")

        for record in data.get("records", []):
            fields = record.get("fields", {})

            user_id = fields.get("ID Telegram", "")
            type_acces = (fields.get("Type acces", "") or "").lower()
            date_str = fields.get("Date", "") or ""
            mois = fields.get("Mois", "") or ""

            try:
                montant = float(fields.get("Montant", 0) or 0)
            except Exception:
                montant = 0.0

            # 💶 Ventes du mois (on ignore les lignes VIP “0 €”)
            if mois == mois_courant and montant > 0 and type_acces != "vip":
                ventes_totales += montant

            # 📅 Ventes du jour + contenus vendus
            if date_str.startswith(today) and montant > 0 and type_acces != "vip":
                ventes_jour += montant
                contenus_vendus += 1

            # 🌟 Clients VIP = clients qui ont payé au moins une fois
            # (Type acces = "paiement" OU "vip") ET montant > 0
            if user_id and montant > 0 and type_acces in ("paiement", "vip"):
                vip_ids.add(user_id)

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
        await bot.send_message(message.chat.id, "❌ Timal, tu n'as pas la permission d'utiliser ce bouton.")
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

        lignes = ["📊 *Récapitulatif global des ventes :*\n"]
        total_global = 0

        for email, total in ventes_par_email.items():
            benefice_vendeur = round(total * 0.88, 2)
            benefice_nath = round(total * 0.12, 2)
            total_global += total
            lignes.append(
                f"• {email} → {total:.2f} €  |  Vendeur : {benefice_vendeur:.2f} €  |  Toi (12 %) : {benefice_nath:.2f} €"
            )

        total_benefice_nath = round(total_global * 0.12, 2)
        total_benefice_vendeurs = round(total_global * 0.88, 2)

        lignes.append("\n💰 *Synthèse globale :*")
        lignes.append(f"• Total des ventes : {total_global:.2f} €")
        lignes.append(f"• Tes bénéfices (12 %) : {total_benefice_nath:.2f} €")
        lignes.append(f"• Bénéfices vendeurs (88 %) : {total_benefice_vendeurs:.2f} €")

        await bot.send_message(message.chat.id, "\n".join(lignes), parse_mode="Markdown")

    except Exception as e:
        print(f"Erreur dans /nath : {e}")
        await bot.send_message(message.chat.id, "❌ Une erreur est survenue lors du traitement des statistiques.")

# FIN de la fonction du propriétaire


# Liste des prix autorisés
prix_list = [1, 3, 9, 14, 19, 24, 29, 34, 39, 44, 49, 59, 69, 79, 89, 99]

# Liste blanche des liens autorisés
WHITELIST_LINKS = [
    "https://novapulseonline.wixsite.com/",
    "https://buy.stripe.com/",
    "https://t.me/mini_jessie_bot?start=cdan"
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

def log_to_airtable(
    pseudo,
    user_id,
    type_acces,
    montant,
    contenu="Paiement Telegram",
    email="yehooptinel6@gmail.com",
):
    if not type_acces:
        type_acces = "Paiement"  # Par défaut pour éviter erreurs

    url_base = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }

    now = datetime.now()

    # Champs communs qu'on veut toujours écrire / mettre à jour
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

    try:
        # 🔹 Cas particulier : accès VIP
        if str(type_acces).lower() == "vip":
            # On cherche la/les lignes VIP existantes pour ce user
            params = {
                "filterByFormula": f"AND({{ID Telegram}} = '{user_id}', {{Type acces}} = 'VIP')"
            }
            r = requests.get(url_base, headers=headers, params=params)
            r.raise_for_status()
            records = r.json().get("records", [])

            if records:
                # On choisit de préférence une ligne qui a déjà un Topic ID
                rec_to_update = records[0]
                for rec in records:
                    if rec.get("fields", {}).get("Topic ID"):
                        rec_to_update = rec
                        break

                rec_id = rec_to_update["id"]
                patch_url = f"{url_base}/{rec_id}"

                # ⚠️ Important : on n'envoie PAS "Topic ID" ici → Airtable le conserve tel quel
                data = {"fields": fields}
                response = requests.patch(patch_url, json=data, headers=headers)
            else:
                # Sécurité : si aucune ligne VIP n'existe (cas improbable),
                # on crée une nouvelle ligne comme avant
                data = {"fields": fields}
                response = requests.post(url_base, json=data, headers=headers)

        # 🔹 Tous les autres types d'accès (Paiement simple, groupé, etc.)
        else:
            data = {"fields": fields}
            response = requests.post(url_base, json=data, headers=headers)

        if response.status_code != 200:
            print(f"❌ Erreur Airtable : {response.text}")
        else:
            print("✅ Paiement ajouté dans Airtable avec succès !")

    except Exception as e:
        print(f"Erreur lors de l'envoi à Airtable : {e}")



# Création du clavier

keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(
)
keyboard_admin = types.ReplyKeyboardMarkup(resize_keyboard=True)
keyboard_admin.add(
    types.KeyboardButton("📖 Commandes"),
    types.KeyboardButton("📊 Statistiques")
)

keyboard_admin.add(
    types.KeyboardButton("✉️ Message à tous les VIPs")
)

from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta

@dp.message_handler(commands=["start"])
async def handle_start(message: types.Message):
    user_id = message.from_user.id
    param = (message.get_args() or "").strip()

    # === Cas A : /start=cdanXX (paiement Stripe pour un contenu) ===
    if param.startswith("cdan") and param[4:].isdigit():
        montant = int(param[4:])
        if montant in prix_list:
            now = datetime.now()
            paiements_valides = [
                t for t in paiements_recents.get(montant, [])
                if now - t < timedelta(minutes=3)
            ]
            if not paiements_valides:
                await bot.send_message(
                    user_id,
                    "❌ Paiement invalide ! Stripe a refusé votre paiement en raison d'un solde insuffisant ou d'un refus général. Veuillez vérifier vos capacités de paiement."
                )
                # avertir tous les admins
                for adm in authorized_admin_ids:
                    try:
                        await bot.send_message(
                            adm,
                            f"⚠️ Problème ! Stripe a refusé le paiement de ton client {message.from_user.username or message.from_user.first_name}."
                        )
                    except Exception:
                        pass
                return

            # Paiement validé
            paiements_recents[montant].remove(paiements_valides[0])
            authorized_users.add(user_id)

            # Si un contenu était en attente → on le livre
            if user_id in contenus_en_attente:
                contenu = contenus_en_attente[user_id]
                if contenu["type"] == types.ContentType.PHOTO:
                    await bot.send_photo(
                        chat_id=user_id,
                        photo=contenu["file_id"],
                        caption=contenu.get("caption")
                    )
                elif contenu["type"] == types.ContentType.VIDEO:
                    await bot.send_video(
                        chat_id=user_id,
                        video=contenu["file_id"],
                        caption=contenu.get("caption")
                    )
                elif contenu["type"] == types.ContentType.DOCUMENT:
                    await bot.send_document(
                        chat_id=user_id,
                        document=contenu["file_id"],
                        caption=contenu.get("caption")
                    )
                del contenus_en_attente[user_id]
            else:
                # Le client a payé avant que tu aies /envXX → on note le paiement en attente
                paiements_en_attente_par_user.add(user_id)

            await bot.send_message(
                user_id,
                f"✅ Merci pour ton paiement de {montant}€ 💖 ! Voici ton contenu...\n\n"
                f"_❗️Si tu as le moindre soucis avec ta commande, contacte-nous à novapulse.online@gmail.com_",
                parse_mode="Markdown"
            )
            # avertir tous les admins
            for adm in authorized_admin_ids:
                try:
                    await bot.send_message(
                        adm,
                        f"💰 Nouveau paiement de {montant}€ de {message.from_user.username or message.from_user.first_name}."
                    )
                except Exception:
                    pass
            log_to_airtable(
                pseudo=message.from_user.username or message.from_user.first_name,
                user_id=user_id,
                type_acces="Paiement",
                montant=float(montant),
                contenu="Paiement validé via Stripe webhook + redirection"
            )
            try:
                from vip_topics import ensure_topic_for_vip
                topic_id = await ensure_topic_for_vip(message.from_user)
            except Exception:
                topic_id = None
            if topic_id is not None:
                try:
                    await bot.request(
                        "sendMessage",
                        {
                            "chat_id": int(os.getenv("STAFF_GROUP_ID", "0")),
                            "message_thread_id": topic_id,
                            "text": (
                                f"💰 *Nouveau paiement contenu*\n\n"
                                f"👤 Client : @{message.from_user.username or message.from_user.first_name}\n"
                                f"💶 Montant : {montant} €\n"
                                f"📊 Paiement enregistré dans Airtable."
                            ),
                            "parse_mode": "Markdown"
                        }
                    )
                except Exception as e:
                    print(f"[VIP_TOPICS] Erreur envoi notif paiement contenu dans topic {topic_id} : {e}")

            return

        # 🔔 Notification dans le TOPIC du client (et plus dans le bot)
                 


        # === Cas B : /start=vipcdan (retour après paiement VIP) ===
    if param == "vipcdan":
        # 1) On marque le user comme VIP côté bot
        authorized_users.add(user_id)

        # 2) On crée / récupère le topic VIP pour ce client
        try:
            from vip_topics import ensure_topic_for_vip
            topic_id = await ensure_topic_for_vip(message.from_user)
        except Exception as e:
            # On log mais ON NE BLOQUE PAS l'envoi des médias
            print(f"[VIP] Erreur ensure_topic_for_vip pour {user_id}: {e}")
            topic_id = None  # pour éviter un NameError plus loin

        # 3) On envoie le pack VIP (2 photos + 1 vidéo)
        await bot.send_message(
            user_id,
            "✨ Bienvenue dans le VIP mon coeur 💕! Et voici ton cadeau 🎁:"
        )

        # 2 photos VIP
        await bot.send_photo(
            chat_id=user_id,
            photo="AgACAgQAAxkBAAMqaQs6QwrJuFB153dt22R1c1lIJKoAAtYLaxug8VhQkqY3q-LYq7gBAAMCAAN4AAM2BA"
        )
        await bot.send_photo(
            chat_id=user_id,
            photo="AgACAgQAAxkBAAMsaQs6dCgDpa7x7qSmObmLd2Cw9vMAAq4LaxvUCVlQIroWslmkpzABAAMCAAN4AAM2BA"
        )

        # 1 vidéo VIP
        await bot.send_video(
            chat_id=user_id,
            video="BAACAgQAAxkBAAMuaQs60rPcYXyWg45ys1NRCusIny8AAmwYAALUCVlQm-qesDvLT1Y2BA"
        )

        # 4) Logs Airtable
        log_to_airtable(
            pseudo=message.from_user.username or message.from_user.first_name,
            user_id=user_id,
            type_acces="VIP",
            montant=2.0,
            contenu="Pack 2 photos + 1 vidéo + accès VIP"
        )

        # 5) Notification dans le TOPIC du client (si on a réussi à le récupérer)
        if topic_id is not None:
            try:
                await bot.request(
                    "sendMessage",
                    {
                        "chat_id": int(os.getenv("STAFF_GROUP_ID", "0")),
                        "message_thread_id": topic_id,
                        "text": (
                            f"🌟 *Nouveau VIP confirmé*\n\n"
                            f"👤 Client : @{message.from_user.username or message.from_user.first_name}\n"
                            f"💶 Montant : 2 €\n"
                            f"📊 Accès VIP enregistré dans le dashboard."
                        ),
                        "parse_mode": "Markdown"
                    }
                )
            except Exception as e:
                print(f"[VIP_TOPICS] Erreur envoi notif VIP dans topic {topic_id} : {e}")

        return  # on sort ici pour ne pas passer à l’accueil normal



    # === Cas C : /start simple (accueil normal) ===
    if is_admin(user_id):
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
    await bot.send_video(
    chat_id=user_id,
    video=WELCOME_VIDEO_FILE_ID
)
    # Envoi à tous les admins (vendeurs)
    try:
        for adm in authorized_admin_ids:
            await bot.send_message(adm, texte_alerte_admin, parse_mode="Markdown")
    except Exception as e:
        print(f"Erreur envoi admin : {e}")

    # Envoi au directeur (toi)
    try:
        await bot.send_message(DIRECTEUR_ID, texte_alerte_directeur, parse_mode="Markdown")
    except Exception as e:
        print(f"Erreur envoi directeur : {e}")

# TEST A SUPPRIMER DEBUT

@dp.message_handler(
    lambda m: m.chat.id == STAFF_GROUP_ID and m.from_user.id in pending_notes,
    content_types=[types.ContentType.TEXT]
)
async def handle_vip_note(message: types.Message):
    admin_id = message.from_user.id

    # DEBUG : tu verras ça dans Render si besoin
    print(f"[NOTES] handle_vip_note triggered for admin_id={admin_id}, chat_id={message.chat.id}")
    print(f"[NOTES] pending_notes = {pending_notes}")

    # Récupérer le VIP concerné et enlever le mode "note"
    vip_user_id = pending_notes.pop(admin_id, None)
    if not vip_user_id:
        # cas bizarre : on était censé être en mode note mais le dict est vide
        return

    note_text = (message.text or "").strip()
    if not note_text:
        await message.reply("❌ Note vide, rien n'a été enregistré.")
        raise CancelHandler()

    print(f"[NOTES] Note reçue pour VIP user_id={vip_user_id} par admin_id={admin_id} : {note_text}")

    # Mise à jour des infos VIP (NOTE UNIQUEMENT)
    info = update_vip_info(vip_user_id, note=note_text)

    panel_message_id = info.get("panel_message_id")
    admin_name = info.get("admin_name") or "Aucun"

    if not panel_message_id:
        await message.reply("⚠️ Impossible de retrouver le panneau VIP pour ce client.")
        raise CancelHandler()

    panel_text = (
        "🧐 PANEL DE CONTRÔLE VIP\n\n"
        f"👤 Client : {vip_user_id}\n"
        f"📒 Notes : {note_text}\n"
        f"👤 Admin en charge : {admin_name}"
    )

    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Prendre en charge", callback_data=f"prendre_{vip_user_id}"),
        InlineKeyboardButton("📝 Ajouter une note", callback_data=f"annoter_{vip_user_id}")
    )

    # On met à jour le panneau dans le STAFF_GROUP
    await bot.edit_message_text(
        chat_id=STAFF_GROUP_ID,
        message_id=panel_message_id,
        text=panel_text,
        reply_markup=kb
    )

    # Petite confirmation dans le topic
    await message.reply("✅ Note enregistrée et panneau mis à jour.", reply=False)

    # 🔥 Très important : empêche les autres handlers (dont /env) de traiter ce message
    raise CancelHandler()


# TEST A SUPPRIMER FIN


# Message et média personnel avec lien 

import re

@dp.message_handler(
    lambda message: is_admin(message.from_user.id)
    and admin_modes.get(message.from_user.id) is None   # ✅ Seulement si pas de diffusion en cours
    and (
        (message.text and "/env" in message.text.lower()) or 
        (message.caption and "/env" in message.caption.lower())
    ),
    content_types=[types.ContentType.TEXT, types.ContentType.PHOTO, 
                   types.ContentType.VIDEO, types.ContentType.DOCUMENT]
)
async def envoyer_contenu_payant(message: types.Message):
    import re  # au cas où pas importé en haut
    admin_id = message.from_user.id

    # 0) ⚠️ si on est en mode "envoi groupé payant", on NE FAIT RIEN
    if admin_modes.get(admin_id) == "en_attente_message_payant":
        return

    # 1) ici c'est le mode NORMAL : on veut répondre à UN client
    if not message.reply_to_message:
        await bot.send_message(
            chat_id=admin_id,
            text="❗ Utilise cette commande en réponse à un message du client."
        )
        return

    # 2) retrouver le client ciblé
    if message.reply_to_message.forward_from:
        user_id = message.reply_to_message.forward_from.id
    else:
        user_id = pending_replies.get((message.chat.id, message.reply_to_message.message_id))

    # 🔥 CAS SPÉCIAL : si on n'a pas de user_id mais qu'on est en mode "note VIP"
    if not user_id:
        # si cet admin est en mode note, on utilise CE message comme note
        if admin_id in pending_notes:
            vip_user_id = pending_notes.pop(admin_id)
            note_text = (message.text or message.caption or "").strip()

            if not note_text:
                await bot.send_message(
                    chat_id=admin_id,
                    text="❗ Note vide, rien n'a été enregistrée."
                )
                return

            # Mise à jour des infos VIP (note)
            info = update_vip_info(vip_user_id, note=note_text)

            topic_id = info.get("topic_id")
            panel_message_id = info.get("panel_message_id")
            admin_name = (
                info.get("admin_name")
                or message.from_user.username
                or message.from_user.first_name
                or str(admin_id)
            )

            if topic_id and panel_message_id:
                panel_text = (
                    "🧐 PANEL DE CONTRÔLE VIP\n\n"
                    f"👤 Client : {vip_user_id}\n"
                    f"📒 Notes : {note_text}\n"
                    f"👤 Admin en charge : {admin_name}"
                )

                kb = InlineKeyboardMarkup()
                kb.add(
                    InlineKeyboardButton("✅ Prendre en charge", callback_data=f"prendre_{vip_user_id}"),
                    InlineKeyboardButton("📝 Ajouter une note", callback_data=f"annoter_{vip_user_id}")
                )

                await bot.edit_message_text(
                    chat_id=STAFF_GROUP_ID,
                    message_id=panel_message_id,
                    text=panel_text,
                    reply_markup=kb
                )

                await bot.send_message(
                    chat_id=admin_id,
                    text="✅ Note enregistrée et panneau mis à jour."
                )
                return
            else:
                await bot.send_message(
                    chat_id=admin_id,
                    text="⚠️ Panneau VIP introuvable pour ce client."
                )
                return

        # 💬 CAS NORMAL (pas en mode note) → on garde ton comportement d'origine
        await bot.send_message(chat_id=admin_id, text="❗ Impossible d'identifier le destinataire.")
        return

    # 3) lire /envXX
    texte = message.caption or message.text or ""
    match = re.search(r"/env(\d+|vip)", texte.lower())
    if not match:
        await bot.send_message(chat_id=admin_id, text="❗ Aucun code /envXX valide détecté.")
        return

    code = match.group(1)

    # ⚠️ on utilise le dict GLOBAL défini plus haut
    lien = liens_paiement.get(code)
    if not lien:
        await bot.send_message(chat_id=admin_id, text="❗ Ce montant n'est pas reconnu dans les liens disponibles.")
        return

    # on remplace /envXX par le vrai lien Stripe
    nouvelle_legende = re.sub(r"/env(\d+|vip)", lien, texte, flags=re.IGNORECASE)

    # 4) si l'admin a joint un média → on le stocke en "contenu en attente"
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
            # on enlève le /envXX dans la caption envoyée après paiement
            "caption": re.sub(r"/env(\d+|vip)", "", texte, flags=re.IGNORECASE).strip()
        }
        from vip_topics import ensure_topic_for_vip
        dummy_user = types.User(id=user_id, is_bot=False, first_name=str(user_id))
        topic_id = await ensure_topic_for_vip(dummy_user)

        await bot.request(
            "sendMessage",
            {
                "chat_id": STAFF_GROUP_ID,
                "message_thread_id": topic_id,
                "text": f"✅ Contenu prêt pour l'utilisateur {user_id}."
            }
        )

        # cas où le client avait déjà payé → on envoie direct
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

    # 5) sinon → on envoie le flouté + lien
    await bot.send_photo(
        chat_id=user_id,
        photo=DEFAULT_FLOU_IMAGE_FILE_ID,
        caption=nouvelle_legende
    )
    await bot.send_message(
        chat_id=user_id,
        text=f"_🔒 Ce contenu {code} € est verrouillé. Clique sur le lien ci-dessus pour le déverrouiller._",
        parse_mode="Markdown"
    )



@dp.message_handler(lambda message: message.text == "📖 Commandes" and is_admin(message.from_user.id))
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

@dp.message_handler(lambda message: message.text == "📊 Statistiques" and is_admin(message.from_user.id))
async def show_stats_direct(message: types.Message):
    await handle_stat(message)


# ======================== IMPORTS & VARIABLES ========================

# ========== HANDLER ADMIN : réponses privées + messages groupés ==========

@dp.message_handler(lambda message: is_admin(message.from_user.id), content_types=types.ContentType.ANY)
async def handle_admin_message(message: types.Message):
    admin_id = message.from_user.id
    mode = admin_modes.get(admin_id)

    # 1) L'admin ouvre le menu d'envoi groupé
    if message.text == "✉️ Message à tous les VIPs":
        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton("📩 Message gratuit", callback_data="vip_message_gratuit"),
            InlineKeyboardButton("💸 Message payant", callback_data="vip_message_payant")
        )
        await bot.send_message(
            chat_id=admin_id,
            text="🧩 Choisis le type de message à envoyer à tous les VIPs :",
            reply_markup=kb
        )
        return

    # 2) SI on est déjà dans un mode groupé → on traite, puis on sort
    if mode == "en_attente_message":
        admin_modes[admin_id] = None
        await traiter_message_groupé(message, admin_id=admin_id)
        return

    if mode == "en_attente_message_payant":
        admin_modes[admin_id] = None
        await traiter_message_payant_groupé(message, admin_id=admin_id)
        return

    # 3) SINON → c'est le comportement normal (réponse à un client)
    user_id = None

    if message.reply_to_message:
        # 🔍 Ancien comportement : on se base sur le forward ou pending_replies
        if message.reply_to_message.forward_from:
            user_id = message.reply_to_message.forward_from.id
        else:
            user_id = pending_replies.get((message.chat.id, message.reply_to_message.message_id))
    else:
        # Pas de reply → si on est dans le supergroupe staff, on utilise le topic_id
        if message.chat.id == STAFF_GROUP_ID and message.message_thread_id is not None:
            user_id = get_user_id_by_topic_id(message.message_thread_id)
        else:
            print("❌ Pas de reply détecté (et pas dans un topic staff connu)")
            return

    if not user_id:
        await bot.send_message(chat_id=admin_id, text="❗Impossible d'identifier le destinataire.")
        return

    # ✅ Envoi normal (comme avant)
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
            await bot.send_message(chat_id=admin_id, text="📂 Type de message non supporté.")
    except Exception as e:
        await bot.send_message(chat_id=admin_id, text=f"❗Erreur admin -> client : {e}")


# ========== IMPORTS ESSENTIELS ==========
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ========== HANDLER CLIENT : transfert vers admin ==========

from ban_storage import ban_list  # à ajouter tout en haut si pas déjà fait


STAFF_GROUP_ID = int(os.getenv("STAFF_GROUP_ID", "0"))

@dp.message_handler(
    lambda message: message.chat.type == "private" and not is_admin(message.from_user.id),
    content_types=types.ContentType.ANY
)
async def relay_from_client(message: types.Message):
    """
    Tous les clients (VIP ou non) sont transférés dans un topic dédié
    dans le STAFF_GROUP. Le statut VIP sert uniquement aux stats / envois groupés.
    """
    user_id = message.from_user.id

    print(f"[RELAY] message from {user_id} (chat {message.chat.id}), authorized={user_id in authorized_users}")

    # 1) Vérifier la ban_list
    for admin_id, clients_bannis in ban_list.items():
        if user_id in clients_bannis:
            try:
                await message.delete()
            except Exception:
                pass
            try:
                await bot.send_message(
                    user_id,
                    "🚫 Tu as été banni, tu ne peux plus envoyer de messages."
                )
            except Exception:
                pass
            return

    # 2) Création / récupération du topic dédié pour ce client
    try:
        from vip_topics import ensure_topic_for_vip

        topic_id = await ensure_topic_for_vip(message.from_user)

        res = await bot.request(
            "forwardMessage",
            {
                "chat_id": STAFF_GROUP_ID,
                "from_chat_id": message.chat.id,
                "message_id": message.message_id,
                "message_thread_id": topic_id,
            }
        )

        sent_msg_id = res.get("message_id")
        if sent_msg_id:
            pending_replies[(STAFF_GROUP_ID, sent_msg_id)] = message.chat.id

        print(f"✅ Message client reçu de {message.chat.id} et transféré dans le topic {topic_id}")
    except Exception as e:
        print(f"❌ Erreur transfert message client vers topic : {e}")


# 1. code pour le bouton prendre en charge début

@dp.callback_query_handler(lambda c: c.data.startswith("prendre_"))
async def handle_prendre_en_charge(callback_query: types.CallbackQuery):
    admin_id = callback_query.from_user.id
    data = callback_query.data  # ex: "prendre_8440217096"

    try:
        vip_user_id = int(data.split("_", 1)[1])
    except Exception:
        await callback_query.answer("ID VIP invalide.", show_alert=True)
        return

    # Déterminer le nom de l'admin
    admin_name = (
        callback_query.from_user.username
        or callback_query.from_user.first_name
        or str(admin_id)
    )

    print(f"[VIP] Admin {admin_id} prend en charge VIP {vip_user_id} ({admin_name})")

    # On met à jour les infos VIP (ADMIN UNIQUEMENT)
    info = update_vip_info(
        vip_user_id,
        admin_id=admin_id,
        admin_name=admin_name,
    )

    panel_message_id = info.get("panel_message_id")
    note_text = info.get("note", "Aucune note")

    if not panel_message_id:
        await callback_query.answer("Panneau introuvable pour ce VIP.", show_alert=True)
        return

    panel_text = (
        "🧐 PANEL DE CONTRÔLE VIP\n\n"
        f"👤 Client : {vip_user_id}\n"
        f"📒 Notes : {note_text}\n"
        f"👤 Admin en charge : {admin_name}"
    )

    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Prendre en charge", callback_data=f"prendre_{vip_user_id}"),
        InlineKeyboardButton("📝 Ajouter une note", callback_data=f"annoter_{vip_user_id}")
    )

    # On met à jour le panneau
    await bot.edit_message_text(
        chat_id=STAFF_GROUP_ID,
        message_id=panel_message_id,
        text=panel_text,
        reply_markup=kb
    )

    await callback_query.answer("✅ Tu es maintenant en charge de ce VIP.")



# 1. code pour le bouton prendre en charge fin

# 1. code pour le bouton annoter début



@dp.callback_query_handler(lambda c: c.data and c.data.startswith("annoter_"))
async def handle_annoter_vip(callback_query: types.CallbackQuery):
    admin_id = callback_query.from_user.id

    # Vérifier qu'on clique bien depuis le STAFF_GROUP
    if callback_query.message.chat.id != STAFF_GROUP_ID:
        await callback_query.answer("Action réservée au staff.", show_alert=True)
        return

    # Récupère l'user_id du VIP depuis la callback
    try:
        user_id = int(callback_query.data.split("_", 1)[1])
    except Exception:
        await callback_query.answer("Données invalides.", show_alert=True)
        return

    # Si l'admin est déjà en mode note, renvoyer une info et ne rien re-créer
    if admin_id in pending_notes:
        current_target = pending_notes.get(admin_id)
        # Si c'est pour le même client, on informe
        if current_target == user_id:
            await callback_query.answer("📝 Tu es déjà en mode annotation pour ce client. Envoie ta note dans le topic.", show_alert=False)
            return
        # Sinon, prévenir que l'admin est déjà en mode note pour un autre client
        await callback_query.answer("🔔 Tu es actuellement en mode annotation pour un autre client. Termine ou annule d'abord.", show_alert=True)
        return

    # On récupère les infos déjà stockées (topic_id, panel_message_id, etc.)
    info = update_vip_info(user_id)  # sans note/admin => juste retour du dict
    topic_id = info.get("topic_id")

    if not topic_id:
        await callback_query.answer("Impossible de retrouver le topic VIP.", show_alert=True)
        return

    # On passe cet admin en "mode note" pour ce user_id
    pending_notes[admin_id] = user_id

    # Marquer l'admin comme "en train d'annoter" visuellement (ferme le loader)
    await callback_query.answer()

    # ⚠️ ICI : on utilise bot.request pour poster DANS LE TOPIC
    try:
        await bot.request(
            "sendMessage",
            {
                "chat_id": STAFF_GROUP_ID,
                "message_thread_id": topic_id,
                "text": (
                    f"📝 Envoie maintenant ta note pour le client {user_id} dans ce topic.\n"
                    "➡️ Le prochain message que tu écris ici sera enregistré comme NOTE.\n\n"
                    "Si tu veux annuler : envoie `/annuler_note`."
                ),
            },
        )
    except Exception as e:
        # Nettoyage si envoi échoue (pour éviter rester bloqué en pending)
        pending_notes.pop(admin_id, None)
        print(f"[NOTES] Erreur envoi prompt annotation (callback annoter_) : {e}")
        await callback_query.answer("Impossible d'envoyer l'invite d'annotation.", show_alert=True)




# 1. code pour le bouton annoter fin


# ========== CHOIX DANS LE MENU INLINE ==========

@dp.callback_query_handler(lambda call: call.data in ["vip_message_gratuit", "vip_message_payant"])
async def choix_type_message_vip(call: types.CallbackQuery):
    await call.answer()
    admin_id = call.from_user.id
    if call.data == "vip_message_gratuit":
        admin_modes[admin_id] = "en_attente_message"
        await bot.send_message(
            chat_id=admin_id,
            text="✍️ Envoie maintenant le message (texte/photo/vidéo) à diffuser GRATUITEMENT à tous les VIPs."
        )
    else:
        admin_modes[admin_id] = "en_attente_message_payant"
        await bot.send_message(
            chat_id=admin_id,
            text="✍️ Envoie maintenant le message (texte/photo/vidéo) à diffuser PAYANT à tous les VIPs."
        )

# ========== TRAITEMENT MESSAGE GROUPÉ GRATUIT ==========

async def traiter_message_groupé(message: types.Message, admin_id=None):
    admin_id = admin_id or message.from_user.id
    if message.text:
        pending_mass_message[admin_id] = {"type": "text", "content": message.text}
        preview = message.text
    elif message.photo:
        pending_mass_message[admin_id] = {
            "type": "photo",
            "content": message.photo[-1].file_id,
            "caption": message.caption or ""
        }
        preview = f"[Photo] {message.caption or ''}"
    elif message.video:
        pending_mass_message[admin_id] = {
            "type": "video",
            "content": message.video.file_id,
            "caption": message.caption or ""
        }
        preview = f"[Vidéo] {message.caption or ''}"
    elif message.audio:
        pending_mass_message[admin_id] = {"type": "audio", "content": message.audio.file_id, "caption": message.caption or ""}
        preview = f"[Audio] {message.caption or ''}"
    elif message.voice:
        pending_mass_message[admin_id] = {"type": "voice", "content": message.voice.file_id}
        preview = "[Note vocale]"
    else:
        await message.reply("❌ Message non supporté.")
        return

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Confirmer l’envoi", callback_data="confirmer_envoi_groupé"),
        InlineKeyboardButton("❌ Annuler l’envoi", callback_data="annuler_envoi_groupé")
    )
    await message.reply(f"Prévisualisation :\n\n{preview}", reply_markup=kb)



# ========== CALLBACKS ENVOI / ANNULATION GROUPÉ ==========

@dp.callback_query_handler(lambda call: call.data == "confirmer_envoi_groupé")
async def confirmer_envoi_groupé(call: types.CallbackQuery):
    await call.answer()
    admin_id = call.from_user.id
    message_data = pending_mass_message.get(admin_id)
    if not message_data:
        await call.message.edit_text("❌ Aucun message en attente à envoyer.")
        return

    await bot.send_message(chat_id=admin_id, text="⏳ Envoi du message à tous les VIPs...")

    envoyes = 0
    erreurs = 0

    for vip_id in list(authorized_users):
        try:
            vip_id = int(vip_id)

            # cas PAYANT → on envoie l'image floutée + le lien dans la légende
            if message_data.get("payant"):
                await bot.send_photo(
                    chat_id=vip_id,
                    photo=DEFAULT_FLOU_IMAGE_FILE_ID,
                    caption=message_data.get("caption", "")
                )
                await bot.send_message(
                    chat_id=vip_id,
                    text="_🔒 Ce contenu est verrouillé. Paie via le lien ci-dessus pour le débloquer._",
                    parse_mode="Markdown"
                )
            else:
                # cas GRATUIT → on envoie tel quel
                if message_data["type"] == "text":
                    await bot.send_message(chat_id=vip_id, text=message_data["content"])
                elif message_data["type"] == "photo":
                    await bot.send_photo(chat_id=vip_id, photo=message_data["content"], caption=message_data.get("caption", ""))
                elif message_data["type"] == "video":
                    await bot.send_video(chat_id=vip_id, video=message_data["content"], caption=message_data.get("caption", ""))
                elif message_data["type"] == "audio":
                    await bot.send_audio(chat_id=vip_id, audio=message_data["content"], caption=message_data.get("caption", ""))
                elif message_data["type"] == "voice":
                    await bot.send_voice(chat_id=vip_id, voice=message_data["content"])

            envoyes += 1
        except Exception as e:
            print(f"❌ Erreur envoi à {vip_id} : {e}")
            erreurs += 1

    await bot.send_message(chat_id=admin_id, text=f"✅ Envoyé à {envoyes} VIP(s).\n⚠️ Échecs : {erreurs}")
    pending_mass_message.pop(admin_id, None)


@dp.callback_query_handler(lambda call: call.data == "annuler_envoi_groupé")
async def annuler_envoi_groupé(call: types.CallbackQuery):
    await call.answer("❌ Envoi annulé.")
    admin_id = call.from_user.id
    pending_mass_message.pop(admin_id, None)
    await call.message.edit_text("❌ Envoi annulé.")



#mettre le tableau de vips
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
