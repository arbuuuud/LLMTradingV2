"""Data ingestion, canonical adapter, and hybrid data lake merger."""

from src.data.adapter import BrokerSpec, BrokerAdapter
from src.data.merger import HybridDataLake

__all__ = ["BrokerSpec", "BrokerAdapter", "HybridDataLake"]
