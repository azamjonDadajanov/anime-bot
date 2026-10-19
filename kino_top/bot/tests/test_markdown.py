"""``bot.markdown``: the model's markdown becomes a whitelisted Telegram HTML.

The point of these tests is not pretty-printing: it is that everything the
model writes is escaped, and only the tags Telegram documents are ever rebuilt.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from ..markdown import to_telegram_html
from ..utils import escape_html


class TelegramMarkdownTests(SimpleTestCase):
	def test_bold_and_italic_become_tags(self) -> None:
		self.assertEqual(
			to_telegram_html("**Mana tavsiyalar:** *Naruto* yaxshi"),
			"<b>Mana tavsiyalar:</b> <i>Naruto</i> yaxshi",
		)
		self.assertEqual(to_telegram_html("__qalin__ va _kursiv_"), "<b>qalin</b> va <i>kursiv</i>")

	def test_a_bullet_line_gets_a_marker_instead_of_an_asterisk(self) -> None:
		self.assertEqual(
			to_telegram_html("- Birinchi\n- **Ikkinchi**"),
			"• Birinchi\n• <b>Ikkinchi</b>",
		)

	def test_ordered_lists_keep_their_numbers(self) -> None:
		self.assertEqual(
			to_telegram_html("1. Birinchi\n2. Ikkinchi"),
			"1. Birinchi\n2. Ikkinchi",
		)

	def test_a_heading_is_a_bold_line(self) -> None:
		self.assertEqual(to_telegram_html("### Sarlavha"), "<b>Sarlavha</b>")

	def test_strikethrough_and_inline_code(self) -> None:
		self.assertEqual(
			to_telegram_html("~~eski~~ va `kod`"),
			"<s>eski</s> va <code>kod</code>",
		)

	def test_a_safe_link_becomes_an_anchor(self) -> None:
		self.assertEqual(
			to_telegram_html("[Naruto](https://anichopar.uz/media/naruto?x=1&y=2)"),
			'<a href="https://anichopar.uz/media/naruto?x=1&amp;y=2">Naruto</a>',
		)

	def test_an_unsafe_link_keeps_only_its_label(self) -> None:
		self.assertEqual(to_telegram_html("[bos](javascript:alert(1))"), "bos")
		self.assertEqual(to_telegram_html("[bos](data:text/html,x)"), "bos")

	def test_model_written_html_is_escaped_not_rendered(self) -> None:
		self.assertEqual(
			to_telegram_html("<script>alert(1)</script> & <b>soxta</b>"),
			"&lt;script&gt;alert(1)&lt;/script&gt; &amp; &lt;b&gt;soxta&lt;/b&gt;",
		)

	def test_a_fenced_block_is_pre_and_still_escaped(self) -> None:
		self.assertEqual(
			to_telegram_html("```python\nprint(1 < 2)\n```"),
			"<pre>print(1 &lt; 2)</pre>",
		)

	def test_an_unterminated_fence_is_not_swallowed(self) -> None:
		self.assertEqual(
			to_telegram_html("```\nprint(1)"),
			"<pre>print(1)</pre>",
		)

	def test_apostrophes_are_escaped_like_the_rest_of_the_bot(self) -> None:
		# The assistant speaks Uzbek, so this happens in almost every answer.
		self.assertEqual(
			to_telegram_html("qo'rqinchli"),
			escape_html("qo'rqinchli"),
		)

	def test_blank_input_stays_blank(self) -> None:
		self.assertEqual(to_telegram_html(""), "")
		self.assertEqual(to_telegram_html(None), "")

	def test_only_whitelisted_tags_are_produced(self) -> None:
		answer = (
			"# Reja\n"
			"**Bugun** *yaxshi* ~~kechagi~~ `kod`\n"
			"> iqtibos\n"
			"- [havola](https://anichopar.uz)\n"
			"```\nkod\n```\n"
			"---"
		)
		rendered = to_telegram_html(answer)
		for tag in ("<b>", "<i>", "<s>", "<code>", "<pre>", "<blockquote>", "<a href="):
			self.assertIn(tag, rendered)
		# Nothing outside the allowed set survives, escaped or not.
		self.assertNotIn("<script", rendered)
		self.assertNotIn("<div", rendered)
		self.assertNotIn("&lt;", rendered)
