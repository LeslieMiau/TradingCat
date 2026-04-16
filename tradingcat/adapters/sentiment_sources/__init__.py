"""Adapters that fetch sentiment indicators from external sources.

Each source lives in its own module so failure modes (rate limits, schema
drift, regional IP blocks) stay isolated. The shared `SentimentHttpClient`
from `tradingcat/adapters/sentiment_http.py` carries retries/TTL; these
modules are concerned only with URL/field mapping.
"""
