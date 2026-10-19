"""AniVoy — the AI assistant: one online model with tools over the catalogue.

The assistant is not a search box with a model glued on. It is a chat model
that is handed a small set of **functions** (OpenAI-style ``tools``) and decides,
per request, which of them it needs:

* ``search_catalog`` — find titles by name, synopsis, genre, type or year;
* ``title_details`` — everything about one title (synopsis, parts, plan, ...);
* ``list_parts`` — the episode/chapter list of a title;
* ``list_genres`` — the catalogue's genres with counts;
* ``popular_titles`` — the highest rated / newest / upcoming titles;
* ``catalog_stats`` — how much content the platform holds;
* ``personal_taste`` — the user's favourites and last watched titles, and only
  registered when the user opted in.

That is what makes "Naruto nechta qismdan iborat?", "menga qo'rqinchli anime
ayt" and "sevimlilarimga o'xshash nima bor?" all answerable by the same
assistant: it calls the function it needs, reads the result, and writes the
answer in Uzbek. No offline encoder, no vector index — the model is the only
"intelligence" and the database is the only source of truth. A title the model
talks about is always a title a tool actually returned.

Everything is strictly online: with no provider configured (or every provider
on cooldown) :class:`movies.llm.LLMUnavailable` is reported through
``AssistantAnswer.error`` and the callers say the assistant is unavailable.
There is no local fallback any more, by design.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from django.db.models import Count, Q

from . import llm
from .models import Genre, MediaPart, MediaTitle

logger = logging.getLogger(__name__)

# How many tool rounds one question may take. Three is plenty for
# "list genres → search in one → look up its parts"; the cap keeps a model that
# keeps calling tools from spending the whole deadline.
MAX_TOOL_ROUNDS = 4
# Titles shown under one answer. The model may have looked up more (they all
# stay in the prompt), but a chat bubble with twenty links is unreadable.
MAX_RESULTS = 12
# Per tool call: enough for a page of titles, small enough for the cheapest
# provider's context window.
MAX_SEARCH_RESULTS = 8
MAX_ANSWER_TOKENS = 900
# An identical question inside this window reuses the previous answer (a page
# refresh or the bot's "yana so'rash" are the common repeats).
CACHE_TTL_SECONDS = 120
CACHE_MAX_ENTRIES = 128
# How much of the conversation rides along with the next question.
MAX_HISTORY_MESSAGES = 10
HISTORY_MESSAGE_MAX_CHARS = 300
# The one-sentence summary shown under a title link.
SUMMARY_MAX_CHARS = 180

SUBSCRIPTION_REQUIRED_TEXT = (
    "AI yordamchi faqat obunachilar uchun. «🎫 Obuna» bo'limidan tarifni tanlang."
)
UNAVAILABLE_TEXT = (
    "AI yordamchi hozircha javob bera olmaydi: model sozlanmagan yoki barcha "
    "provayderlar limitda. Keyinroq qayta urinib ko'ring."
)
EMPTY_QUERY_TEXT = "Savol yoki qidiruv matnini yozing."

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
_EDGE_PUNCTUATION = ".,!?;:()[]{}<>\"'’‘“”«»…"


# --------------------------------------------------------------------------- #
# Shared text helpers
# --------------------------------------------------------------------------- #
def clean_text(value: object) -> str:
    """Collapse whitespace so a query and its cache key are stable."""
    return " ".join(str(value or "").split())


def one_line_summary(title: MediaTitle) -> str:
    """One sentence about the title, shown under its link in the results."""
    synopsis = clean_text(title.synopsis)
    if synopsis:
        sentence = _SENTENCE_END.split(synopsis)[0].strip()
        if len(sentence) > SUMMARY_MAX_CHARS:
            sentence = sentence[: SUMMARY_MAX_CHARS - 1].rstrip() + "…"
        return sentence
    genres = ", ".join(genre.name for genre in title.genres.all()[:3])
    label = title.get_type_display().lower()
    if genres:
        return f"{genres} janridagi {label}."
    return f"{title.get_type_display()} — {title.get_status_display().lower()}."


def title_payload(title: MediaTitle, *, site_url: str = "") -> dict:
    """The JSON shape both clients render for one title card."""
    base = str(site_url or "").rstrip("/")
    slug = title.slug
    return {
        "id": title.pk,
        "title": title.title,
        "slug": slug,
        "type": title.type,
        "type_display": title.get_type_display(),
        "code": title.code,
        "release_year": title.release_year,
        "rating": title.rating,
        "genres": [genre.name for genre in title.genres.all()],
        "summary": one_line_summary(title),
        "url": f"{base}/media/{slug}" if base else f"/media/{slug}",
    }


def format_history(messages: Sequence[Mapping[str, Any]]) -> List[Dict[str, str]]:
    """The last turns as chat messages (``ai`` becomes ``assistant``)."""
    formatted: List[Dict[str, str]] = []
    for item in list(messages or [])[-MAX_HISTORY_MESSAGES:]:
        role = str(item.get("role") or "").strip().lower()
        text = str(item.get("text") or "").strip()[:HISTORY_MESSAGE_MAX_CHARS]
        if not text:
            continue
        formatted.append(
            {"role": "assistant" if role == "ai" else "user", "content": text}
        )
    return formatted


def user_can_use(user) -> bool:
    """The assistant is a paid feature: an active subscription is required.

    The same rule the rest of the site uses — ``is_active`` means a plan that is
    paid *and* not expired.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    subscription = getattr(user, "subscription", None)
    return bool(subscription is not None and subscription.is_active)


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
def _words(query: str) -> List[str]:
    """Query tokens for a forgiving ``icontains`` match.

    Only the edges are trimmed: keeping the apostrophe in ``qo'rqinchli`` is
    what makes it match the synopsis and the genre name as the user wrote it.
    """
    tokens = []
    for raw in clean_text(query).split():
        token = raw.strip(_EDGE_PUNCTUATION)
        if len(token) >= 3:
            tokens.append(token)
    return tokens


def _text_filter(query: str) -> Q:
    tokens = _words(query)
    if not tokens:
        return Q()
    condition = Q()
    for token in tokens:
        condition |= (
            Q(title__icontains=token)
            | Q(synopsis__icontains=token)
            | Q(genres__name__icontains=token)
        )
    return condition


def _candidate_line(index: int, title: MediaTitle) -> str:
    genres = ", ".join(genre.name for genre in title.genres.all()[:4]) or "—"
    return (
        f"{index}. [id: {title.pk}] Nomi: {title.title} | Turi: "
        f"{title.get_type_display()} | Janrlar: {genres} | Yil: "
        f"{title.release_year or '—'} | Reyting: {title.rating}/10 | Kod: "
        f"{title.code} | Mazmun: {one_line_summary(title)}"
    )


class _ToolRunner:
    """Runs the functions the model asks for and remembers what it found.

    ``found`` is the answer's result list: only titles a tool actually returned
    are rendered, so the model can describe the catalogue but never invent a
    title that is not in it. ``used`` records which functions ran, which tells
    the clients whether a question was a catalogue lookup or small talk.
    """

    def __init__(self, *, personal_context: str = "") -> None:
        self.personal_context = (personal_context or "").strip()
        self.found: Dict[int, MediaTitle] = {}
        self.used: List[str] = []
        self._tools: Dict[str, Callable[..., str]] = {
            "search_catalog": self.search_catalog,
            "title_details": self.title_details,
            "list_parts": self.list_parts,
            "list_genres": self.list_genres,
            "popular_titles": self.popular_titles,
            "catalog_stats": self.catalog_stats,
        }
        if self.personal_context:
            self._tools["personal_taste"] = self.personal_taste

    # ------------------------------------------------------------- plumbing
    def schemas(self) -> List[Dict[str, Any]]:
        return [schema for schema in TOOL_SCHEMAS if schema["function"]["name"] in self._tools]

    def run(self, name: str, arguments: str) -> str:
        handler = self._tools.get(name)
        if handler is None:
            return (
                f"Xatolik: '{name}' funksiyasi mavjud emas. Mavjud funksiyalar: "
                + ", ".join(sorted(self._tools))
            )
        self.used.append(name)
        try:
            parsed = json.loads(arguments or "{}")
        except (TypeError, ValueError):
            return "Xatolik: argumentlar JSON obyekt emas."
        if not isinstance(parsed, dict):
            parsed = {}
        try:
            return handler(**parsed)
        except TypeError as exc:
            return f"Xatolik: argumentlar mos kelmadi ({exc})."
        except Exception as exc:  # noqa: BLE001 - a tool bug is reported to the model
            logger.exception("AI tool %s failed", name)
            return f"Xatolik: {name} bajarilmadi ({exc})."

    def _remember(self, title: MediaTitle) -> None:
        self.found.setdefault(title.pk, title)

    def titles(self, *, limit: int = MAX_RESULTS) -> Tuple[MediaTitle, ...]:
        return tuple(list(self.found.values())[: max(1, int(limit or MAX_RESULTS))])

    # -------------------------------------------------------------- the tools
    def search_catalog(
        self,
        matn: str = "",
        tur: str = "",
        janr: str = "",
        yil: Any = None,
        limit: Any = None,
    ) -> str:
        """Search the catalogue and return numbered candidates."""
        try:
            wanted = int(limit or MAX_SEARCH_RESULTS)
        except (TypeError, ValueError):
            wanted = MAX_SEARCH_RESULTS
        wanted = max(1, min(wanted, 10))
        queryset = MediaTitle.objects.prefetch_related("genres")
        if tur:
            media_type = str(tur).strip().lower()
            if media_type in MediaTitle.MediaType.values:
                queryset = queryset.filter(type=media_type)
        if janr:
            queryset = queryset.filter(genres__name__icontains=str(janr).strip())
        try:
            year = int(yil) if yil not in (None, "") else None
        except (TypeError, ValueError):
            year = None
        if year:
            queryset = queryset.filter(release_year=year)
        if matn:
            queryset = queryset.filter(_text_filter(str(matn)))
        results = list(queryset.distinct().order_by("-rating", "-release_year", "title")[:wanted])
        if not results:
            return (
                "Hech narsa topilmadi. Boshqa sinonim, janr nomi yoki "
                "ruscha/inglizcha nom bilan qayta qidirib ko'r."
            )
        lines = [_candidate_line(index, title) for index, title in enumerate(results, start=1)]
        for title in results:
            self._remember(title)
        return "\n".join(lines)

    def title_details(self, id: Any = None, nom: str = "") -> str:
        """Everything about one title: synopsis, genres, parts, access plan."""
        title = self._find_title(id=id, name=nom)
        if title is None:
            return "Bunday kontent katalogda topilmadi."
        self._remember(title)
        parts = MediaPart.objects.filter(content=title)
        seasons = sorted(
            {
                part.season_number
                for part in parts.only("season_number")
                if part.season_number is not None
            }
        )
        genres = ", ".join(genre.name for genre in title.genres.all()) or "—"
        return (
            f"[id: {title.pk}] Nomi: {title.title}\n"
            f"Turi: {title.get_type_display()} | Janrlar: {genres}\n"
            f"Yil: {title.release_year or '—'} | Holat: {title.get_status_display()}\n"
            f"Reyting: {title.rating}/10 | Kod: {title.code}\n"
            f"Qismlar: {parts.count()} | Mavsumlar: "
            f"{', '.join(str(value) for value in seasons) or '—'}\n"
            f"Tarif: {title.get_required_plan_display()} | Til: {title.language}\n"
            f"Tavsif: {clean_text(title.synopsis)[:400] or '—'}"
        )

    def list_parts(self, id: Any = None, nom: str = "") -> str:
        """The episode/chapter list, so "nechta qism bor" has an exact answer."""
        title = self._find_title(id=id, name=nom)
        if title is None:
            return "Bunday kontent katalogda topilmadi."
        self._remember(title)
        parts = list(
            MediaPart.objects.filter(content=title).order_by("season_number", "number")
        )
        if not parts:
            return f"«{title.title}» uchun hali qismlar qo'shilmagan."
        lines = [f"«{title.title}» — {len(parts)} ta qism:"]
        for part in parts[:40]:
            season = f"{part.season_number}-mavsum " if part.season_number else ""
            suffix = f" · {part.title}" if part.title else ""
            lines.append(f"- {season}{part.number}-qism{suffix}")
        if len(parts) > 40:
            lines.append(f"… yana {len(parts) - 40} ta qism")
        return "\n".join(lines)

    def list_genres(self) -> str:
        rows = (
            Genre.objects.annotate(total=Count("media_titles"))
            .filter(total__gt=0)
            .order_by("-total", "name")[:60]
        )
        if not rows:
            return "Janrlar hali kiritilmagan."
        return "Janrlar (kontent soni bilan):\n" + "\n".join(
            f"- {genre.name} ({genre.total})" for genre in rows
        )

    def popular_titles(self, tur: str = "mashhur", limit: Any = None) -> str:
        try:
            wanted = int(limit or MAX_SEARCH_RESULTS)
        except (TypeError, ValueError):
            wanted = MAX_SEARCH_RESULTS
        wanted = max(1, min(wanted, 10))
        kind = str(tur or "mashhur").strip().lower()
        queryset = MediaTitle.objects.prefetch_related("genres")
        if kind in {"yangi", "new", "latest"}:
            queryset = queryset.order_by("-created_at", "-id")
            label = "Eng yangi kontent"
        elif kind in {"kutilmoqda", "upcoming", "tez kunda"}:
            queryset = queryset.filter(status=MediaTitle.Status.UPCOMING).order_by(
                "-created_at"
            )
            label = "Kutilayotgan kontent"
        else:
            queryset = queryset.order_by("-rating", "-created_at")
            label = "Eng yuqori reytingli kontent"
        results = list(queryset[:wanted])
        if not results:
            return f"{label}: hozircha bo'sh."
        for title in results:
            self._remember(title)
        return label + ":\n" + "\n".join(
            _candidate_line(index, title) for index, title in enumerate(results, start=1)
        )

    def catalog_stats(self) -> str:
        counts = {
            row["type"]: row["total"]
            for row in MediaTitle.objects.values("type").annotate(total=Count("id"))
        }
        labels = dict(MediaTitle.MediaType.choices)
        lines = [
            f"- {labels.get(media_type, media_type)}: {counts.get(media_type, 0)} ta"
            for media_type in MediaTitle.MediaType.values
        ]
        return (
            f"Katalogda jami {sum(counts.values())} ta kontent, "
            f"{Genre.objects.count()} ta janr:\n" + "\n".join(lines)
        )

    def personal_taste(self) -> str:
        """The opted-in favourites/recent block, as the model should read it."""
        return self.personal_context or "Foydalanuvchi shaxsiy ma'lumotlarini ulashmagan."

    # -------------------------------------------------------------- helpers
    def _find_title(self, *, id: Any = None, name: str = "") -> Optional[MediaTitle]:
        queryset = MediaTitle.objects.prefetch_related("genres")
        try:
            title_id = int(id) if id not in (None, "") else 0
        except (TypeError, ValueError):
            title_id = 0
        if title_id:
            return queryset.filter(pk=title_id).first()
        text = clean_text(name)
        if not text:
            return None
        if text.isdigit():
            found = queryset.filter(code=text).first()
            if found is not None:
                return found
        return queryset.filter(title__icontains=text).order_by("-rating").first()


def _string_property(description: str) -> Dict[str, Any]:
    return {"type": "string", "description": description}


TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_catalog",
            "description": (
                "Katalogdan kontent qidiradi. Foydalanuvchi janr, kayfiyat, mavzu, "
                "nom yoki yil bo'yicha qidirsa shu funksiyani chaqir. Bir necha "
                "xil sinonim/nom bilan bir necha marta chaqirish mumkin."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "matn": _string_property(
                        "Qidiruv matni: nom, mavzu, kayfiyat yoki janr so'zi. "
                        "Bo'sh qoldirilsa faqat filtrlar qo'llanadi."
                    ),
                    "tur": {
                        "type": "string",
                        "enum": list(MediaTitle.MediaType.values),
                        "description": "Faqat shu turdagi kontent.",
                    },
                    "janr": _string_property("Janr nomi, masalan «Qo'rqinchli»."),
                    "yil": {"type": "integer", "description": "Chiqarilgan yil."},
                    "limit": {
                        "type": "integer",
                        "description": "Nechta natija qaytarilsin (1-10).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "title_details",
            "description": (
                "Bitta kontent haqida to'liq ma'lumot: janr, yil, reyting, qismlar "
                "soni, mavsumlar, tarif va tavsif."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "search_catalog qaytargan [id: N] raqami.",
                    },
                    "nom": _string_property("Kontent nomi yoki 4 xonali kodi."),
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_parts",
            "description": "Kontentning qismlari (epizodlari/boblar) ro'yxati.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "Kontent raqami."},
                    "nom": _string_property("Kontent nomi yoki kodi."),
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_genres",
            "description": "Katalogdagi barcha janrlar va ularning kontent soni.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "popular_titles",
            "description": "Mashhur, eng yangi yoki kutilayotgan kontent ro'yxati.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tur": {
                        "type": "string",
                        "enum": ["mashhur", "yangi", "kutilmoqda"],
                        "description": "Qaysi ro'yxat kerak.",
                    },
                    "limit": {"type": "integer", "description": "Nechta natija."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "catalog_stats",
            "description": "Katalog statistikasi: turlar bo'yicha kontent soni.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "personal_taste",
            "description": (
                "Foydalanuvchining sevimlilari va oxirgi ko'rganlari. Faqat "
                "foydalanuvchi shaxsiy ma'lumotlarini ulashishga rozi bo'lsa "
                "mavjud. «Menga o'xshashini top» kabi so'rovlarda ishlatiladi."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #

SYSTEM_PROMPT = (
    "Sen AniVoy — AniChopar platformasining AI yordamchisisan. "
    "Sening asosiy vazifang foydalanuvchilarning savollariga javob berish, "
    "suhbatlashish, tushuntirish va kerak bo'lganda katalogdan anime, "
    "serial, kino yoki manga topib berishdir.\n\n"

    "MUHIM ASOSIY QOIDA:\n"
    "Har bir suhbatni anime tavsiya qilishga burma. Foydalanuvchining "
    "haqiqiy niyatini tushun va aynan so'ralgan narsaga javob ber. "
    "Foydalanuvchi anime yoki boshqa kontentni so'ramagan bo'lsa, "
    "o'z tashabbusing bilan kontent tavsiya qilma, ro'yxat ko'rsatma "
    "va katalog funksiyalarini chaqirma.\n\n"

    "1. UMUMIY SAVOLLAR VA SUHBAT:\n"
    "- Salomlashish, oddiy suhbat, bilimga oid savollar, tushuntirishlar, "
    "fikrlar, tarjima, maslahat va boshqa mavzulardagi savollarga "
    "bevosita javob ber.\n"
    "- Anime haqidagi savol har doim anime tavsiyasi so'rovi degani emas. "
    "Masalan, «Narutoda asosiy maqsad nima?» deb so'ralsa, Naruto "
    "asaridagi asosiy maqsadni tushuntir. Bunda boshqa animelarni "
    "tavsiya qilma va katalogdan ro'yxat chiqarma.\n"
    "- «Naruto nima haqida?», «Luffyning maqsadi nima?» yoki "
    "«Attack on Titan oxiri nimani anglatadi?» kabi savollarga "
    "asar mazmuni, qahramonlar yoki voqealar haqida javob ber.\n"
    "- Bunday savollarga javob berish uchun katalogdan qidirish shart "
    "emas. O'z bilimlaringdan foydalan. Agar aniq ma'lumotga ishonching "
    "komil bo'lmasa, buni ochiq ayt va faktlarni to'qib chiqarma.\n"
    "- Foydalanuvchi shunchaki anime nomini tilga olgani uchun unga "
    "o'xshash animelarni taklif qilma.\n\n"

    "2. QACHON KATALOGDAN ANIME YOKI BOSHQA KONTENT QIDIRISH KERAK:\n"
    "Faqat foydalanuvchi kontentni topishni, ko'rishni, ro'yxatini "
    "olishni yoki tavsiya qilishni so'raganda katalog funksiyalaridan "
    "foydalan.\n"
    "Bunga quyidagilar kiradi:\n"
    "- «Menga Naruto kabi animelarni ayt».\n"
    "- «Yaxshi animelarni tavsiya qil».\n"
    "- «Anime ro'yxatini ko'rsat».\n"
    "- «Yangi chiqqan animelar qaysilar?».\n"
    "- «O'zbek tilidagi seriallarni top».\n"
    "- «Shu animening qismlarini ko'rsat».\n"
    "- «Katalogdan fantastik janrdagi kinolarni top».\n"
    "Bu holatlarda so'rovga mos funksiyani chaqir va faqat u qaytargan "
    "ma'lumotlarga asoslanib javob ber.\n\n"

    "3. ANIME HAQIDA SAVOL VA ANIME TAVSIYASI O'RTASIDAGI FARQ:\n"
    "Quyidagi ikki holatni qat'iy farqla:\n"
    "Foydalanuvchi: «Salom, Narutoda asosiy maqsad nima?»\n"
    "Javob: Naruto o'z qishlog'ida tan olinishni, Hokage bo'lishni "
    "va do'stlarini himoya qilishni maqsad qiladi. Savolga mos ravishda "
    "batafsilroq tushuntir, ammo boshqa animelarni tavsiya qilma.\n\n"
    "Foydalanuvchi: «Salom, menga Narutoga o'xshash animelarni ayt».\n"
    "Javob: Avval katalogdan Naruto uslubiga mos animelarni qidir. "
    "So'ng «Mana, siz so'ragan animelar:» deb, topilgan animelar "
    "ro'yxatini ko'rsat.\n\n"

    "4. KATALOG FUNKSIYALARIDAN FOYDALANISH:\n"
    "- Har bir kontent qidiruvi so'rovga mos bo'lsin. Kontent nomi, "
    "ma'lumotlari, qismlari, janrlari, mashhur yoki yangi kontent "
    "va katalog statistikasi uchun tegishli funksiyalardan foydalan.\n"
    "- Birinchi qidiruv natija bermasa, boshqa sinonim, ruscha yoki "
    "inglizcha nom bilan yana bir marta urinib ko'r.\n"
    "- Qayta qidirish ham natija bermasa, kontent katalogda "
    "topilmaganini ayt.\n"
    "- Katalog qaytarmagan kontent nomi, qism soni, chiqish yili, "
    "reyting yoki boshqa ma'lumotlarni o'ylab topma.\n"
    "- Umumiy bilim bilan javob berish mumkin bo'lgan savol uchun "
    "katalog funksiyalarini keraksiz chaqirma.\n"
    "- Foydalanuvchi aniq ro'yxat so'rasa, javobda topilgan kontent "
    "nomlarini aynan katalogda ko'rsatilgan shaklda yoz.\n"
    "- Foydalanuvchi faqat bitta kontent haqida ma'lumot so'rasa, "
    "butun katalog ro'yxatini ko'rsatma.\n\n"

    "5. SHAXSIY TAVSIYALAR:\n"
    "Agar foydalanuvchi «Menga mos anime top», «Sevimlilarimga "
    "o'xshashlarini tavsiya qil» yoki shunga o'xshash shaxsiy "
    "tavsiya so'rasa va personal_taste funksiyasi mavjud bo'lsa, "
    "undan foydalan. Tavsiyalarni mavjud foydalanuvchi ma'lumotlariga "
    "asosla. Bunday ma'lumotlar mavjud bo'lmasa, ularni bor deb ko'rsatma.\n\n"

    "6. O'ZINGNI TANISHTIRISH:\n"
    "- Sen AniVoy nomli AI yordamchisisan.\n"
    "- «Sen kimsan?» deb so'ralsa, «Men AniVoy, AniChopar "
    "platformasining AI yordamchisiman» deb javob ber.\n"
    "- O'zingni inson deb ko'rsatma va mavjud bo'lmagan imkoniyatlaring "
    "borligini da'vo qilma.\n"
    "- «Botmisan?» deb so'ralsa, AI yordamchisi ekaningni rost ayt.\n\n"

    "7. JAVOB USLUBI:\n"
    "- Foydalanuvchiga o'zbek tilida, tabiiy, samimiy va tushunarli "
    "tarzda javob ber. Boshqa til so'ralsa, o'sha tildan foydalan.\n"
    "- Oddiy savollarga qisqa va aniq javob ber. Murakkab savollarga "
    "kerakli darajada batafsil tushuntirish ber.\n"
    "- Anime yoki boshqa kontent ro'yxatini faqat foydalanuvchi "
    "shuni so'raganda ko'rsat.\n"
    "- Keraksiz tavsiyalar, ortiqcha uzrlar va mavzudan chetga "
    "chiqadigan gaplardan qoch.\n"
    "- Har doim foydalanuvchining oxirgi xabari va asl niyatiga "
    "ustuvorlik ber.\n"
    "- Javobni yengil markdown bilan tartibla: muhim so'zlar uchun "
    "**qalin**, ro'yxat uchun «- » bilan boshlanadigan qatorlar, "
    "sarlavhalar uchun «### ». Jadval, HTML teglari va ortiqcha "
    "bezaklardan foydalanma."
)


SUPPORT_SYSTEM_PROMPT = (
    "Sen AniVoy — AniChopar platformasining texnik yordamchisisan. "
    "Foydalanuvchi «Adminga xabar» bo'limida sayt, ilova, obuna, to'lov yoki "
    "akkount bo'yicha muammo bilan murojaat qiladi. O'zingni bot deb "
    "atamaysan.\n\n"
    "Vazifang: muammoni hal qilishga yordam berish.\n"
    "* Muammoni bir jumla bilan takrorla.\n"
    "* Tartiblangan ko'rsatmalar ber — har bir qadam alohida qator (nima "
    "bosish, nima tekshirish).\n"
    "* Maslahat ber — bunday holat qaytamasligi uchun nima qilish kerak.\n"
    "* Kontent haqida savol bo'lsa, berilgan funksiyalar bilan katalogdan "
    "aniqlab javob ber; ma'lumot bo'lmasa taxmin qilma.\n"
    "* Ko'p uchraydigan muammolar (parolni unutish, to'lov tasdiqlanmasligi, "
    "video ochilmasligi, ilova sekinligi, bildirishnoma kelmasligi) avval "
    "o'z holida tuzatish yo'llari bilan javob ber; ular ishlamasa, xabarni "
    "administratorga yuborishni taklif qil.\n"
    "* Javob o'zbekcha, qat'iy, ishonchli va qisqa bo'lsin.\n"
    "* Qadamlarni markdown ro'yxati sifatida yoz («1. » yoki «- »), "
    "muhim joylarni **qalin** qil; HTML teglarini ishlatma."
)


# --------------------------------------------------------------------------- #
# The answer
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AssistantAnswer:
    """One complete assistant answer.

    ``titles`` are the catalogue rows the tools returned (the clients render
    them as links); ``answer`` is the model's prose. ``used_llm`` is false when
    no provider answered — the clients then report the assistant unavailable,
    because there is no offline fallback any more. ``conversational`` means the
    question was not a catalogue lookup, so no result list belongs under it.
    """

    query: str
    titles: Tuple[MediaTitle, ...] = ()
    answer: str = ""
    used_llm: bool = False
    conversational: bool = False
    tools: Tuple[str, ...] = ()
    error: str = ""


_CACHE: Dict[Tuple[Any, ...], Tuple[float, AssistantAnswer]] = {}
_CACHE_LOCK = threading.Lock()


def _cache_key(
    query: str,
    limit: Optional[int],
    media_type: str,
    support: bool,
    personal_context: str,
    history: Sequence[Mapping[str, Any]],
) -> Tuple[Any, ...]:
    return (
        clean_text(query).lower(),
        int(limit or MAX_RESULTS),
        media_type,
        bool(support),
        clean_text(personal_context),
        tuple((str(item.get("role") or ""), str(item.get("text") or "")) for item in history),
        # A different chain may answer differently: never mix their answers.
        llm.chain_signature(),
    )


def _cache_get(key: Tuple[Any, ...]) -> Optional[AssistantAnswer]:
    now = time.monotonic()
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if entry is None:
            return None
        stored_at, result = entry
        if now - stored_at > CACHE_TTL_SECONDS:
            _CACHE.pop(key, None)
            return None
        return result


def _cache_put(key: Tuple[Any, ...], result: AssistantAnswer) -> None:
    with _CACHE_LOCK:
        if len(_CACHE) >= CACHE_MAX_ENTRIES:
            oldest = sorted(_CACHE.items(), key=lambda item: item[1][0])
            for stale_key, _ in oldest[: max(1, CACHE_MAX_ENTRIES // 2)]:
                _CACHE.pop(stale_key, None)
        _CACHE[key] = (time.monotonic(), result)


def clear_cache() -> None:
    """Drop every cached answer (tests, or an operator's manual reset)."""
    with _CACHE_LOCK:
        _CACHE.clear()


def _assistant_message(result: llm.ChatResult) -> Dict[str, Any]:
    """The assistant turn that carries the tool calls back to the provider.

    A call's ``extra`` metadata rides along untouched: Gemini 3 puts the
    ``thought_signature`` there and refuses the follow-up round without it,
    while other providers send none and keep exactly the classic shape.
    """
    calls = []
    for call in result.tool_calls:
        entry: Dict[str, Any] = {
            "id": call.id,
            "type": "function",
            "function": {"name": call.name, "arguments": call.arguments or "{}"},
        }
        if call.extra:
            entry["extra_content"] = call.extra
        calls.append(entry)
    return {
        "role": "assistant",
        "content": result.content or "",
        "tool_calls": calls,
    }


def answer(
    query: str,
    *,
    limit: Optional[int] = None,
    media_type: str = "",
    history: Sequence[Mapping[str, Any]] = (),
    support: bool = False,
    personal_context: str = "",
) -> AssistantAnswer:
    """Ask the assistant: it calls the tools it needs, then writes the answer.

    ``media_type`` narrows the catalogue the tools may use (the website's type
    filter). ``history`` is the last few ``{"role", "text"}`` turns, so
    "oldingisiga o'xshashini top" still means something. ``personal_context``
    (favourites + last watched) is only passed by callers when the user opted
    in, and it is also what enables the ``personal_taste`` tool.
    """
    text = clean_text(query)
    if not text:
        return AssistantAnswer(query=query)

    cache_key = _cache_key(
        text,
        limit,
        media_type,
        support,
        personal_context,
        list(history or []),
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    if not llm.is_configured():
        return AssistantAnswer(query=query, error=llm.no_provider_message())

    runner = _ToolRunner(personal_context=personal_context)
    media_note = ""
    if media_type:
        media_note = f"\n\nFaol filtr: faqat {media_type} turidagi kontent kerak."
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SUPPORT_SYSTEM_PROMPT if support else SYSTEM_PROMPT}
    ]
    messages.extend(format_history(history))
    messages.append({"role": "user", "content": text + media_note})

    tools = runner.schemas()
    used_llm = False
    answer_text = ""
    try:
        for round_number in range(MAX_TOOL_ROUNDS + 1):
            final_round = round_number == MAX_TOOL_ROUNDS
            result = llm.chat_completion(
                messages,
                max_tokens=MAX_ANSWER_TOKENS,
                tools=None if final_round else tools,
                tool_choice="auto",
            )
            used_llm = used_llm or bool(result.content or result.tool_calls)
            if result.tool_calls and not final_round:
                messages.append(_assistant_message(result))
                for call in result.tool_calls:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "name": call.name,
                            "content": runner.run(call.name, call.arguments),
                        }
                    )
                continue
            answer_text = (result.content or "").strip()
            break
    except llm.LLMUnavailable as exc:
        logger.info("AI assistant could not answer: %s", exc)
        return AssistantAnswer(
            query=query,
            titles=runner.titles(limit=limit or MAX_RESULTS),
            used_llm=False,
            tools=tuple(runner.used),
            error=str(exc),
        )
    except Exception as exc:  # noqa: BLE001 - the caller must get a reason
        logger.exception("AI assistant failed")
        return AssistantAnswer(
            query=query,
            titles=runner.titles(limit=limit or MAX_RESULTS),
            used_llm=False,
            tools=tuple(runner.used),
            error=str(exc),
        )

    titles = runner.titles(limit=limit or MAX_RESULTS)
    result = AssistantAnswer(
        query=query,
        titles=titles,
        answer=answer_text,
        used_llm=bool(answer_text),
        # No tool was called and there is no list: the model treated the
        # request as a conversation, so clients show the words alone.
        conversational=bool(answer_text) and not runner.used and not titles,
        tools=tuple(dict.fromkeys(runner.used)),
    )
    if result.used_llm:
        _cache_put(cache_key, result)
    return result
