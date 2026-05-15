"""Orchestration for country conditions memo generation."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from audit.writer import AuditWriter
from cases.repository import CaseRepository
from config import get_settings
from country_conditions.graph import build_country_conditions_graph
from country_conditions.models import CountryConditionsMemoStatus
from country_conditions.repository import CountryConditionsRepository
from country_conditions.schemas import CountryConditionsInputs
from db.session import get_async_session_maker

log = structlog.get_logger()


class CountryConditionsService:
    """Kicks off LangGraph memo generation in a background asyncio task."""

    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._session_maker = session_maker

    def _maker(self) -> async_sessionmaker[AsyncSession]:
        if self._session_maker is not None:
            return self._session_maker
        return get_async_session_maker()

    async def generate(
        self,
        *,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
        inputs: CountryConditionsInputs,
        requested_by_user_id: uuid.UUID,
        correlation_request_id: uuid.UUID,
        session: AsyncSession,
        audit: AuditWriter,
    ) -> tuple[uuid.UUID, int]:
        """Persist memo row, audit start, commit, then schedule graph run."""
        case_repo = CaseRepository(session)
        case = await case_repo.get_case_for_org(organization_id, case_id)
        if case is None:
            raise ValueError("Case not found")

        cc_repo = CountryConditionsRepository(session)
        inputs_dict = inputs.model_dump(mode="json")
        memo = await cc_repo.create_memo_with_artifact(
            organization_id,
            case_id,
            inputs=inputs_dict,
            generated_by_user_id=requested_by_user_id,
            correlation_request_id=correlation_request_id,
        )
        await audit.record(
            "country_conditions.generate.start",
            organization_id,
            requested_by_user_id,
            "country_conditions_memo",
            memo.id,
            metadata={"case_id": str(case_id), "version": memo.version},
        )
        await session.flush()

        memo_id = memo.id
        version = memo.version
        await session.commit()

        asyncio.create_task(
            self._run_graph_background(
                organization_id=organization_id,
                case_id=case_id,
                memo_id=memo_id,
                user_id=requested_by_user_id,
                correlation_request_id=correlation_request_id,
                inputs_dict=inputs_dict,
            ),
        )
        log.info(
            "country_conditions_generation_scheduled",
            memo_id=str(memo_id),
            case_id=str(case_id),
        )
        return memo_id, version

    async def _run_graph_background(
        self,
        *,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
        memo_id: uuid.UUID,
        user_id: uuid.UUID,
        correlation_request_id: uuid.UUID,
        inputs_dict: dict[str, Any],
    ) -> None:
        settings = get_settings()
        uri = settings.resolved_checkpoint_database_url()
        maker = self._maker()
        stub_local = (
            settings.country_conditions_e2e_stub
            and settings.environment.strip().lower() == "local"
        )
        structlog.contextvars.bind_contextvars(
            organization_id=str(organization_id),
            user_id=str(user_id),
        )
        try:
            async with maker() as session:
                audit = AuditWriter(session, correlation_request_id)
                repo = CountryConditionsRepository(session)
                try:
                    await repo.update_memo_status(
                        organization_id,
                        memo_id,
                        CountryConditionsMemoStatus.generating,
                    )
                    await session.flush()

                    if stub_local:
                        from country_conditions.e2e_stub import e2e_stub_final_memo_dict

                        await repo.update_memo_complete(
                            organization_id,
                            memo_id,
                            output=e2e_stub_final_memo_dict(),
                            model_versions={"e2e": "fixture"},
                        )
                        await audit.record(
                            "country_conditions.generate.complete",
                            organization_id,
                            user_id,
                            "country_conditions_memo",
                            memo_id,
                            metadata={"case_id": str(case_id), "e2e_stub": True},
                        )
                        await session.commit()
                        return

                    async with AsyncPostgresSaver.from_conn_string(uri) as checkpointer:
                        await checkpointer.setup()
                        graph = build_country_conditions_graph(
                            checkpointer=checkpointer,
                            session=session,
                            organization_id=organization_id,
                            user_id=user_id,
                            memo_id=memo_id,
                            audit=audit,
                        )
                        init: dict[str, Any] = {
                            "organization_id": organization_id,
                            "case_id": case_id,
                            "memo_id": memo_id,
                            "requested_by_user_id": user_id,
                            "inputs": inputs_dict,
                            "model_versions": {},
                        }
                        final_state = await graph.ainvoke(
                            init,
                            {"configurable": {"thread_id": str(memo_id)}},
                        )
                    final_memo = final_state.get("final_memo")
                    model_versions = final_state.get("model_versions", {})
                    if not isinstance(final_memo, dict):
                        raise RuntimeError("graph finished without final_memo")
                    await repo.update_memo_complete(
                        organization_id,
                        memo_id,
                        output=final_memo,
                        model_versions=dict(model_versions),
                    )
                    await audit.record(
                        "country_conditions.generate.complete",
                        organization_id,
                        user_id,
                        "country_conditions_memo",
                        memo_id,
                        metadata={"case_id": str(case_id)},
                    )
                    await session.commit()
                except BaseException as exc:
                    await session.rollback()
                    err_text = f"{type(exc).__name__}: {exc}"
                    log.exception(
                        "country_conditions_generation_failed",
                        memo_id=str(memo_id),
                    )
                    async with maker() as session2:
                        audit2 = AuditWriter(session2, correlation_request_id)
                        repo2 = CountryConditionsRepository(session2)
                        await repo2.update_memo_failed(
                            organization_id,
                            memo_id,
                            error_message=err_text[:8000],
                        )
                        await audit2.record(
                            "country_conditions.generate.failed",
                            organization_id,
                            user_id,
                            "country_conditions_memo",
                            memo_id,
                            metadata={"error": err_text[:2000]},
                        )
                        await session2.commit()
        finally:
            structlog.contextvars.unbind_contextvars(
                "organization_id",
                "user_id",
            )


def get_country_conditions_service() -> CountryConditionsService:
    return CountryConditionsService()
