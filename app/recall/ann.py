from __future__ import annotations

import json
import os
from functools import cached_property
from pathlib import Path
from typing import Any


class AnnUnavailable(RuntimeError):
    """Raised when the configured ANN backend cannot be used."""


class AnnClient:
    """Small ANN client used by ItemSearch.

    The client intentionally keeps Milvus/Faiss imports lazy so local JSONL
    search still works in environments that do not have vector dependencies.
    """

    def __init__(self) -> None:
        self.backend = os.environ.get("ANN_BACKEND", "milvus").lower()
        self.index_path = os.environ.get("ANN_INDEX_PATH")
        self.collection_name = os.environ.get("MILVUS_COLLECTION", "products")
        self.vector_field = os.environ.get("MILVUS_VECTOR_FIELD", "embedding")

    def is_configured(self) -> bool:
        if self.backend == "faiss":
            return bool(self.index_path)
        if self.backend == "milvus":
            return True
        return False

    def search(
        self,
        emb: list[float],
        top_k: int,
        platform: str,
    ) -> list[dict[str, Any]]:
        """Search ANN backend and return product metadata rows."""
        if not emb:
            return []
        if self.backend == "faiss":
            return self._search_faiss(emb=emb, top_k=top_k, platform=platform)
        if self.backend == "milvus":
            return self._search_milvus(emb=emb, top_k=top_k, platform=platform)
        raise AnnUnavailable(f"Unsupported ANN_BACKEND: {self.backend}")

    @cached_property
    def _faiss_index(self) -> Any:
        if not self.index_path:
            raise AnnUnavailable("ANN_INDEX_PATH is not configured")
        try:
            import faiss  # type: ignore
        except ImportError as exc:
            raise AnnUnavailable("faiss is not installed") from exc

        path = Path(self.index_path)
        if not path.exists():
            raise AnnUnavailable(f"Faiss index not found: {path}")
        return faiss.read_index(str(path))

    @cached_property
    def _faiss_meta(self) -> dict[int, dict[str, Any]]:
        if not self.index_path:
            raise AnnUnavailable("ANN_INDEX_PATH is not configured")

        meta_path = Path(self.index_path).with_suffix(".json")
        if not meta_path.exists():
            raise AnnUnavailable(f"Faiss metadata not found: {meta_path}")
        with meta_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raise AnnUnavailable("Faiss metadata must be a JSON object")
        return {int(k): v for k, v in raw.items() if isinstance(v, dict)}

    def _search_faiss(
        self,
        emb: list[float],
        top_k: int,
        platform: str,
    ) -> list[dict[str, Any]]:
        try:
            import numpy as np  # type: ignore
        except ImportError as exc:
            raise AnnUnavailable("numpy is not installed") from exc

        vec = np.asarray([emb], dtype=np.float32)
        limit = top_k * 3 if platform != "all" else top_k
        scores, idxs = self._faiss_index.search(vec, limit)

        results: list[dict[str, Any]] = []
        normalized_platform = platform.lower()
        for score, idx in zip(scores[0], idxs[0]):
            if idx < 0:
                continue
            meta = self._faiss_meta.get(int(idx))
            if not meta:
                continue
            if (
                normalized_platform != "all"
                and str(meta.get("platform", "")).lower() != normalized_platform
            ):
                continue
            results.append({**meta, "score": float(score)})
            if len(results) >= top_k:
                break
        return results

    @cached_property
    def _milvus_client(self) -> Any:
        try:
            from pymilvus import MilvusClient  # type: ignore
        except ImportError as exc:
            raise AnnUnavailable("pymilvus is not installed") from exc

        uri = os.environ.get("MILVUS_URI", "http://localhost:19530")
        token = os.environ.get("MILVUS_TOKEN")
        db_name = os.environ.get("MILVUS_DB_NAME")
        kwargs: dict[str, Any] = {"uri": uri}
        if token:
            kwargs["token"] = token
        if db_name:
            kwargs["db_name"] = db_name
        return MilvusClient(**kwargs)

    def _search_milvus(
        self,
        emb: list[float],
        top_k: int,
        platform: str,
    ) -> list[dict[str, Any]]:
        output_fields = [
            "item_id",
            "platform",
            "title",
            "price_cny",
            "coupon_cny",
            "final_price_cny",
            "shop_name",
            "sales",
            "image_url",
            "url",
            "attributes_json",
            "raw_json",
            "embedding_text",
        ]
        expr = None
        if platform.lower() != "all":
            escaped = platform.lower().replace('"', '\\"')
            expr = f'platform == "{escaped}"'

        hits = self._milvus_client.search(
            collection_name=self.collection_name,
            data=[emb],
            anns_field=self.vector_field,
            limit=top_k,
            filter=expr,
            output_fields=output_fields,
        )

        rows: list[dict[str, Any]] = []
        for hit in hits[0] if hits else []:
            entity = hit.get("entity") if isinstance(hit, dict) else None
            if not isinstance(entity, dict):
                entity = {}
            distance = hit.get("distance") if isinstance(hit, dict) else None
            score = hit.get("score") if isinstance(hit, dict) else distance
            rows.append({**entity, "score": score})
        return rows


ann_client = AnnClient()
