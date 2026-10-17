"""Multilingual sentence embeddings behind the AI catalogue search.

The vector space is the one of
``sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`` — a 384
dimensional sentence encoder trained on 50+ languages. That multilingual
behaviour is the whole point of the feature: an Uzbek request such as
"menga sarguzasht va qo'rqinchli animelar ayt" has to land on the right titles
even though the catalogue stores Russian/English titles and no English word of
the query appears in the index.

The *official ONNX export* of that very model is executed through
``onnxruntime`` instead of PyTorch. The deployment serves Django behind gunicorn
on a small CPU box; the ONNX path needs neither torch nor transformers, pulls no
CUDA libraries and keeps both the image and the memory footprint small, while
producing the same vectors. Pooling follows the model card exactly — the mean of
the token vectors weighted by the attention mask, then L2 normalisation — so the
vectors match the reference implementation.

This module only turns text into vectors; ``movies.ai_search`` owns the index,
the documents and the search itself.
"""

from __future__ import annotations

import logging
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from django.conf import settings

logger = logging.getLogger(__name__)

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DOWNLOAD_BASE_URL = f"https://huggingface.co/{MODEL_NAME}/resolve/main/"
DEFAULT_MODEL_FILE = "onnx/model.onnx"
# The graph alone is not enough: the tokenizer and the small configs shipped
# next to it are what make the ONNX runtime produce sentence-transformers
# compatible vectors.
SIDECAR_FILES = (
    "tokenizer.json",
    "config.json",
    "special_tokens_map.json",
    "1_Pooling/config.json",
    "sentence_bert_config.json",
)
EMBEDDING_DIM = 384
# ``sentence_bert_config.json`` of this model caps a sentence at 128 tokens.
MAX_TOKENS = 128
DEFAULT_BATCH_SIZE = 16
_CHUNK_SIZE = 1 << 20

ProgressCallback = Optional[Callable[[str, int, int], None]]


class EmbeddingUnavailable(RuntimeError):
	"""Raised when the encoder cannot be used at all.

	Covers both a missing model download and a deployment without the
	``onnxruntime``/``tokenizers`` packages. Callers treat it as "the AI search
	is not configured right now" and say so instead of failing the request.
	"""


def model_dir() -> Path:
	"""Directory that holds the model files (``AI_MODEL_DIR``)."""
	configured = str(getattr(settings, "AI_MODEL_DIR", "") or "").strip()
	if configured:
		return Path(configured)
	return Path(settings.BASE_DIR) / "ai_models"


def model_file() -> str:
	"""Relative path of the graph inside :func:`model_dir` (``AI_MODEL_FILE``)."""
	return str(getattr(settings, "AI_MODEL_FILE", "") or DEFAULT_MODEL_FILE).strip()


def model_path() -> Path:
	return model_dir() / model_file()


def required_files() -> List[str]:
	"""Every file the encoder needs, as paths relative to :func:`model_dir`."""
	return [model_file(), *SIDECAR_FILES]


def missing_files() -> List[str]:
	"""Requirements that are absent (or empty) on disk."""
	root = model_dir()
	missing = []
	for name in required_files():
		path = root / name
		try:
			if not path.is_file() or path.stat().st_size == 0:
				missing.append(name)
		except OSError:  # pragma: no cover - unreadable directory
			missing.append(name)
	return missing


def is_ready() -> bool:
	"""True when every model file is already on disk."""
	return not missing_files()


def download_model(
	*, force: bool = False, on_progress: ProgressCallback = None, retries: int = 3
) -> List[str]:
	"""Fetch the ONNX graph, tokenizer and configs into :func:`model_dir`.

	The graph is ~470MB, so the download is written to ``<name>.part`` and moved
	into place only when it is complete: an interrupted run keeps its progress
	and the next one continues from the byte it stopped at (HTTP ``Range``),
	instead of starting over or leaving a truncated model that onnxruntime would
	reject.

	Files that already exist are skipped unless ``force`` is set. Returns the
	paths that ended up on disk in this run.
	"""
	downloaded: List[str] = []
	for name in required_files():
		destination = model_dir() / name
		if not force and destination.is_file() and destination.stat().st_size > 0:
			continue
		destination.parent.mkdir(parents=True, exist_ok=True)
		partial = destination.with_name(destination.name + ".part")
		last_error: Optional[Exception] = None
		for attempt in range(1, max(1, retries) + 1):
			try:
				_download_file(name, destination, partial, on_progress=on_progress)
			except (urllib.error.URLError, OSError, ValueError) as exc:
				last_error = exc
				logger.warning(
					"Model download of %s failed (attempt %s/%s): %s",
					name,
					attempt,
					retries,
					exc,
				)
				continue
			last_error = None
			break
		if last_error is not None:
			raise EmbeddingUnavailable(
				f"{name} yuklanmadi: {last_error}. Internetni tekshirib, buyruqni "
				"qaytadan ishga tushiring — yuklangan qism saqlanadi."
			) from last_error
		downloaded.append(str(destination))
	return downloaded


def _download_file(
	name: str,
	destination: Path,
	partial: Path,
	*,
	on_progress: ProgressCallback = None,
) -> None:
	"""Stream one file, resuming a previous partial download when there is one."""
	url = DOWNLOAD_BASE_URL + name
	resume_from = partial.stat().st_size if partial.is_file() else 0
	headers = {"Range": f"bytes={resume_from}-"} if resume_from else {}
	request = urllib.request.Request(url, headers=headers)
	with urllib.request.urlopen(request, timeout=60) as response:
		# A server that ignores ``Range`` answers 200 with the whole file, which
		# must overwrite the partial one instead of appending to it.
		appending = resume_from > 0 and response.status == 206
		total = int(response.headers.get("Content-Length") or 0) + (resume_from if appending else 0)
		done = resume_from if appending else 0
		with partial.open("ab" if appending else "wb") as handle:
			while True:
				chunk = response.read(_CHUNK_SIZE)
				if not chunk:
					break
				handle.write(chunk)
				done += len(chunk)
				if on_progress is not None:
					on_progress(name, done, total)
	if total and done < total:
		raise ValueError(f"{name}: {done}/{total} bayt yuklandi (ulanish uzildi).")
	partial.replace(destination)


@dataclass
class TextEncoder:
	"""A loaded ONNX sentence encoder (built by :func:`load_encoder`)."""

	model_name: str
	model_path: str
	tokenizer: object
	session: object
	input_names: frozenset = field(default_factory=frozenset)

	def encode(
		self, texts: Sequence[str], *, batch_size: int = DEFAULT_BATCH_SIZE
	) -> List[List[float]]:
		"""Embed ``texts`` into L2-normalised :data:`EMBEDDING_DIM` vectors."""
		import numpy as np

		vectors: List[List[float]] = []
		batch_size = max(1, int(batch_size or DEFAULT_BATCH_SIZE))
		for start in range(0, len(texts), batch_size):
			batch = [str(text or "") for text in texts[start : start + batch_size]]
			encodings = self.tokenizer.encode_batch(batch)
			# ``enable_padding`` pads every sequence of the batch to the longest
			# one, which is what makes the arrays rectangular here.
			input_ids = np.asarray([item.ids for item in encodings], dtype=np.int64)
			attention = np.asarray(
				[item.attention_mask for item in encodings], dtype=np.int64
			)
			feed = {"input_ids": input_ids, "attention_mask": attention}
			if "token_type_ids" in self.input_names:
				feed["token_type_ids"] = np.zeros_like(input_ids)
			outputs = self.session.run(None, feed)
			# Mean pooling over the tokens the attention mask keeps, then
			# normalise: the recipe from the model card.
			hidden = np.asarray(outputs[0], dtype=np.float32)
			weights = attention[..., None].astype(np.float32)
			summed = (hidden * weights).sum(axis=1)
			counts = np.clip(weights.sum(axis=1), 1e-9, None)
			pooled = summed / counts
			norms = np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12, None)
			vectors.extend((pooled / norms).tolist())
		return vectors


_ENCODER: Optional[TextEncoder] = None
_LOCK = threading.Lock()


def load_encoder(*, refresh: bool = False) -> TextEncoder:
	"""Return the process-wide encoder, loading it on first use.

	Raises :class:`EmbeddingUnavailable` when the model has not been downloaded
	or the runtime packages are missing, so callers can degrade gracefully.
	"""
	global _ENCODER
	if _ENCODER is not None and not refresh:
		return _ENCODER
	with _LOCK:
		if _ENCODER is not None and not refresh:
			return _ENCODER
		_ENCODER = _build_encoder()
		return _ENCODER


def reset_encoder_cache() -> None:
	"""Drop the loaded encoder (tests, or after a fresh download)."""
	global _ENCODER
	with _LOCK:
		_ENCODER = None


def _build_encoder() -> TextEncoder:
	missing = missing_files()
	if missing:
		raise EmbeddingUnavailable(
			"Model fayllari topilmadi: "
			+ ", ".join(missing)
			+ ". `python manage.py index_anime_embeddings --download-model` "
			"buyrug'ini bajaring."
		)
	try:
		import onnxruntime
		from tokenizers import Tokenizer
	except ImportError as exc:  # pragma: no cover - depends on deployment
		raise EmbeddingUnavailable(
			"onnxruntime/tokenizers o'rnatilmagan: " + str(exc)
		) from exc

	tokenizer = Tokenizer.from_file(str(model_dir() / "tokenizer.json"))
	tokenizer.enable_truncation(max_length=MAX_TOKENS, strategy="longest_first")
	pad_token_id = tokenizer.token_to_id("<pad>")
	tokenizer.enable_padding(pad_id=1 if pad_token_id is None else pad_token_id)

	options = onnxruntime.SessionOptions()
	# One embedding request is a tiny batch; extra threads only add contention
	# with the web workers.
	options.intra_op_num_threads = max(1, min(4, (getattr(settings, "AI_MODEL_THREADS", 4) or 4)))
	options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
	session = onnxruntime.InferenceSession(
		str(model_path()), sess_options=options, providers=["CPUExecutionProvider"]
	)
	encoder = TextEncoder(
		model_name=MODEL_NAME,
		model_path=str(model_path()),
		tokenizer=tokenizer,
		session=session,
		input_names=frozenset(item.name for item in session.get_inputs()),
	)
	logger.info(
		"AI embeddings ready: %s (%s), inputs=%s",
		MODEL_NAME,
		model_file(),
		", ".join(sorted(encoder.input_names)),
	)
	return encoder


def encode_texts(
	texts: Sequence[str], *, batch_size: int = DEFAULT_BATCH_SIZE
) -> List[List[float]]:
	"""Embed ``texts`` with the shared encoder (raises :class:`EmbeddingUnavailable`)."""
	if not texts:
		return []
	return load_encoder().encode(texts, batch_size=batch_size)
