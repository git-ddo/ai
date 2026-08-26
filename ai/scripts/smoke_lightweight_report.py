"""Generate one compact report from selected real-repository evidence."""

import asyncio
import json
import logging
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings
from app.core.exceptions import LLMProviderError
from app.llm import GeminiProvider
from app.prompts import build_system_prompt
from scripts.smoke_internal_report import build_smoke_input

OUTPUT_PATH = Path(__file__).with_name("smoke_lightweight_report.output.json")
SELECTED_EVIDENCE_IDS = frozenset(
    {
        "ev_001",
        "ev_002",
        "ev_005",
        "ev_006",
        "ev_007",
        "ev_008",
        "ev_009",
        "ev_010",
        "ev_013",
        "ev_014",
        "ev_015",
        "ev_016",
    }
)


class LightweightModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LightweightFinding(LightweightModel):
    content: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1, max_length=2)


class LightweightRepositoryResult(LightweightModel):
    repository_full_name: str = Field(min_length=1)
    summary: LightweightFinding
    highlight: LightweightFinding
    improvement: LightweightFinding
    interview_question: LightweightFinding


class LightweightPortfolioResult(LightweightModel):
    representative_repository: str = Field(min_length=1)
    representative_reason: LightweightFinding
    repositories: tuple[LightweightRepositoryResult, ...] = Field(
        min_length=2,
        max_length=2,
    )
    limitation: str = Field(min_length=1)


def build_lightweight_prompt() -> str:
    portfolio = build_smoke_input()
    repositories: list[dict[str, object]] = []
    for repository in portfolio.repositories:
        evidence = [
            {
                "evidence_id": item.evidence_id,
                "analysis_depth": item.analysis_depth.value,
                "evidence_type": item.evidence_type.value,
                "summary": item.summary,
                "source_paths": item.source_paths,
                "technology_names": item.technology_names,
            }
            for item in repository.evidence
            if item.evidence_id in SELECTED_EVIDENCE_IDS
        ]
        repositories.append(
            {
                "repository_full_name": repository.repository_full_name,
                "description": repository.description,
                "evidence": evidence,
            }
        )

    data = json.dumps(
        {"repositories": repositories},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"""
[UNTRUSTED REPOSITORY DATA]
{data}
[/UNTRUSTED REPOSITORY DATA]

[TASK]
- 한국어로 매우 짧게 작성한다.
- Repository마다 요약, 어필 포인트, 개선 제안, 면접 질문을 정확히 하나씩 생성한다.
- 각 항목은 제공된 해당 Repository Evidence ID만 1~2개 참조한다.
- 대표 Repository 하나와 Evidence 기반 이유를 생성한다.
- 입력에 없는 기술, 파일, 역할 또는 개인 기여를 생성하지 않는다.
- NOT_OBSERVED를 실제 부재로 단정하지 않는다.
- 코드 구간을 Repository 전체 품질로 일반화하지 않는다.
- 결과는 LightweightPortfolioResult Structured Output Schema를 따른다.
[/TASK]
""".strip()


async def run() -> int:
    provider: GeminiProvider | None = None
    try:
        provider = GeminiProvider(Settings())
        generation = await provider.generate_structured(
            system_prompt=build_system_prompt(),
            user_prompt=build_lightweight_prompt(),
            response_model=LightweightPortfolioResult,
        )
    except (LLMProviderError, ValueError) as exc:
        print(f"Lightweight smoke failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        if provider is not None:
            await provider.aclose()

    output = generation.value.model_dump_json(indent=2)
    OUTPUT_PATH.write_text(output + "\n", encoding="utf-8")
    print(f"Lightweight result saved to {OUTPUT_PATH}", file=sys.stderr)
    print(output)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(asyncio.run(run()))
