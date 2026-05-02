from __future__ import annotations

import base64
import json
import logging
import mimetypes
from pathlib import Path
from typing import Any

import httpx

from aiagent.vision.character_retriever import CharacterRetriever
from aiagent.vision.image_store import ImageStore, StoredImage
from aiagent.graphs.graph_model import (
    CharacterCandidate,
    VisionAnalyzeResult,
    VisionLive2DSuggestion,
    VisionMemoryCandidate,
    VisionSafetyResult,
)

logger = logging.getLogger(__name__)


class VisionService:
    def __init__(
        self,
        image_store: ImageStore,
        character_retriever: CharacterRetriever,
        provider: str = "mock",
        model: str = "",
        api_key: str | None = None,
        base_url: str = "",
        timeout_seconds: float = 60.0,
        confident_score: float = 0.78,
    ) -> None:
        self.image_store = image_store
        self.character_retriever = character_retriever
        self.provider = provider.strip().lower()
        self.model = model.strip()
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.confident_score = confident_score

    def analyze_upload(
        self,
        file_obj,
        filename: str,
        user_prompt: str = "",
        user_id: str = "guest",
    ) -> VisionAnalyzeResult:
        stored = self.image_store.save_upload(file_obj=file_obj, filename=filename)
        return self.analyze_stored_image(
            stored=stored,
            user_prompt=user_prompt,
            user_id=user_id,
        )

    def analyze_local_path(
        self,
        image_path: str | Path,
        user_prompt: str = "",
        user_id: str = "guest",
    ) -> VisionAnalyzeResult:
        stored = self.image_store.save_local_copy(image_path)
        return self.analyze_stored_image(
            stored=stored,
            user_prompt=user_prompt,
            user_id=user_id,
        )

    def analyze_stored_image(
        self,
        stored: StoredImage,
        user_prompt: str = "",
        user_id: str = "guest",
    ) -> VisionAnalyzeResult:
        candidates = self.character_retriever.retrieve(stored.path, top_k=5)
        model_data = self._analyze_with_model(
            stored=stored,
            candidates=candidates,
            user_prompt=user_prompt,
        )

        return self._build_result(
            stored=stored,
            candidates=candidates,
            model_data=model_data,
            user_prompt=user_prompt,
            user_id=user_id,
        )

    def rebuild_character_index(self, force_rebuild: bool = True) -> dict[str, Any]:
        return self.character_retriever.build_index(force_rebuild=force_rebuild)

    def character_index_stats(self) -> dict[str, Any]:
        return self.character_retriever.stats()

    def _analyze_with_model(
        self,
        stored: StoredImage,
        candidates: list[CharacterCandidate],
        user_prompt: str,
    ) -> dict[str, Any]:
        if self.provider in {"", "mock"}:
            return self._mock_model_result(candidates)

        if self.provider in {"openai", "siliconflow"}:
            return self._openai_compatible_vision(
                stored=stored,
                candidates=candidates,
                user_prompt=user_prompt,
            )

        raise ValueError(f"Unsupported vision provider: {self.provider}")

    def _openai_compatible_vision(
        self,
        stored: StoredImage,
        candidates: list[CharacterCandidate],
        user_prompt: str,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("Vision API key is not configured.")

        if not self.base_url:
            raise RuntimeError("Vision base URL is not configured.")

        if not self.model:
            raise RuntimeError("Vision model is not configured.")

        image_data_url = self._image_to_data_url(stored.path)
        candidate_text = self._format_candidates_for_prompt(candidates)

        prompt = f"""
你是面向二次元角色/IP 的高准确识图分析器。你的任务不是泛泛描述图片，而是结合角色图库候选项进行可靠判断。

重要规则：
1. 不要只凭大模型印象猜角色。
2. 必须优先参考候选角色的 image embedding 相似度、角色名、别名、视觉特征。
3. 如果候选相似度不足，或者图片信息不足，必须降低置信度。
4. 如果无法确认角色，recognized_characters 返回空数组。
5. 不要把相似角色混淆，例如洛天依、初音未来、言和、乐正绫。
6. confidence 必须是 0 到 1 之间的小数。
7. 输出必须是 JSON，不要输出 Markdown，不要输出解释性正文。

用户附加说明：
{user_prompt or "无"}

候选角色：
{candidate_text}

请输出 JSON：
{{
  "summary": "图片总体描述",
  "objects": ["物体1", "物体2"],
  "scene": "场景",
  "ocr_text": ["识别到的文字"],
  "mood": "氛围",
  "recognized_characters": [
    {{
      "character_id": "luotianyi",
      "name": "洛天依",
      "confidence": 0.91,
      "evidence": ["候选图库相似度高", "视觉特征匹配"]
    }}
  ],
  "safety": {{
    "has_sensitive_content": false,
    "risk_level": "none",
    "reason": ""
  }},
  "memory": {{
    "should_consider": false,
    "reason": ""
  }},
  "live2d": {{
    "suggested_emotion": "calm",
    "suggested_expression": "gentle",
    "suggested_motion": "soft_idle",
    "suggested_background": "room_default"
  }}
}}
""".strip()

        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "temperature": 0.1,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                }
            ],
        }

        with httpx.Client(timeout=self.timeout_seconds, trust_env=False) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        parsed = self._extract_json(content)
        parsed["_raw_model_output"] = content
        return parsed

    def _mock_model_result(self, candidates: list[CharacterCandidate]) -> dict[str, Any]:
        recognized = []

        if candidates:
            best = candidates[0]
            if best.confidence >= self.confident_score:
                recognized.append(
                    {
                        "character_id": best.character_id,
                        "name": best.name,
                        "confidence": best.confidence,
                        "evidence": best.evidence,
                    }
                )

        return {
            "summary": "已完成图片角色图库检索。当前为 mock vision，只根据 CLIP 图像向量候选判断。",
            "objects": [],
            "scene": "unknown",
            "ocr_text": [],
            "mood": "unknown",
            "recognized_characters": recognized,
            "safety": {
                "has_sensitive_content": False,
                "risk_level": "none",
                "reason": "",
            },
            "memory": {
                "should_consider": False,
                "reason": "mock vision 不自动建议写入长期记忆",
            },
            "live2d": {
                "suggested_emotion": "neutral",
                "suggested_expression": "neutral",
                "suggested_motion": "idle",
                "suggested_background": "room_default",
            },
            "_raw_model_output": "",
        }

    def _build_result(
        self,
        stored: StoredImage,
        candidates: list[CharacterCandidate],
        model_data: dict[str, Any],
        user_prompt: str,
        user_id: str,
    ) -> VisionAnalyzeResult:
        recognized = self._normalize_model_characters(
            raw_items=model_data.get("recognized_characters", []),
            retrieved_candidates=candidates,
        )

        best_confidence = max([item.confidence for item in recognized], default=0.0)
        is_confident = best_confidence >= self.confident_score

        if not is_confident:
            recognized = [
                item
                for item in recognized
                if item.confidence >= max(self.confident_score - 0.12, 0.0)
            ]

        return VisionAnalyzeResult(
            image_id=stored.image_id,
            image_path=str(stored.path),
            width=stored.width,
            height=stored.height,
            format=stored.format,
            summary=str(model_data.get("summary", "")).strip(),
            objects=[str(item).strip() for item in model_data.get("objects", []) if str(item).strip()],
            scene=str(model_data.get("scene", "")).strip(),
            ocr_text=[str(item).strip() for item in model_data.get("ocr_text", []) if str(item).strip()],
            mood=str(model_data.get("mood", "")).strip(),
            recognized_characters=recognized,
            is_confident=is_confident,
            confidence=best_confidence,
            safety=VisionSafetyResult(**(model_data.get("safety") or {})),
            memory=VisionMemoryCandidate(**(model_data.get("memory") or {})),
            live2d=VisionLive2DSuggestion(**(model_data.get("live2d") or {})),
            raw_model_output=str(model_data.get("_raw_model_output", "")),
            metadata={
                "user_id": user_id,
                "user_prompt": user_prompt,
                "character_retrieval_candidates": [
                    item.model_dump(mode="json")
                    for item in candidates
                ],
                "vision_provider": self.provider,
                "vision_model": self.model,
                "confident_score": self.confident_score,
            },
        )

    def _normalize_model_characters(
        self,
        raw_items: Any,
        retrieved_candidates: list[CharacterCandidate],
    ) -> list[CharacterCandidate]:
        if not isinstance(raw_items, list):
            raw_items = []

        retrieved_by_id = {
            item.character_id: item
            for item in retrieved_candidates
        }

        output: list[CharacterCandidate] = []

        for raw in raw_items:
            if not isinstance(raw, dict):
                continue

            character_id = str(raw.get("character_id", "")).strip()
            if not character_id:
                continue

            base = retrieved_by_id.get(character_id)

            try:
                model_confidence = float(raw.get("confidence", 0.0))
            except (TypeError, ValueError):
                model_confidence = 0.0

            model_confidence = min(max(model_confidence, 0.0), 1.0)
            retrieval_score = base.score if base else 0.0

            if base:
                final_confidence = round(model_confidence * 0.62 + retrieval_score * 0.38, 6)
            else:
                final_confidence = round(model_confidence * 0.55, 6)

            evidence: list[str] = []
            if base:
                evidence.extend(base.evidence)
            evidence.extend([str(item).strip() for item in raw.get("evidence", []) if str(item).strip()])

            output.append(
                CharacterCandidate(
                    character_id=character_id,
                    name=str(raw.get("name") or (base.name if base else character_id)).strip(),
                    aliases=base.aliases if base else [],
                    score=retrieval_score,
                    confidence=final_confidence,
                    evidence=evidence,
                    metadata={
                        "model_confidence": model_confidence,
                        "retrieval_score": retrieval_score,
                    },
                )
            )

        if output:
            return sorted(output, key=lambda item: item.confidence, reverse=True)

        return retrieved_candidates[:3]

    def _format_candidates_for_prompt(self, candidates: list[CharacterCandidate]) -> str:
        if not candidates:
            return "无候选角色。"

        lines: list[str] = []
        for index, item in enumerate(candidates, start=1):
            aliases = "、".join(item.aliases) if item.aliases else "无"
            evidence = "；".join(item.evidence)
            lines.append(
                f"{index}. character_id={item.character_id}, name={item.name}, "
                f"aliases={aliases}, retrieval_score={item.score:.3f}, evidence={evidence}"
            )

        return "\n".join(lines)

    def _image_to_data_url(self, image_path: str | Path) -> str:
        path = Path(image_path)
        mime_type = mimetypes.guess_type(str(path))[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    def _extract_json(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()

        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`").strip()
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if start < 0 or end <= start:
            raise ValueError("No JSON object found in vision model output.")

        parsed = json.loads(cleaned[start : end + 1])
        if not isinstance(parsed, dict):
            raise ValueError("Vision model JSON root is not an object.")

        return parsed
