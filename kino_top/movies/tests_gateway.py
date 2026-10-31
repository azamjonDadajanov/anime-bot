"""``movies.gateway`` — the assistant's model calls routed through Respan Gateway.

The gateway runs **inside this process**, so these tests talk to nothing but a
local fixture: a tiny OpenAI-compatible HTTP server on loopback that answers and
records what actually arrived. A provider row of kind ``gateway`` goes into the
chain, the real request building and failover run, and the fixture is then the
witness — which is the only way to tell "the assistant's call went through the
gateway" from "the assistant answered without one".

No provider key is used here and no request leaves the machine: the gateway's
own provider is this fixture (or, in the file case, a ``gateway.toml`` that
points at it), exactly as a developer would run it before pointing it at a real
vendor.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase, override_settings

from . import ai_assistant, gateway, llm
from .models import AIProvider, MediaTitle


def completion(text: str = "fixture javob", *, tool: str = "") -> dict:
	"""One OpenAI-shaped completion body, with an optional function call."""
	message = {"role": "assistant", "content": text}
	if tool:
		message["tool_calls"] = [
			{
				"id": "call_fixture",
				"type": "function",
				"function": {"name": tool, "arguments": json.dumps({"matn": "anime"})},
			}
		]
	return {
		"id": "chatcmpl-fixture",
		"object": "chat.completion",
		"created": 0,
		"model": "fixture",
		"choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
	}


def sequence(answers: list):
	"""A fixture program: one answer per request, the last one repeated."""
	pending = list(answers)

	def answer(payload):
		return pending.pop(0) if len(pending) > 1 else pending[0]

	return answer


class _ProviderHandler(BaseHTTPRequestHandler):
	"""The fixture's HTTP side: record the request, answer with its program."""

	def do_POST(self) -> None:
		length = int(self.headers.get("Content-Length") or 0)
		raw = self.rfile.read(length)
		try:
			payload = json.loads(raw.decode("utf-8") or "{}")
		except ValueError:
			payload = {}
		self.server.payloads.append(payload)
		self.server.authorization = self.headers.get("Authorization") or ""
		status, body, headers = self.server.answer(payload)
		encoded = json.dumps(body).encode("utf-8")
		self.send_response(status)
		self.send_header("Content-Type", "application/json")
		for name, value in (headers or {}).items():
			self.send_header(name, value)
		self.send_header("Content-Length", str(len(encoded)))
		self.end_headers()
		self.wfile.write(encoded)

	def log_message(self, *args) -> None:  # noqa: D102 - the fixture is silent
		pass


class FixtureProvider(ThreadingHTTPServer):
	"""A local stand-in for a provider: ``answer`` decides what it returns."""

	def __init__(self) -> None:
		super().__init__(("127.0.0.1", 0), _ProviderHandler)
		self.payloads = []
		self.authorization = ""
		self.answer = lambda payload: (200, completion(), {})
		self._thread = threading.Thread(target=self.serve_forever, daemon=True)

	def start(self) -> "FixtureProvider":
		self._thread.start()
		return self

	@property
	def base_url(self) -> str:
		host, port = self.server_address[:2]
		return f"http://{host}:{port}/v1"


class GatewayTestCase(TestCase):
	def setUp(self):
		super().setUp()
		self.fixture = FixtureProvider().start()
		# Ordered so the fixture outlives the gateway's last request.
		self.addCleanup(self.fixture.server_close)
		self.addCleanup(self.fixture.shutdown)
		# The gateway and every cooldown are process-wide: a leftover would make
		# the next test route somewhere else or skip the row being tested.
		gateway.reset()
		self.addCleanup(gateway.reset)
		llm.reset_cooldowns()
		llm.reset_signature_cache()
		ai_assistant.clear_cache()
		self.addCleanup(llm.reset_cooldowns)
		self.addCleanup(llm.reset_signature_cache)
		self.addCleanup(ai_assistant.clear_cache)

	def use_env_provider(self, *, model: str = "fixture-upstream") -> None:
		"""Point ``AI_LLM_*`` — the gateway's own provider — at the fixture."""
		override = override_settings(
			AI_LLM_ENABLED=True,
			AI_LLM_PROVIDER="custom",
			AI_LLM_API_KEY="fixture-key",
			AI_LLM_MODEL=model,
			AI_LLM_BASE_URL=self.fixture.base_url,
			AI_GATEWAY_CONFIG="",
		)
		override.enable()
		self.addCleanup(override.disable)

	def make_gateway_row(self, model: str = "anivoy", **extra) -> AIProvider:
		fields = dict(
			kind=AIProvider.Kind.GATEWAY,
			api_key="",
			model=model,
			base_url="",
			priority=1,
		)
		fields.update(extra)
		return AIProvider.objects.create(name="Respan Gateway", **fields)

	def gateway_config(self, model: str = "anivoy") -> llm.ProviderConfig:
		"""The chain entry the row produces, without going through the database."""
		return llm.ProviderConfig(
			name="Respan Gateway",
			kind=llm.GATEWAY_KIND,
			api_key="",
			model=model,
			base_url="",
		)


class GatewayRoutingTests(GatewayTestCase):
	def test_the_assistant_answers_through_the_gateway(self):
		"""The whole point: the app's own request reaches the model via the gateway.

		The row asks for its model (a route), the gateway forwards it to the
		provider configured for the deployment, and the answer comes back in
		the shape the assistant already parses.
		"""
		self.use_env_provider()
		row = self.make_gateway_row(model="anivoy")

		result = llm.chat_completion([{"role": "user", "content": "salom"}])

		self.assertEqual(result.content, "fixture javob")
		self.assertEqual(result.provider, row.name)
		self.assertEqual(len(self.fixture.payloads), 1)
		payload = self.fixture.payloads[0]
		# The model the row asked for, and the question itself.
		self.assertEqual(payload["model"], "anivoy")
		self.assertEqual(payload["messages"][-1]["content"], "salom")
		# The gateway reached the provider with the deployment's own key.
		self.assertEqual(self.fixture.authorization, "Bearer fixture-key")

	def test_the_catalogue_functions_travel_through_the_gateway(self):
		"""AniVoy is useless without tool calls: they must survive the hop."""
		self.use_env_provider()
		self.make_gateway_row()
		self.fixture.answer = lambda payload: (200, completion("", tool="search_catalog"), {})
		tools = [
			{
				"type": "function",
				"function": {"name": "search_catalog", "parameters": {}},
			}
		]

		result = llm.chat_completion(
			[{"role": "user", "content": "anime top"}], tools=tools
		)

		self.assertEqual(self.fixture.payloads[0]["tools"], tools)
		self.assertEqual(len(result.tool_calls), 1)
		self.assertEqual(result.tool_calls[0].name, "search_catalog")
		self.assertEqual(json.loads(result.tool_calls[0].arguments), {"matn": "anime"})

	def test_a_gateway_row_needs_no_key_of_its_own(self):
		"""The gateway holds the provider keys, so the row only names its model."""
		override = override_settings(AI_LLM_API_KEY="", AI_LLM_MODEL="", AI_GATEWAY_CONFIG="")
		override.enable()
		self.addCleanup(override.disable)
		self.make_gateway_row(model="anivoy")

		chain = llm.provider_chain()

		self.assertEqual([config.label for config in chain], ["Respan Gateway"])
		self.assertEqual(chain[0].kind, llm.GATEWAY_KIND)
		self.assertEqual(chain[0].api_key, "")

	def test_a_gateway_toml_decides_the_route(self):
		"""``AI_GATEWAY_CONFIG`` is the operator's own routing table."""
		with TemporaryDirectory() as folder:
			path = Path(folder) / "gateway.toml"
			path.write_text(
				"\n".join(
					(
						'log = "off"',
						"ui = false",
						"[providers.local]",
						'formats = ["openai-chat"]',
						f'base_url = "{self.fixture.base_url}"',
						'key = "toml-key"',
						'[routes."smart"]',
						'to = "local"',
					)
				),
				encoding="utf-8",
			)
			override = override_settings(AI_GATEWAY_CONFIG=str(path), AI_LLM_API_KEY="")
			override.enable()
			self.addCleanup(override.disable)
			self.make_gateway_row(model="smart")

			result = llm.chat_completion([{"role": "user", "content": "salom"}])

		self.assertEqual(result.content, "fixture javob")
		self.assertEqual(self.fixture.payloads[0]["model"], "smart")
		self.assertEqual(self.fixture.authorization, "Bearer toml-key")


class GatewayWorkflowTests(GatewayTestCase):
	def test_anivoy_answers_through_the_gateway(self):
		"""The whole assistant, end to end: a question, a function, an answer.

		``movies.ai_assistant`` builds the request and runs the tool it is
		asked for, ``movies.llm`` sends both rounds through the gateway, and
		the fixture plays the model — so this is the feature the user actually
		uses, not a mock of it.
		"""
		self.use_env_provider()
		self.make_gateway_row(model="anivoy")
		title = MediaTitle.objects.create(
			title="Anime Qorong'i O'rmon", synopsis="Qo'rqinchli o'rmondagi voqea."
		)
		self.fixture.answer = sequence(
			[
				(200, completion("", tool="search_catalog"), {}),
				(200, completion("Mana, topilgan anime."), {}),
			]
		)

		result = ai_assistant.answer("qo'rqinchli anime ayt")

		self.assertTrue(result.used_llm)
		self.assertEqual(result.answer, "Mana, topilgan anime.")
		self.assertEqual([item.pk for item in result.titles], [title.pk])
		self.assertIn("search_catalog", result.tools)
		# Two rounds, both through the gateway; the second one carried the
		# function's result back to the model.
		self.assertEqual(len(self.fixture.payloads), 2)
		self.assertEqual(self.fixture.payloads[0]["model"], "anivoy")
		self.assertTrue(
			any(item.get("role") == "tool" for item in self.fixture.payloads[1]["messages"])
		)


class GatewayFailureTests(GatewayTestCase):
	def test_a_limit_answer_becomes_the_chains_limit(self):
		"""One 429 through the gateway puts the row on cooldown, exactly as direct."""
		self.use_env_provider()
		self.fixture.answer = lambda payload: (
			429,
			{"error": {"message": "rate limit"}},
			{"Retry-After": "45"},
		)

		status, detail = llm.probe(self.gateway_config())

		self.assertEqual(status, "limit")
		self.assertIn("429", detail)

	def test_a_missing_configuration_is_reported_as_one(self):
		"""No provider key and no gateway.toml: the row is skipped, not retried.

		The message names the setting to fix, and nothing pretends a model was
		asked — no request reaches the fixture at all.
		"""
		override = override_settings(AI_LLM_API_KEY="", AI_GATEWAY_CONFIG="")
		override.enable()
		self.addCleanup(override.disable)

		status, detail = llm.probe(self.gateway_config())

		self.assertEqual(status, "model_topilmadi")
		self.assertIn("sozlanmagan", detail)
		self.assertEqual(self.fixture.payloads, [])
