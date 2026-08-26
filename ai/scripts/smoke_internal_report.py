"""Run the full internal report pipeline with inspected public-repository evidence."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from app.core.config import Settings
from app.core.exceptions import LLMProviderError, PortfolioReportDeadlineError
from app.domain import (
    AnalysisDepth,
    InternalEvidence,
    InternalEvidenceType,
    InternalPortfolioInput,
    InternalRepositoryInput,
    SnapshotHashAlgorithm,
)
from app.llm import GeminiProvider
from app.services import PortfolioReportService

OUTPUT_PATH = Path(__file__).with_name("smoke_internal_report.output.json")


def _gitddo_backend_input() -> InternalRepositoryInput:
    repository_name = "git-ddo/backend"
    activity_sha = "0f33058cd81881e9223277615606a5b1c73e8528"
    snapshot_sha = "21a8c30379c0ff9167f59ff164ea89a23f0bf483"

    return InternalRepositoryInput(
        repository_id="1325278478",
        repository_full_name=repository_name,
        description="GitHub 포트폴리오 분석 및 코칭 서비스의 Spring Boot 백엔드",
        analysis_depth=AnalysisDepth.P2,
        completed_evidence_levels=(
            AnalysisDepth.P0,
            AnalysisDepth.P1,
            AnalysisDepth.P2,
        ),
        snapshot_hash_algorithm=SnapshotHashAlgorithm.SHA1,
        snapshot_sha=snapshot_sha,
        evidence=(
            InternalEvidence(
                evidence_id="ev_001",
                repository_full_name=repository_name,
                evidence_type=InternalEvidenceType.GITHUB_STATIC,
                analysis_depth=AnalysisDepth.P0,
                key="TECHNOLOGY_DEPENDENCY",
                summary=(
                    "build.gradle에서 Java 21, Spring Boot 4.1, Spring Data JPA, "
                    "Spring Security OAuth2 Client, PostgreSQL, Flyway와 Testcontainers "
                    "의존성이 관찰되었습니다."
                ),
                source_paths=("build.gradle",),
                technology_names=(
                    "Java",
                    "Spring Boot",
                    "Spring Data JPA",
                    "Spring Security",
                    "PostgreSQL",
                    "Flyway",
                    "Testcontainers",
                ),
            ),
            InternalEvidence(
                evidence_id="ev_002",
                repository_full_name=repository_name,
                evidence_type=InternalEvidenceType.GITHUB_STATIC,
                analysis_depth=AnalysisDepth.P0,
                key="README_SECTIONS_OBSERVED",
                summary=(
                    "README에서 기술 구성, GitHub OAuth 설정, 로컬 실행, 환경 변수, "
                    "Swagger, 저장소 조회 API와 포트폴리오 평가 흐름이 관찰되었습니다."
                ),
                source_paths=("README.md",),
            ),
            InternalEvidence(
                evidence_id="ev_003",
                repository_full_name=repository_name,
                evidence_type=InternalEvidenceType.GITHUB_STATIC,
                analysis_depth=AnalysisDepth.P0,
                key="TEST_FILES_OBSERVED",
                summary=(
                    "src/test 아래에서 분석 수집기, 요청 조립기, 응답 Validator, "
                    "HTTP Client 등을 대상으로 한 테스트 파일 15개가 관찰되었습니다."
                ),
                source_paths=("src/test/java",),
            ),
            InternalEvidence(
                evidence_id="ev_004",
                repository_full_name=repository_name,
                evidence_type=InternalEvidenceType.GITHUB_STATIC,
                analysis_depth=AnalysisDepth.P0,
                key="DOCKER_COMPOSE_OBSERVED",
                summary=(
                    "compose.yml에서 PostgreSQL 17 컨테이너, healthcheck와 영속 볼륨 "
                    "구성이 관찰되었습니다."
                ),
                source_paths=("compose.yml",),
                technology_names=("Docker Compose", "PostgreSQL"),
            ),
            InternalEvidence(
                evidence_id="ev_005",
                repository_full_name=repository_name,
                evidence_type=InternalEvidenceType.BACKEND_DERIVED,
                analysis_depth=AnalysisDepth.P0,
                key="GITHUB_ACTIONS_NOT_OBSERVED",
                summary=(
                    "고정된 snapshot의 수집 대상 파일 트리에서 .github/workflows의 "
                    "Workflow 파일이 관찰되지 않았습니다. 실제 부재를 뜻하지 않습니다."
                ),
                derived_from_level=AnalysisDepth.P0,
            ),
            InternalEvidence(
                evidence_id="ev_006",
                repository_full_name=repository_name,
                evidence_type=InternalEvidenceType.GITHUB_ACTIVITY,
                analysis_depth=AnalysisDepth.P1,
                key="COMMIT_ACTIVITY_OBSERVED",
                summary=(
                    "커밋 0f33058에서 P1 Evidence 수집기, 활동 영향도 정책, AI 요청 "
                    "조립기와 AI 응답 Validator의 변경이 관찰되었습니다. 이는 활동 "
                    "범위 후보이며 개인 기여도나 숙련도를 뜻하지 않습니다."
                ),
                source_paths=(
                    "src/main/java/com/gitddo/analysis/application/P1EvidenceCollector.java",
                    "src/main/java/com/gitddo/analysis/application/AiAnalysisResponseValidator.java",
                ),
                commit_sha=activity_sha,
            ),
            InternalEvidence(
                evidence_id="ev_007",
                repository_full_name=repository_name,
                evidence_type=InternalEvidenceType.CODE_EVIDENCE,
                analysis_depth=AnalysisDepth.P2,
                key="CODE_SNIPPET",
                summary=(
                    "P1EvidenceCollector.java 113~153행에서 PR을 영향도 기준으로 제한해 "
                    "선택하고, 제한 초과 Warning과 PR Evidence를 생성하는 흐름이 "
                    "직접 관찰되었습니다. 판단 범위는 이 코드 구간으로 제한됩니다."
                ),
                source_paths=(
                    "src/main/java/com/gitddo/analysis/application/P1EvidenceCollector.java",
                ),
                technology_names=("Java",),
                path="src/main/java/com/gitddo/analysis/application/P1EvidenceCollector.java",
                start_line=113,
                end_line=153,
                commit_sha=snapshot_sha,
                source_evidence_refs=("ev_006",),
            ),
            InternalEvidence(
                evidence_id="ev_008",
                repository_full_name=repository_name,
                evidence_type=InternalEvidenceType.CODE_EVIDENCE,
                analysis_depth=AnalysisDepth.P2,
                key="CODE_SNIPPET",
                summary=(
                    "AiAnalysisResponseValidator.java 47~60행에서 요청의 Repository, "
                    "Evidence, UserClaim ID 집합을 구성하고 사용 깊이·저장소·코칭 "
                    "참조를 순차 검증하는 흐름이 직접 관찰되었습니다."
                ),
                source_paths=(
                    "src/main/java/com/gitddo/analysis/application/AiAnalysisResponseValidator.java",
                ),
                technology_names=("Java",),
                path="src/main/java/com/gitddo/analysis/application/AiAnalysisResponseValidator.java",
                start_line=47,
                end_line=60,
                commit_sha=snapshot_sha,
                source_evidence_refs=("ev_006",),
            ),
        ),
    )


def _congraduation_backend_input() -> InternalRepositoryInput:
    repository_name = "congraduation-team/congraduation-backend"
    activity_sha = "8c8f61901c1a1c78209aed7536e3fc73ff499a7e"
    snapshot_sha = "ea6c94d7fa14f271c1d2b5d27d7a4ed8efa9be53"

    return InternalRepositoryInput(
        repository_id="1278187947",
        repository_full_name=repository_name,
        description="세종대학교 졸업요건 진단 및 미래 학기 설계 백엔드 서비스",
        analysis_depth=AnalysisDepth.P2,
        completed_evidence_levels=(
            AnalysisDepth.P0,
            AnalysisDepth.P1,
            AnalysisDepth.P2,
        ),
        snapshot_hash_algorithm=SnapshotHashAlgorithm.SHA1,
        snapshot_sha=snapshot_sha,
        evidence=(
            InternalEvidence(
                evidence_id="ev_009",
                repository_full_name=repository_name,
                evidence_type=InternalEvidenceType.GITHUB_STATIC,
                analysis_depth=AnalysisDepth.P0,
                key="TECHNOLOGY_DEPENDENCY",
                summary=(
                    "build.gradle에서 Java 21, Spring Boot 3.3, Spring Data JPA, "
                    "MySQL, Apache POI, Jsoup와 Spring Boot Test 의존성이 관찰되었습니다."
                ),
                source_paths=("build.gradle",),
                technology_names=(
                    "Java",
                    "Spring Boot",
                    "Spring Data JPA",
                    "MySQL",
                    "Apache POI",
                    "Jsoup",
                ),
            ),
            InternalEvidence(
                evidence_id="ev_010",
                repository_full_name=repository_name,
                evidence_type=InternalEvidenceType.GITHUB_STATIC,
                analysis_depth=AnalysisDepth.P0,
                key="README_SECTIONS_OBSERVED",
                summary=(
                    "README에서 문제 정의, 핵심 기능, 기술 스택, 아키텍처, 실행 방법, "
                    "테스트 명령, 주요 API와 프로젝트 구조가 관찰되었습니다."
                ),
                source_paths=("README.md",),
            ),
            InternalEvidence(
                evidence_id="ev_011",
                repository_full_name=repository_name,
                evidence_type=InternalEvidenceType.GITHUB_STATIC,
                analysis_depth=AnalysisDepth.P0,
                key="TEST_FILES_OBSERVED",
                summary=(
                    "src/test에서 졸업요건 정책, 로드맵, 인증, ABEEK, 파서 및 서비스에 "
                    "대한 테스트 파일들이 관찰되었습니다."
                ),
                source_paths=("src/test/java",),
            ),
            InternalEvidence(
                evidence_id="ev_012",
                repository_full_name=repository_name,
                evidence_type=InternalEvidenceType.GITHUB_STATIC,
                analysis_depth=AnalysisDepth.P0,
                key="DOCKER_COMPOSE_OBSERVED",
                summary="docker-compose.yml에서 로컬 MySQL 실행 구성이 관찰되었습니다.",
                source_paths=("docker-compose.yml",),
                technology_names=("Docker Compose", "MySQL"),
            ),
            InternalEvidence(
                evidence_id="ev_013",
                repository_full_name=repository_name,
                evidence_type=InternalEvidenceType.GITHUB_STATIC,
                analysis_depth=AnalysisDepth.P0,
                key="GITHUB_ACTIONS_WORKFLOW_OBSERVED",
                summary=(
                    ".github/workflows/deploy.yml에서 main push 시 Java 21 환경에서 "
                    "bootJar를 빌드하고 EC2로 전송한 뒤 서비스를 재시작하는 Workflow가 "
                    "관찰되었습니다. 해당 Workflow는 테스트를 제외하고 빌드합니다."
                ),
                source_paths=(".github/workflows/deploy.yml",),
                technology_names=("GitHub Actions", "Java"),
            ),
            InternalEvidence(
                evidence_id="ev_014",
                repository_full_name=repository_name,
                evidence_type=InternalEvidenceType.GITHUB_ACTIVITY,
                analysis_depth=AnalysisDepth.P1,
                key="COMMIT_ACTIVITY_OBSERVED",
                summary=(
                    "커밋 8c8f619에서 2021학번 공통교양 필수 정책과 대응 테스트의 "
                    "동시 변경이 관찰되었습니다. 이는 활동 범위 후보이며 개인 기여도나 "
                    "숙련도를 뜻하지 않습니다."
                ),
                source_paths=(
                    "src/main/java/com/example/congraduation/service/graduation/"
                    "BalancedLiberalCoursePolicyService.java",
                    "src/test/java/com/example/congraduation/service/graduation/"
                    "GraduationProgressServiceTest.java",
                ),
                commit_sha=activity_sha,
            ),
            InternalEvidence(
                evidence_id="ev_015",
                repository_full_name=repository_name,
                evidence_type=InternalEvidenceType.CODE_EVIDENCE,
                analysis_depth=AnalysisDepth.P2,
                key="CODE_SNIPPET",
                summary=(
                    "BalancedLiberalCoursePolicyService.java 34~43행에서 2021학번에 적용할 "
                    "공통교양 필수 과목 목록이 상수로 분리되어 직접 관찰되었습니다. "
                    "판단 범위는 이 코드 구간으로 제한됩니다."
                ),
                source_paths=(
                    "src/main/java/com/example/congraduation/service/graduation/"
                    "BalancedLiberalCoursePolicyService.java",
                ),
                technology_names=("Java", "Spring Boot"),
                path=(
                    "src/main/java/com/example/congraduation/service/graduation/"
                    "BalancedLiberalCoursePolicyService.java"
                ),
                start_line=34,
                end_line=43,
                commit_sha=snapshot_sha,
                source_evidence_refs=("ev_014",),
            ),
            InternalEvidence(
                evidence_id="ev_016",
                repository_full_name=repository_name,
                evidence_type=InternalEvidenceType.CODE_EVIDENCE,
                analysis_depth=AnalysisDepth.P2,
                key="CODE_SNIPPET",
                summary=(
                    "GraduationProgressServiceTest.java 891~936행에서 2021학번 학생과 "
                    "8개 공통교양 이수 데이터를 구성하고 추출 결과를 검증하는 테스트 "
                    "사례가 직접 관찰되었습니다."
                ),
                source_paths=(
                    "src/test/java/com/example/congraduation/service/graduation/"
                    "GraduationProgressServiceTest.java",
                ),
                technology_names=("Java", "Spring Boot"),
                path=(
                    "src/test/java/com/example/congraduation/service/graduation/"
                    "GraduationProgressServiceTest.java"
                ),
                start_line=891,
                end_line=936,
                commit_sha=snapshot_sha,
                source_evidence_refs=("ev_014",),
            ),
        ),
    )


def build_smoke_input(
    *,
    repository_count: int = 2,
    analysis_depth: AnalysisDepth = AnalysisDepth.P2,
) -> InternalPortfolioInput:
    """Build a depth-scoped portfolio input from inspected public repositories."""
    if repository_count not in {1, 2}:
        raise ValueError("Smoke input supports one or two repositories.")

    repositories = (_gitddo_backend_input(), _congraduation_backend_input())
    return InternalPortfolioInput(
        requested_analysis_depth=analysis_depth,
        repositories=tuple(
            _repository_at_depth(repository, analysis_depth)
            for repository in repositories[:repository_count]
        ),
    )


def _repository_at_depth(
    repository: InternalRepositoryInput,
    analysis_depth: AnalysisDepth,
) -> InternalRepositoryInput:
    completed_levels = {
        AnalysisDepth.P0: (AnalysisDepth.P0,),
        AnalysisDepth.P1: (AnalysisDepth.P0, AnalysisDepth.P1),
        AnalysisDepth.P2: (AnalysisDepth.P0, AnalysisDepth.P1, AnalysisDepth.P2),
    }[analysis_depth]
    return repository.model_copy(
        update={
            "analysis_depth": analysis_depth,
            "completed_evidence_levels": completed_levels,
            "evidence": tuple(
                evidence
                for evidence in repository.evidence
                if evidence.analysis_depth in completed_levels
            ),
        }
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--depth",
        choices=tuple(depth.value for depth in AnalysisDepth),
        default=AnalysisDepth.P0.value,
    )
    parser.add_argument("--repository-count", type=int, choices=(1, 2), default=1)
    parser.add_argument("--question-count", type=int, default=1)
    parser.add_argument("--statement-count", type=int, default=1)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    """Execute the internal pipeline once and print its validated JSON result."""
    settings = Settings()
    provider: GeminiProvider | None = None
    analysis_depth = AnalysisDepth(args.depth)
    output_path = args.output or OUTPUT_PATH.with_name(
        f"smoke_internal_report_{analysis_depth.value.lower()}_"
        f"{args.repository_count}repo.output.json"
    )

    try:
        provider = GeminiProvider(settings)
        service = PortfolioReportService(
            provider,
            deadline_seconds=settings.ai_analysis_deadline_seconds,
        )
        report = await service.generate(
            build_smoke_input(
                repository_count=args.repository_count,
                analysis_depth=analysis_depth,
            ),
            question_count=args.question_count,
            statement_count=args.statement_count,
        )
    except (LLMProviderError, PortfolioReportDeadlineError, ValueError) as exc:
        print(f"Smoke run failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        if provider is not None:
            await provider.aclose()

    output = report.model_dump_json(indent=2)
    output_path.write_text(output + "\n", encoding="utf-8")
    print(f"Smoke result saved to {output_path}", file=sys.stderr)
    print(output)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(asyncio.run(run(_parse_args())))
