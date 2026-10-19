# Copy every stored cover blob onto disk as a media file.
#
# Forward: `cover_blob` (base64-ish bytes in the database) -> `covers/<slug>.*`
# on the media volume, which nginx serves directly. Backwards: read the file
# back into the blob column and delete it, so a rollback keeps the covers.
#
# Production held base64 *text* in that column (the panel posted base64 and the
# API round-tripped it), while the import command wrote raw image bytes, so the
# payload is sniffed: base64 text is decoded before the file is written,
# anything that already is an image is stored as-is. `fix_covers` re-runs the
# same repair for rows an interrupted migration left behind.

import base64

from django.core.files.base import ContentFile
from django.db import migrations


def _extension(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return "jpg"


def _looks_like_image(data: bytes) -> bool:
    return (
        data[:8] == b"\x89PNG\r\n\x1a\n"
        or data[:3] == b"\xff\xd8\xff"
        or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")
        or data[:6] in (b"GIF87a", b"GIF89a")
    )


def _decode_payload(value) -> bytes:
    """Image bytes for one stored blob, whatever shape it was written in."""
    if value is None:
        return b""
    if isinstance(value, str):
        data = value.encode("latin-1", "ignore")
    elif isinstance(value, memoryview):
        data = value.tobytes()
    else:
        data = bytes(value)
    if not data or _looks_like_image(data):
        return data
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        return data
    payload = text.strip()
    if payload.startswith("data:"):
        payload = payload.split(",", 1)[1] if "," in payload else ""
    payload = "".join(payload.split())
    payload += "=" * (-len(payload) % 4)
    try:
        decoded = base64.b64decode(payload, validate=True)
    except Exception:  # noqa: BLE001 - a payload that is not base64 stays untouched
        return data
    return decoded if _looks_like_image(decoded) else data


def blobs_to_files(apps, schema_editor):
    MediaTitle = apps.get_model("movies", "MediaTitle")
    database = schema_editor.connection.alias
    for title in MediaTitle.objects.using(database).iterator(chunk_size=100):
        blob = title.cover_blob
        if not blob:
            continue
        data = _decode_payload(blob)
        name = f"{title.slug or title.pk}.{_extension(data)}"
        # save() applies upload_to ("covers/") and de-duplicates the filename,
        # so a replaced cover always ends up at a new URL the browser has not
        # cached yet.
        title.cover.save(name, ContentFile(data), save=False)
        title.save(update_fields=["cover"])


def files_to_blobs(apps, schema_editor):
    MediaTitle = apps.get_model("movies", "MediaTitle")
    database = schema_editor.connection.alias
    for title in MediaTitle.objects.using(database).iterator(chunk_size=100):
        cover = title.cover
        if not cover:
            continue
        try:
            cover.open("rb")
            try:
                data = cover.read()
            finally:
                cover.close()
        except OSError:
            continue
        title.cover_blob = data
        title.save(update_fields=["cover_blob"])
        cover.delete(save=False)


class Migration(migrations.Migration):

    dependencies = [
        ('movies', '0018_cover_moves_to_media_files'),
    ]

    operations = [
        migrations.RunPython(blobs_to_files, files_to_blobs),
    ]
