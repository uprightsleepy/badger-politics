"""Static data products generated from SQLite at build time.

Everything here is provenance-filtered: rows with source='legiscan' are
display-only and never leave the database (hard rule). The static JSON API,
feeds, calendars, and bulk exports all go through queries.py, which bakes
the filter in.
"""
