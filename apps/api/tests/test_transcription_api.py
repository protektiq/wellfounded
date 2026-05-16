"""Integration tests for interview upload and transcription pipeline."""

from __future__ import annotations

import asyncio
import base64
import re
import struct
import uuid
import wave
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cases.models import Case, ClaimBasis
from config import get_settings
from declarations.models import TranscriptStatus
from orgs.models import UserRole, UserStatus
from orgs.repository import OrgRepository
from storage import s3_client
from transcription.repository import TranscriptionRepository

_API_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _make_test_wav(path: Path, duration_seconds: float = 1.0) -> None:
    sample_rate = 16000
    n_frames = int(sample_rate * duration_seconds)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        silence = struct.pack("<h", 0) * n_frames
        wf.writeframes(silence)


@pytest.fixture
def envelope_master_key_b64() -> str:
    return base64.b64encode(b"0" * 32).decode("ascii")


@pytest.fixture(autouse=True)
def _transcription_test_env(
    envelope_master_key_b64: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVELOPE_MASTER_KEY", envelope_master_key_b64)
    monkeypatch.setenv("TRANSCRIPTION_E2E_STUB", "true")
    monkeypatch.setenv("ENVIRONMENT", "local")
    get_settings.cache_clear()


async def _magic_login(
    *,
    api_client: AsyncClient,
    db_session: AsyncSession,
    slug: str,
    email: str,
    role: UserRole,
    capsys: pytest.CaptureFixture[str],
) -> uuid.UUID:
    org_repo = OrgRepository(db_session)
    org = await org_repo.get_org_by_slug(slug)
    if org is None:
        org = await org_repo.create_org(name="Tx Org", slug=slug)
    user = await org_repo.get_user_by_email(email, org.id)
    if user is None:
        user = await org_repo.create_user(
            organization_id=org.id,
            email=email,
            display_name="Tx User",
            role=role,
            status=UserStatus.active,
        )
    await db_session.commit()

    await api_client.post(
        "/auth/magic-link",
        json={"email": email, "organization_slug": slug},
    )
    out = capsys.readouterr().out
    m = re.search(r"token=([^\s]+)", out)
    assert m is not None, out
    r = await api_client.get(
        f"/auth/callback?token={m.group(1)}",
        follow_redirects=False,
    )
    assert r.status_code == 302
    return user.id


async def _create_case(
    api_client: AsyncClient,
    *,
    lead_user_id: uuid.UUID,
) -> uuid.UUID:
    r = await api_client.post(
        "/cases",
        json={
            "pseudonym": "M.A. — Eritrea",
            "country_code": "er",
            "basis": ClaimBasis.political_opinion.value,
            "group_description": "PSG",
            "filing_deadline": None,
            "asylum_office": None,
            "intake_notes": "Notes",
            "assignments": [
                {"user_id": str(lead_user_id), "role_on_case": "lead_attorney"},
            ],
        },
    )
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["id"])


@pytest.mark.asyncio(loop_scope="session")
async def test_interview_upload_encrypts_at_rest(
    api_client: AsyncClient,
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slug = f"tx-enc-{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    user_id = await _magic_login(
        api_client=api_client,
        db_session=db_session,
        slug=slug,
        email=email,
        role=UserRole.attorney,
        capsys=capsys,
    )
    case_id = await _create_case(api_client, lead_user_id=user_id)

    wav_path = _API_FIXTURES / "audio" / "test_upload.wav"
    _make_test_wav(wav_path, duration_seconds=1.0)

    with wav_path.open("rb") as f:
        r = await api_client.post(
            f"/cases/{case_id}/interviews",
            data={"source_language": "es"},
            files={"file": ("interview.wav", f, "audio/wav")},
        )
    assert r.status_code == 202, r.text
    audio_id = uuid.UUID(r.json()["interview_audio_id"])

    result = await db_session.execute(select(Case).where(Case.id == case_id))
    org_id = result.scalar_one().organization_id
    repo = TranscriptionRepository(db_session)
    audio = await repo.get_interview_audio(org_id, audio_id)
    assert audio is not None
    raw = s3_client.get_object_bytes(key=audio.storage_key)
    assert raw[:4] != b"RIFF"


@pytest.mark.asyncio(loop_scope="session")
async def test_interview_upload_202_and_poll_complete(
    api_client: AsyncClient,
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slug = f"tx-poll-{uuid.uuid4().hex[:8]}"
    user_id = await _magic_login(
        api_client=api_client,
        db_session=db_session,
        slug=slug,
        email=f"{slug}@example.com",
        role=UserRole.attorney,
        capsys=capsys,
    )
    case_id = await _create_case(api_client, lead_user_id=user_id)
    wav_path = _API_FIXTURES / "audio" / "poll.wav"
    _make_test_wav(wav_path)

    with wav_path.open("rb") as f:
        r = await api_client.post(
            f"/cases/{case_id}/interviews",
            data={"source_language": "es"},
            files={"file": ("interview.wav", f, "audio/wav")},
        )
    assert r.status_code == 202
    transcript_id = uuid.UUID(r.json()["transcript_id"])
    audio_id = uuid.UUID(r.json()["interview_audio_id"])

    result = await db_session.execute(select(Case).where(Case.id == case_id))
    org_id = result.scalar_one().organization_id
    repo = TranscriptionRepository(db_session)

    for _ in range(80):
        await db_session.rollback()
        tx = await repo.get_transcript(org_id, transcript_id)
        if tx is not None and tx.status == TranscriptStatus.complete:
            break
        await asyncio.sleep(0.05)
    else:
        tx = await repo.get_transcript(org_id, transcript_id)
        detail = tx.status.value if tx else "missing"
        err = tx.error_message if tx else None
        pytest.fail(f"transcript did not complete: status={detail} err={err}")

    r2 = await api_client.get(f"/cases/{case_id}/transcripts/{transcript_id}")
    assert r2.status_code == 200
    assert r2.json()["status"] == "complete"

    r3 = await api_client.get(f"/cases/{case_id}/interviews/{audio_id}")
    assert r3.status_code == 200
    assert r3.json()["transcription_status"] == "complete"


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("lang", ["es", "zh", "fr", "ht", "ti", "prs"])
async def test_transcription_stub_six_languages(
    api_client: AsyncClient,
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
    lang: str,
) -> None:
    slug = f"tx-{lang}-{uuid.uuid4().hex[:6]}"
    user_id = await _magic_login(
        api_client=api_client,
        db_session=db_session,
        slug=slug,
        email=f"{slug}@example.com",
        role=UserRole.attorney,
        capsys=capsys,
    )
    case_id = await _create_case(api_client, lead_user_id=user_id)
    wav_path = _API_FIXTURES / "audio" / f"{lang}.wav"
    _make_test_wav(wav_path, duration_seconds=0.5)

    with wav_path.open("rb") as f:
        r = await api_client.post(
            f"/cases/{case_id}/interviews",
            data={"source_language": lang},
            files={"file": (f"{lang}.wav", f, "audio/wav")},
        )
    assert r.status_code == 202
    transcript_id = uuid.UUID(r.json()["transcript_id"])

    result = await db_session.execute(select(Case).where(Case.id == case_id))
    org_id = result.scalar_one().organization_id
    repo = TranscriptionRepository(db_session)

    for _ in range(80):
        await db_session.rollback()
        tx = await repo.get_transcript(org_id, transcript_id)
        if tx is not None and tx.status == TranscriptStatus.complete:
            assert tx.source_language.value == lang
            return
        await asyncio.sleep(0.05)
    tx = await repo.get_transcript(org_id, transcript_id)
    pytest.fail(
        f"transcript for {lang} did not complete: "
        f"{tx.status.value if tx else 'missing'} {tx.error_message if tx else ''}",
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_org_data_key_revoke_blocks_upload(
    api_client: AsyncClient,
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slug = f"tx-rev-{uuid.uuid4().hex[:8]}"
    user_id = await _magic_login(
        api_client=api_client,
        db_session=db_session,
        slug=slug,
        email=f"{slug}@example.com",
        role=UserRole.admin,
        capsys=capsys,
    )
    case_id = await _create_case(api_client, lead_user_id=user_id)
    result = await db_session.execute(select(Case).where(Case.id == case_id))
    org_id = result.scalar_one().organization_id

    org_repo = OrgRepository(db_session)
    await org_repo.revoke_data_key(org_id)
    await db_session.commit()

    wav_path = _API_FIXTURES / "audio" / "revoke.wav"
    _make_test_wav(wav_path)
    with wav_path.open("rb") as f:
        r = await api_client.post(
            f"/cases/{case_id}/interviews",
            data={"source_language": "es"},
            files={"file": ("interview.wav", f, "audio/wav")},
        )
    assert r.status_code == 403


@pytest.mark.asyncio(loop_scope="session")
async def test_interview_rejects_invalid_format(
    api_client: AsyncClient,
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
) -> None:
    slug = f"tx-bad-{uuid.uuid4().hex[:8]}"
    user_id = await _magic_login(
        api_client=api_client,
        db_session=db_session,
        slug=slug,
        email=f"{slug}@example.com",
        role=UserRole.attorney,
        capsys=capsys,
    )
    case_id = await _create_case(api_client, lead_user_id=user_id)
    r = await api_client.post(
        f"/cases/{case_id}/interviews",
        data={"source_language": "es"},
        files={"file": ("bad.txt", b"not audio", "text/plain")},
    )
    assert r.status_code == 400


def test_encryption_round_trip() -> None:
    import uuid as _uuid

    from encryption.service import (
        LocalEnvelopeCrypto,
        decrypt_audio_from_storage,
        encrypt_audio_for_storage,
    )

    crypto = LocalEnvelopeCrypto(b"1" * 32)
    org = _uuid.uuid4()
    plain = b"RIFF....test audio content"
    packed, _kid = encrypt_audio_for_storage(crypto, org, plain)
    out = decrypt_audio_from_storage(crypto, org, packed, is_revoked=False)
    assert out == plain
