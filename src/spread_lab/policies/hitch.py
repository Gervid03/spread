"""Idea 26 (Hitch): paired-gig dispatcher subclassing Desk."""
from __future__ import annotations

from ..policy import Desk as BaseDesk, Params as BaseParams


class Desk(BaseDesk):
    Params = BaseParams
