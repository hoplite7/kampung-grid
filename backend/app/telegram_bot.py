"""The Telegram bot: a judge's own phone buzzes with a real message. (Person 1 owns this.)

Turn it on with KG_TELEGRAM_TOKEN in backend/.env (from @BotFather). Without a token
the bot simply stays off and nothing else changes.

How it works
    1. The judge scans the QR code -> Telegram opens t.me/<bot>?start=kavitha -> taps Start.
    2. They now play that helper. When the crisis starts, their task arrives here as a
       Telegram message with buttons (On my way / Reached / Need help).
    3. In "low data" mode the task arrives as SMS-style text with 1 / 2 buttons.
    4. /stop, or Reset on the control panel, deletes their chat ID. It's never saved to disk.

We use "long polling" (we ask Telegram for new messages), so no public web address is needed.
"""

import asyncio
import os

import httpx

from . import people

TOKEN = os.getenv("KG_TELEGRAM_TOKEN", "").strip()
API = os.getenv("KG_TELEGRAM_API", "https://api.telegram.org")

# chat_id -> helper_id, and back. In memory only.
CHATS: dict[int, str] = {}
STATE = {"username": None, "running": False, "error": None}
_sent: set[tuple[int, str]] = set()  # (task_id, kind) already sent, so nothing arrives twice
_task = None

BUTTONS = {
    "en": {"on_the_way": "On my way", "reached": "Reached", "need_help": "Need help"},
    "ms": {"on_the_way": "Dalam perjalanan", "reached": "Sudah sampai", "need_help": "Perlu bantuan"},
    "zh": {"on_the_way": "我在路上", "reached": "已到达", "need_help": "需要帮助"},
    "ta": {"on_the_way": "வழியில்", "reached": "சென்றடைந்தேன்", "need_help": "உதவி தேவை"},
}

WELCOME = (
    "Welcome to the Kampung Grid demo! You're now playing {name}, a helper at {unit}, Block 123.\n\n"
    "Everything here is made up for the demo. We don't see your phone number, only a chat ID, "
    "and it's deleted when the demo resets or you send /stop.\n\n"
    "Keep this chat open. If a neighbour needs you, a message will arrive here."
)


# ---- Talking to Telegram ------------------------------------------------------


async def call(method: str, **params) -> dict:
    """One Telegram API call. Replaced in tests."""
    async with httpx.AsyncClient(timeout=40) as client:
        r = await client.post(f"{API}/bot{TOKEN}/{method}", json=params)
        return r.json()


async def send(chat_id: int, text: str, buttons: list[list[tuple[str, str]]] | None = None) -> None:
    params: dict = {"chat_id": chat_id, "text": text}
    if buttons:
        params["reply_markup"] = {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in buttons]}
    try:
        await call("sendMessage", **params)
    except Exception as exc:
        print(f"[telegram] send failed: {exc}")


def chat_for(helper_id: str | None) -> int | None:
    return next((c for c, h in CHATS.items() if h == helper_id), None)


def task_buttons(task_id: int, status: str, lang: str) -> list[list[tuple[str, str]]]:
    b = BUTTONS.get(lang, BUTTONS["en"])
    first = ("on_the_way", b["on_the_way"]) if status == "sent" else ("reached", b["reached"])
    return [[(first[1], f"t:{task_id}:{first[0]}")], [(b["need_help"], f"t:{task_id}:need_help")]]


# ---- Messages from people -------------------------------------------------------


async def handle_update(update: dict) -> None:
    if "message" in update:
        msg = update["message"]
        chat = msg["chat"]["id"]
        text = (msg.get("text") or "").strip()
        if text.startswith("/start"):
            role = text.split(" ", 1)[1].strip() if " " in text else ""
            if role:
                await join(chat, role)
            else:
                await offer_roles(chat)
        elif text.startswith("/stop"):
            helper = CHATS.pop(chat, None)
            if helper:
                people.release(helper)
            await send(chat, "You've left the demo. Your chat ID has been deleted. Thanks for playing!")
        else:
            await send(chat, "Tap the buttons on your task when one arrives. Send /stop to leave the demo.")
    elif "callback_query" in update:
        await handle_button(update["callback_query"])


async def offer_roles(chat: int) -> None:
    free = [r for r in people.roles() if not r["taken"]]
    if not free:
        await send(chat, "Sorry, every helper role is taken right now.")
        return
    await send(chat, "Who would you like to play?", [[(f"{r['name']} ({r['unit']})", f"j:{r['helper_id']}")] for r in free])


async def join(chat: int, role: str) -> None:
    old = CHATS.get(chat)
    if old and old != role:
        people.release(old)
    try:
        r = people.claim(role, "telegram")
    except ValueError as exc:
        await send(chat, f"{exc}. Pick another:")
        await offer_roles(chat)
        return
    CHATS[chat] = role
    await send(chat, WELCOME.format(name=r["name"], unit=r["unit"]))
    from .live import hub

    await hub.broadcast({"type": "joined", "helper_id": role, "via": "telegram"})


async def handle_button(q: dict) -> None:
    from . import crisis, silence
    from .db import get_session
    from .models import Task

    chat = q["message"]["chat"]["id"]
    kind, *rest = q.get("data", "").split(":")
    reply = "Done"
    # Remove the buttons from the message that was tapped, so old buttons don't pile up.
    if q["message"].get("message_id"):
        try:
            await call("editMessageReplyMarkup", chat_id=chat, message_id=q["message"]["message_id"], reply_markup={"inline_keyboard": []})
        except Exception:
            pass
    try:
        if kind == "j":
            await join(chat, rest[0])
        elif kind == "t":
            task_id, status = int(rest[0]), rest[1]
            with get_session() as s:
                task = s.get(Task, task_id)
            if task is None or task.helper_id != CHATS.get(chat):
                reply = "This task isn't yours"
            elif task.status in {"reached", "need_help", "reassigned", "escalated"}:
                reply = "This task is already closed"
            else:
                await crisis.set_task_status(task_id, status)
                await after_tap(chat, task_id, status, people.helper_language(task.helper_id))
        elif kind == "k":
            await silence.resolve(int(rest[0]), rest[1])
            await send(chat, "Thank you for checking on him. 🙏" if rest[1] == "okay" else "Thank you. An RC volunteer will be asked next.")
    except Exception as exc:
        print(f"[telegram] button failed: {exc}")
        reply = "Something went wrong"
    try:
        await call("answerCallbackQuery", callback_query_id=q["id"], text=reply)
    except Exception:
        pass


async def after_tap(chat: int, task_id: int, status: str, lang: str) -> None:
    if status == "on_the_way":
        await send(chat, "Thank you. Tap when you've reached them:", task_buttons(task_id, "on_the_way", lang))
    elif status == "reached":
        await send(chat, "✓ Thank you. Stay with them until help arrives, if you can.")
    elif status == "need_help":
        await send(chat, "Help is being sent. If it's an emergency, call 995 now.")


# ---- Messages from the system (every live message passes through here) ------


async def on_live(msg: dict) -> None:
    t = msg.get("type")
    if t == "reset":
        for chat in list(CHATS):
            await send(chat, "The demo has been reset. Thanks for playing! Your chat ID has been deleted.")
        CHATS.clear()
        _sent.clear()
        return
    if t == "task_updated":
        task = msg["task"]
        chat = chat_for(task.get("helper_id"))
        ins = task.get("instructions")
        if chat and ins and task["status"] in {"sent", "on_the_way"} and (task["id"], "task") not in _sent:
            _sent.add((task["id"], "task"))
            steps = "\n".join(f"{i}. {s}" for i, s in enumerate(ins.get("steps", []), 1))
            bring = f"\n\nBring: {', '.join(ins['bring'])}" if ins.get("bring") else ""
            await send(chat, f"🚨 A neighbour needs you\n\n{ins['headline']}\n\n{steps}{bring}", task_buttons(task["id"], task["status"], ins.get("language", "en")))
    elif t == "sms":
        chat = chat_for(msg.get("helper_id"))
        if chat and (msg["task_id"], "sms") not in _sent:
            _sent.add((msg["task_id"], "sms"))
            await send(
                chat,
                f"📵 Mobile data is down. In real life this arrives as an SMS:\n\n{msg['text']}",
                [[("1 · reached", f"t:{msg['task_id']}:reached"), ("2 · need help", f"t:{msg['task_id']}:need_help")]],
            )
    elif t == "task_status":
        task = msg["task"]
        chat = chat_for(task.get("helper_id"))
        if chat and task["status"] == "reassigned" and (task["id"], "moved") not in _sent:
            _sent.add((task["id"], "moved"))
            await send(chat, f"{task['resident_name']}'s task has moved to another neighbour, because it wasn't accepted in time. Thank you anyway.")
    elif t == "knock_request":
        chat = chat_for(msg.get("helper_id"))
        c = msg["case"]
        if chat:
            await send(
                chat,
                f"🚪 Could you knock on a neighbour's door?\n\n{c['name']}, {c['unit']}. We haven't heard from him in a while. Please knock and check he's okay. No need to go in.",
                [[("He's okay", f"k:{c['id']}:okay"), ("No answer", f"k:{c['id']}:no_answer")]],
            )
    elif t == "verified_message":
        for chat in CHATS:
            await send(chat, f"✅ Verified update from the town council:\n{msg['answer']}")


# ---- Starting and stopping ------------------------------------------------------


async def _poll() -> None:
    offset = None
    STATE["running"] = True
    while True:
        try:
            params = {"timeout": 25, "allowed_updates": ["message", "callback_query"]}
            if offset is not None:
                params["offset"] = offset
            data = await call("getUpdates", **params)
            if not data.get("ok"):
                STATE["error"] = data.get("description", "Telegram said no")
                print(f"[telegram] {STATE['error']}")
                await asyncio.sleep(5)
                continue
            STATE["error"] = None
            for update in data["result"]:
                offset = update["update_id"] + 1
                try:
                    await handle_update(update)
                except Exception as exc:
                    print(f"[telegram] update failed: {exc}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            STATE["error"] = f"can't reach Telegram ({exc.__class__.__name__})"
            await asyncio.sleep(5)


async def start() -> None:
    global _task
    if not TOKEN:
        print("[telegram] off (no KG_TELEGRAM_TOKEN in .env)")
        return
    try:
        me = await call("getMe")
        if not me.get("ok"):
            STATE["error"] = me.get("description", "bad token")
            print(f"[telegram] couldn't start: {STATE['error']}. Check KG_TELEGRAM_TOKEN in backend/.env")
            return
        STATE["username"] = me["result"]["username"]
        await call("deleteWebhook")
    except Exception as exc:
        STATE["error"] = f"can't reach Telegram ({exc.__class__.__name__})"
        print(f"[telegram] couldn't start: {STATE['error']}")
        return
    from .live import hub

    hub.listeners.append(on_live)
    _task = asyncio.create_task(_poll())
    print(f"[telegram] on: https://t.me/{STATE['username']}")


async def stop() -> None:
    if _task:
        _task.cancel()


def status() -> dict:
    return {"enabled": bool(TOKEN), "username": STATE["username"], "error": STATE["error"], "joined": len(CHATS)}
