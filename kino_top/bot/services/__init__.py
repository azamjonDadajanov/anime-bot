"""Reusable service layer shared by user handlers and the admin panel.

Handlers stay thin: they validate input, call one of these functions and render
the result. Every database access is wrapped with :func:`bot.utils.to_async` so
handlers never block the event loop.
"""
