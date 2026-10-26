"""Chopar — yopiq manba kanalidan medialarni olib, foydalanuvchining
o'z kanaliga ko'chirib yuboradi.

Barcha ma'lumotlar .env dan olinadi (koddа hech qanday maxfiy qiymat yo'q):

    CHOPAR_API_ID, CHOPAR_API_HASH   my.telegram.org dan olingan ilova kaliti
    CHOPAR_PHONE                    birinchi kirish uchun (+998...)
    CHOPAR_SOURCE_CHAT              manba kanal ID yoki @username
    CHOPAR_TARGET_CHAT              maqsad kanal ID yoki @username
    CHOPAR_SESSION_PATH             session fayl yo'li (default: ./data/chopar)
    CHOPAR_BACKFILL_LIMIT           birinchi ishda ko'chiriladigan oxirgi N ta xabar
    CHOPAR_DELAY                    xabarlar orasidagi kutish (soniya)

Komandalar:

    python main.py          # ishga tushirish (session bo'lmasa xato beradi)
    python main.py login    # birinchi kirish: telefon/kod/parol so'rab session yozadi

Dastur qayta ishga tushganda allaqachon ko'chirilgan xabarlarni takrorlamaydi:
oxirgi ko'chirilgan xabar IDsi progress.json da saqlanadi va konteyner
volume'da (chopar-data) qoladi.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import re
import sys
import tempfile
from pathlib import Path
import shutil

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, RPCError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("chopar")


def load_dotenv() -> None:
    """Docker'da env compose tomonidan beriladi; lokal ishda .env o'qiladi."""
    if os.environ.get("CHOPAR_API_ID"):
        return
    for candidate in (Path(__file__).with_name(".env"), Path.cwd() / ".env"):
        try:
            lines = candidate.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())
        return


def env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


def require(name: str) -> str:
    value = env(name)
    if not value:
        log.error("%s .env da o'rnatilmagan.", name)
        sys.exit(1)
    return value


def parse_chat(value: str) -> int | str:
    """"-1003514954083" kabi raqamli manzilni butun songa aylantiradi.

    Telethon string ko'rinishidagi raqamni telefon raqami deb tushunib,
    GetContacts so'rovini yuboradi — bu esa FloodWait olib keladi.
    """
    text = value.strip()
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text


load_dotenv()

API_ID = int(require("CHOPAR_API_ID"))
API_HASH = require("CHOPAR_API_HASH")
PHONE = env("CHOPAR_PHONE", "")
SOURCE = parse_chat(require("CHOPAR_SOURCE_CHAT"))
TARGET = parse_chat(require("CHOPAR_TARGET_CHAT"))

# Dialoglardan topilgan to'liq entity'lar (run() boshida to'ldiriladi).
source_entity = None
target_entity = None
SESSION_PATH = Path(
    env("CHOPAR_SESSION_PATH", str(Path(__file__).resolve().parent / "data" / "chopar"))
)
BACKFILL_LIMIT = int(env("CHOPAR_BACKFILL_LIMIT", "150"))
DELAY = float(env("CHOPAR_DELAY", "2"))

SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
PROGRESS_FILE = SESSION_PATH.parent / "progress.json"

COMMAND = sys.argv[1] if len(sys.argv) > 1 else ""

# TelegramClient konstruktori o'zi session faylini yaratib qo'yadi, shuning uchun
# mavjudligini SHUNDAN oldin tekshiramiz — aks holda tekshirish har doim o'tadi.
if not COMMAND and not SESSION_PATH.with_suffix(".session").exists():
    log.error(
        "Session topilmadi (%s.session). Birinchi marta uchun:\n"
        "  docker compose run --rm --interactive chopar python main.py login",
        SESSION_PATH,
    )
    sys.exit(1)
if COMMAND and COMMAND != "login":
    log.error("Noma'lum komanda: %s", COMMAND)
    sys.exit(1)

client = TelegramClient(str(SESSION_PATH), API_ID, API_HASH)


def load_progress() -> dict:
    try:
        return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_progress(last_id: int) -> None:
    PROGRESS_FILE.write_text(
        json.dumps({"source": str(SOURCE), "last_id": last_id}),
        encoding="utf-8",
    )


async def process_and_send(msg) -> bool:
    """Bitta xabarni yuklab olib kanalga yuboradi. True — muvaffaqiyatli."""
    if msg.action:
        return True
    if not (msg.media or msg.text):
        return True

    tmp_dir = tempfile.mkdtemp(prefix="chopar-")
    file_path = None
    try:
        if msg.media:
            log.info("[MEDIA] ID %s yuklanmoqda...", msg.id)
            file_path = await client.download_media(msg, file=tmp_dir)
            if file_path:
                await client.send_file(
                    target_entity,
                    file=file_path,
                    caption=msg.text or "",
                    supports_streaming=True
                )
            elif msg.text:
                # Yuklab bo'lmadigan media (masalan interaktiv tugma) — matnni ko'chiramiz.
                await client.send_message(target_entity, message=msg.text)
        elif msg.text:
            await client.send_message(target_entity, message=msg.text)

        log.info("[OK] ID %s ko'chirildi", msg.id)
        return True
    except FloodWaitError as exc:
        log.warning("FloodWait %s soniya — kutamiz (ID %s)", exc.seconds, msg.id)
        await asyncio.sleep(exc.seconds + 1)
        return False
    except RPCError as exc:
        log.error("[XATO] ID %s yuborilmadi: %s", msg.id, exc)
        return False
    finally:
        # Yaratilgan vaqtinchalik papkani va faylni to'liq o'chirish
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)
        


async def copy_range(min_id: int = 0, limit: int | None = None) -> None:
    """min_id dan keyingi (yoki oxirgi limit ta) xabarlarni eskidan yangiga
    tartibda ko'chiradi va har biridan keyin progressni saqlaydi.

    Xabar ko'chirilmasa (FloodWait/RPC xato) u bosqich ichida qayta
    uriniladi; natija bo'lmasa backfill to'xtaydi — progress faqat
    muvaffaqiyatli xabargacha yozilgani uchun qayta ishga tushirish
    o'sha joydan davom etadi.
    """
    if min_id:
        iterator = client.iter_messages(source_entity, min_id=min_id, reverse=True)
        messages = [msg async for msg in iterator]
    else:
        collected = [
            msg async for msg in client.iter_messages(source_entity, limit=limit)
        ]
        messages = list(reversed(collected))

    total = len(messages)
    log.info("Ko'chiriladigan xabarlar: %s ta", total)
    for index, msg in enumerate(messages, start=1):
        for attempt in range(3):
            ok = await process_and_send(msg)
            if ok:
                break
            await asyncio.sleep(min(DELAY * (attempt + 1) * 5, 60))
        if not ok:
            log.error(
                "Xabar %s ko'chirilmadi — backfill to'xtatildi. "
                "Qayta ishga tushirish shu joydan davom etadi.",
                msg.id,
            )
            return
        save_progress(msg.id)
        log.info("  %s/%s", index, total)
        await asyncio.sleep(DELAY)


async def resolve_entity(ref: int | str, role: str):
    """Manba/maqsad kanalni dialoglar ro'yxatidan topadi.

    Raqamli ID keshda ham, dialogda ham bo'lishi shart; Telethon'ning
    ``get_input_entity`` funksiyasi manzilni keshsiz topa olmaydi.
    """
    if isinstance(ref, str):
        # @username yoki invite-link — to'g'ridan-to'g'ri so'rov bilan olamiz.
        return await client.get_entity(ref)
    async for dialog in client.iter_dialogs():
        if dialog.id == ref:
            return dialog.entity
    log.error(
        "%s kanal topilmadi (ID %s): akkaunt bu kanalga a'zo emas "
        "yoki ID noto'g'ri.",
        role,
        ref,
    )
    sys.exit(1)


async def resolve_targets() -> None:
    """Manba va maqsad entity'larini topadi; FloodWait bo'lsa kutadi."""
    global source_entity, target_entity
    while True:
        try:
            source_entity = await resolve_entity(SOURCE, "Manba")
            target_entity = await resolve_entity(TARGET, "Maqsad")
            return
        except FloodWaitError as exc:
            log.warning("Telegram cheklovi: %s soniya kutyapiz...", exc.seconds)
            await asyncio.sleep(exc.seconds + 5)


async def run() -> None:
    await client.connect()
    if not await client.is_user_authorized():
        log.error(
            "Session yozilgan, lekin avtorizatsiyadan o'tmagan. Qayta login qiling:\n"
            "  docker compose run --rm --interactive chopar python main.py login"
        )
        sys.exit(1)
    me = await client.get_me()
    log.info("Telegram ulandi: %s", me.username or me.phone)

    await resolve_targets()
    log.info(
        "Kanallar topildi: manba ID %s → maqsad ID %s",
        getattr(source_entity, "id", SOURCE),
        getattr(target_entity, "id", TARGET),
    )

    progress = load_progress()
    last_id = int(progress.get("last_id") or 0)

    if progress.get("source") != str(SOURCE):
        # Manba o'zgargan — progressni e'tiborsiz qoldiramiz.
        last_id = 0

    if last_id:
        log.info("Davom etamiz: ID > %s (oxirgi ko'chirilgan)", last_id)
        await copy_range(min_id=last_id)
    else:
        log.info("Birinchi ishga tushirish: oxirgi %s ta xabar", BACKFILL_LIMIT)
        await copy_range(limit=BACKFILL_LIMIT)

    log.info("Backfill tugadi. Endi yangi xabarlar kuzatilmoqda...")

    @client.on(events.NewMessage(chats=source_entity))
    async def handler(event):
        log.info("[YANGI XABAR] ID %s", event.message.id)
        for attempt in range(3):
            if await process_and_send(event.message):
                save_progress(event.message.id)
                break
            await asyncio.sleep(min(DELAY * (attempt + 1) * 5, 60))
        else:
            log.error(
                "Yangi xabar %s ko'chirilmadi — qayta ishga tushirilganda "
                "orqadagi xabarlar bilan birga qayta uriniladi.",
                event.message.id,
            )
        await asyncio.sleep(DELAY)

    await client.run_until_disconnected()


async def start_and_close() -> None:
    """Telethon'ning ``start``/``disconnect`` metodlari dual: senkron
    kontekstda ``self`` qaytaradi, ishlayotgan loop ichida korutina.
    Shuning uchun qaytgan qiymatni kutyapmiz.
    """
    # PHONE bo'sh bo'lsa, telefoni so'rab so'rang (Telethon'ning default
    # lambda'si) — ``phone=None`` buni o'chirib qo'yadi va ValueError beradi.
    kwargs = {"phone": PHONE} if PHONE else {}
    result = client.start(**kwargs)
    if inspect.isawaitable(result):
        await result
    result = client.disconnect()
    if inspect.isawaitable(result):
        await result


def main() -> None:
    if COMMAND == "login":
        # Birinchi kirish: telefon, Telegram kod va (bo'lsa) 2FA parol so'raladi.
        client.loop.run_until_complete(start_and_close())
        log.info("Session saqlandi: %s.session", SESSION_PATH)
        return

    try:
        client.loop.run_until_complete(run())
    finally:
        # Bu yerda loop to'xtagan — disconnect senkron chaqiriladi.
        if client.is_connected():
            client.disconnect()


if __name__ == "__main__":
    main()
