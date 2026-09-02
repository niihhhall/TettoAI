"""CodeVerity field-intake state machine (PRD §5, States 0–6).

Deterministic routing on the inbound `ButtonPayload` (the de-risk finding). Depends only
on the Repository, Sender, and Services protocols, so it runs fully offline in tests.

Flow:
  unknown phone            -> onboarding (name -> company code) -> STATE_1
  STATE_1_JOBSITE          -> pick job/new              -> STATE_2
  STATE_2_LOCATION         -> confirm address           -> STATE_3
  STATE_3_PHOTOS           -> upload photos / skip       -> STATE_4
  STATE_4_VOICE            -> voice note -> extract       -> confirm
  submit_package           -> compile PDF, notify office -> STATE_6_COMPLETE
                              (bounty credited + CRM pushed on operator approval)
"""

from __future__ import annotations

import asyncio

from app.models import CrewMember, InboundMessage, OutboundAction, State
from app.repository import Repository
from app.services import Services, StubServices
from app.whatsapp.client import OutboxSender, Sender

# Photo-collection tuning (single-worker, in-memory timers). Move to a durable scheduler
# when scaling to multiple workers (see spec: post-demo hardening).
PHOTO_QUIET_SECONDS = 15     # quiet gap after the last photo before we nudge
PHOTO_GRACE_SECONDS = 20     # extra grace after the nudge before auto-advancing
PHOTO_MIN = 1               # minimum photos to proceed (demo=1; recommend 3 in prod)
PHOTO_MAX = 8               # cap; hitting it auto-advances immediately


def normalize_phone(raw: str) -> str:
    """Twilio sends 'whatsapp:+E164'; the DB stores bare E.164. Strip channel prefixes so
    identity lookups match. (De-risk catch: mismatch sent every known foreman to onboarding.)"""
    return raw.split(":", 1)[1].strip() if ":" in raw else raw.strip()


class StateMachine:
    def __init__(self, repo: Repository, services: Services | None = None,
                 sender: Sender | None = None, on_event=None, auto_advance: bool = False,
                 lean_photos: bool = False) -> None:
        self.repo = repo
        self.services = services or StubServices()
        # Sender used for messages the machine emits on its own (e.g. the photo timer),
        # outside a direct inbound reply.
        self.sender = sender or OutboxSender()
        # Optional async callback(event: dict) invoked on completion -> WS broadcast.
        self.on_event = on_event
        # auto_advance schedules the real photo quiet-timer. Off in tests (they call
        # _finish_photos directly) so no background asyncio tasks leak across event loops.
        self.auto_advance = auto_advance
        # lean_photos: suppress the per-good-photo reply and the mid-photo nudge to conserve
        # outbound messages (Twilio trial cap). Evidence is still captured either way.
        self.lean_photos = lean_photos
        # Ephemeral onboarding buffer keyed by phone. Production: persist in a store.
        self._onboarding: dict[str, dict] = {}
        # Per-phone photo batch state (single-worker, in-memory).
        self._photo_timers: dict[str, asyncio.Task] = {}
        self._photo_hashes: dict[str, list[int]] = {}
        # Per-phone lock to serialize concurrent inbound webhooks (photo/voice races).
        self._locks: dict[str, asyncio.Lock] = {}

    async def handle(self, inbound: InboundMessage) -> list[OutboundAction]:
        phone = normalize_phone(inbound.from_)
        # Serialize concurrent webhooks for the same phone. A photo and a voice note sent
        # back-to-back arrive as SEPARATE webhooks that run in separate background tasks;
        # without this, the (faster) voice task can check for photos before the (slower,
        # vision-captioned) photo task has saved them -> "send a photo first" after a photo.
        # Live runs only (auto_advance); tests call sequentially, each on its own event loop.
        if not self.auto_advance:
            return await self._handle(inbound, phone)
        async with self._locks.setdefault(phone, asyncio.Lock()):
            return await self._handle(inbound, phone)

    async def _handle(self, inbound: InboundMessage, phone: str) -> list[OutboundAction]:
        # Every inbound (re)opens the 24h WhatsApp window — record before anything else.
        await self.repo.record_inbound(phone)

        # Demo restart: typing "demo" (or "restart"/"reset") from any state wipes this
        # number and starts over from onboarding (name -> company -> full flow). Lets an
        # operator re-run the whole demo without any database reset.
        if self._is_reset_keyword(inbound.body):
            await self._demo_reset(phone)
            return await self._onboard(inbound, phone)

        crew = await self.repo.get_crew_by_phone(phone)
        if crew is None:
            return await self._onboard(inbound, phone)

        session = await self.repo.get_active_session(crew.crew_id)
        if session is None:
            await self.repo.create_session(crew.crew_id)
            return [self._jobsite_prompt(crew)]

        handlers = {
            State.JOBSITE: self._on_jobsite,
            State.LOCATION: self._on_location,
            State.PHOTOS: self._on_photos,
            State.VOICE: self._on_voice,
            State.CONFIRM: self._on_voice,
        }
        handler = handlers.get(session.current_state, self._on_jobsite)
        return await handler(inbound, crew, session)

    # --- Demo restart keyword ----------------------------------------------------

    _RESET_WORDS = {"demo", "restart", "reset", "start over", "start demo"}

    @classmethod
    def _is_reset_keyword(cls, text: str | None) -> bool:
        return (text or "").strip().lower().strip(".!") in cls._RESET_WORDS

    async def _demo_reset(self, phone: str) -> None:
        """Forget this number so the flow starts fresh from onboarding (name prompt)."""
        self._onboarding.pop(phone, None)
        self._cancel_photo_timer(phone)
        self._photo_hashes.pop(phone, None)
        await self.repo.delete_crew_by_phone(phone)

    # --- State 0.5: onboarding ---------------------------------------------------

    async def _onboard(self, inbound: InboundMessage, phone: str) -> list[OutboundAction]:
        buf = self._onboarding.get(phone)

        if buf is None:
            self._onboarding[phone] = {"step": "name"}
            return [OutboundAction(text=(
                "Welcome to CodeVerity Field Intake.\n\n"
                "This number is not registered yet. To get started, please reply with your full name."
            ))]

        if buf["step"] == "name":
            buf["name"] = inbound.body.strip() or "Unknown Foreman"
            buf["step"] = "company"
            return [OutboundAction(template="codeverity_company_list")]

        # step == "company"
        code = self._resolve_company_code(inbound)
        if code is None and inbound.button_payload == "enter_company_code":
            return [OutboundAction(text="Please reply with your company code (for example, 4821).")]

        company = await self.repo.get_company_by_code(code) if code else None
        if company is None:
            return [OutboundAction(text="That company code was not recognized. Please check it and reply again.")]

        crew = await self.repo.create_crew_member(phone, buf["name"], company.company_id)
        self._onboarding.pop(phone, None)
        await self.repo.create_session(crew.crew_id)
        return [
            OutboundAction(text=f"Thank you. You are now linked to {company.company_name}. Let's begin your inspection."),
            self._jobsite_prompt(crew),
        ]

    @staticmethod
    def _resolve_company_code(inbound: InboundMessage) -> str | None:
        payload = inbound.button_payload
        mapping = {"company_apex": "4821", "company_titan": "7710"}
        if payload in mapping:
            return mapping[payload]
        if payload == "enter_company_code":
            return None
        return inbound.body.strip() or None

    # --- State 1: jobsite selection ---------------------------------------------

    async def _on_jobsite(self, inbound, crew, session) -> list[OutboundAction]:
        payload = inbound.button_payload
        if payload in {"job_1", "new_jobsite"} or (payload and payload.startswith("job_")):
            jobs = await self.repo.list_jobsites(crew.company_id) if crew.company_id else []
            job = jobs[0] if (payload != "new_jobsite" and jobs) else None
            await self.repo.update_session(
                session.session_id,
                job_id=(job.job_id if job else None),
                current_state=State.LOCATION,
            )
            # Ask for the real GPS pin — we reverse-geocode it and confirm the actual address.
            return [OutboundAction(text=(
                "Please share the property location so we can verify the address.\n\n"
                "Tap the attachment icon, choose Location, then select Send your current location."
            ))]
        return [self._jobsite_prompt(crew)]

    _LOCATION_PROMPT = (
        "Please share the property location. Tap the attachment icon, choose Location, "
        "then select Send your current location."
    )

    def _jobsite_prompt(self, crew: CrewMember) -> OutboundAction:
        return OutboundAction(
            template="codeverity_jobsite_list",
            variables={"1": "1420 Elmwood Dr", "2": "Claim #A-1029"},
        )

    # --- State 2: location + municipal ordinance --------------------------------

    async def _on_location(self, inbound, crew, session) -> list[OutboundAction]:
        # Foreman shared a GPS pin -> reverse-geocode it and confirm the REAL address.
        if inbound.latitude is not None and inbound.longitude is not None:
            geo = await self.services.reverse_geocode(inbound.latitude, inbound.longitude)
            address = geo.get("address") or inbound.location_label or "the detected location"
            if session.job_id:
                # Existing selected jobsite — correct/confirm its address from the real GPS.
                fields = {"property_address": address}
                if geo.get("city"):
                    fields["city"] = geo["city"]
                if geo.get("county"):
                    fields["county"] = geo["county"]
                await self.repo.update_jobsite(session.job_id, **fields)
            elif crew.company_id:
                # "New Jobsite" path — auto-create the jobsite from the confirmed GPS location.
                job = await self.repo.create_jobsite(
                    crew.company_id, property_address=address,
                    city=geo.get("city"), county=geo.get("county"), zip_code=geo.get("zip_code"),
                )
                await self.repo.update_session(session.session_id, job_id=job.job_id)
            return [OutboundAction(template="codeverity_location_confirm", variables={"1": address})]

        if inbound.button_payload == "confirm_address":
            await self.repo.update_session(session.session_id, current_state=State.PHOTOS)
            self._photo_hashes.pop(normalize_phone(inbound.from_), None)
            return [OutboundAction(text=(
                "Address confirmed.\n\n"
                "Please send your roof photos one at a time so we can review each one. "
                "You may add a voice note after any photo to describe that damage.\n\n"
                "Send your first photo when ready."
            ))]
        if inbound.button_payload in {"edit_address", "resend_gps"}:
            return [OutboundAction(text=(
                "No problem. Please share your current location again: tap the attachment icon, "
                "choose Location, then select Send your current location."
            ))]
        # Still waiting for a location pin.
        return [OutboundAction(text=self._LOCATION_PROMPT)]

    # --- State 3: per-photo evidence (photo -> auto caption -> optional voice) ----

    async def _on_photos(self, inbound, crew, session) -> list[OutboundAction]:
        phone = normalize_phone(inbound.from_)

        # Button taps from the "add more / continue" prompt.
        if inbound.button_payload == "photos_done":
            return await self._advance_to_voice(phone, session)
        if inbound.button_payload == "photos_add_more":
            self._reset_photo_timer(phone)
            return [OutboundAction(text="Please send the next photo.")]

        images = [(u, ct) for u, ct in zip(inbound.media_urls, inbound.media_content_types)
                  if (ct or "").startswith("image")]
        audios = [(u, ct) for u, ct in zip(inbound.media_urls, inbound.media_content_types)
                  if (ct or "").startswith("audio")]

        if images:
            replies = await self._ingest_photos(phone, session, images)
            # A voice note sent in the SAME message as a photo attaches to that photo
            # (don't silently drop it).
            if audios:
                replies = replies + await self._attach_photo_voice(phone, session, audios[0])
            return replies
        if audios:
            return await self._attach_photo_voice(phone, session, audios[0])
        # A text arrived during the photo step. If it looks like "done", advance now;
        # otherwise stay silent (the quiet-timer sends the button prompt) so we don't nag.
        if self._looks_done(inbound.body):
            return await self._advance_to_voice(phone, session)
        return []

    _DONE_WORDS = {
        "done", "finished", "finish", "complete", "completed", "that's all", "thats all",
        "all done", "no more", "next", "continue", "proceed", "yes", "yep", "ok", "okay",
    }

    @classmethod
    def _looks_done(cls, text: str | None) -> bool:
        t = (text or "").strip().lower().strip(".!?")
        return t in cls._DONE_WORDS

    async def _advance_to_voice(self, phone, session) -> list[OutboundAction]:
        """Move from the photo step to the closing voice note. Returns the reply action
        (does not call the lock-guarded timer path, to avoid re-entrant locking)."""
        if len(session.approved_photos) < PHOTO_MIN:
            self._reset_photo_timer(phone)
            return [OutboundAction(text="Please send at least one photo before we continue.")]
        self._cancel_photo_timer(phone)
        self._photo_hashes.pop(phone, None)
        await self.repo.update_session(session.session_id, current_state=State.VOICE)
        return [OutboundAction(text=(
            f"All {len(session.approved_photos)} photos received. "
            "Please record one closing voice note describing the overall scope of work."
        ))]

    async def _ingest_photos(self, phone, session, images) -> list[OutboundAction]:
        """CV-gate each photo, auto-caption the good ones (vision), and store structured
        evidence. Single photo -> caption + invite a voice note; bulk drop -> one summary."""
        seen = self._photo_hashes.setdefault(phone, [])
        photos = list(session.approved_photos)
        evidence = list(session.photo_evidence)
        replies: list[OutboundAction] = []
        good: list[tuple[int, str]] = []   # (photo number, caption) accepted this message

        for url, ct in images:
            res = await self.services.ingest_photo(url, ct, seen)
            if not res.get("ok"):
                reason = (res.get("reasons") or ["unusable"])[0]
                if reason == "duplicate":
                    replies.append(OutboundAction(text=(
                        "This photo appears to be a duplicate of one already received. "
                        "Please send a different angle."
                    )))
                else:
                    replies.append(OutboundAction(text=(
                        f"This photo appears {reason}. Please retake and resend it."
                    )))
                continue
            # Vision captioning is DEFERRED to the closing step (see _caption_pending) so photo
            # intake stays fast — otherwise per-photo LLM latency delays the count and desyncs
            # the quiet-timer. We store the evidence record now with an empty caption.
            evidence.append({
                "url": res["url"],
                "caption": "",
                "damage_types": [],
                "supports_codes": [],
                "quality": None,
                "claim_relevance": None,
                "voice_note_url": None,
                "transcript": None,
            })
            photos.append(res["url"])
            seen.append(res["dhash"])
            good.append((len(photos), ""))

        if len(photos) != len(session.approved_photos):
            await self.repo.update_session(
                session.session_id, approved_photos=photos, photo_evidence=evidence)
            session.approved_photos = photos
            session.photo_evidence = evidence

        # In lean mode we stay silent on good photos (evidence is still captured above);
        # only bad-photo callouts and the final advance message are sent.
        if not self.lean_photos:
            if len(good) == 1:
                num, caption = good[0]
                line = f"📷 Photo {num} saved"
                if caption:
                    line += f" — {caption}"
                line += ".\n🎙️ Add a voice note about this photo, or just send the next one."
                replies.append(OutboundAction(text=line))
            elif len(good) > 1:
                replies.append(OutboundAction(text=(
                    f"📷 Saved {len(good)} photos (total {len(photos)}). Going forward, send them "
                    "one at a time so I can note each one — or add a voice note for the last photo."
                )))

        if len(photos) >= PHOTO_MAX:
            self._cancel_photo_timer(phone)
            self._photo_hashes.pop(phone, None)
            await self.repo.update_session(session.session_id, current_state=State.VOICE)
            replies.append(OutboundAction(text=(
                f"That is the maximum of {len(photos)} photos. "
                "Please record one closing voice note describing the overall scope of work."
            )))
            return replies

        self._reset_photo_timer(phone)
        return replies

    async def _attach_photo_voice(self, phone, session, audio) -> list[OutboundAction]:
        """Attach an optional voice note to the most recent photo that has none yet."""
        if not session.photo_evidence:
            self._reset_photo_timer(phone)
            return [OutboundAction(text=(
                "Please send a photo first, then add a voice note to describe it."
            ))]
        url, ct = audio
        stored = await self.services.store_media(url, ct)
        transcript = await self.services.transcribe(stored)
        evidence = list(session.photo_evidence)
        target = next((i for i in range(len(evidence) - 1, -1, -1)
                       if not evidence[i].get("voice_note_url")), len(evidence) - 1)
        evidence[target] = {**evidence[target], "voice_note_url": stored, "transcript": transcript}
        await self.repo.update_session(session.session_id, photo_evidence=evidence)
        session.photo_evidence = evidence
        self._reset_photo_timer(phone)
        # Stay silent after a voice note in lean mode — the quiet-timer nudge is the only
        # message the foreman gets during the photo step.
        if self.lean_photos:
            return []
        return [OutboundAction(text=(
            f"🎙️ Voice note added to photo {target + 1}. Send the next photo, or I'll continue "
            "when you're done."
        ))]

    @staticmethod
    def _augment_transcript(closing: str, evidence: list[dict]) -> str:
        """Fold per-photo captions + per-photo voice notes into the closing transcript so the
        extractor sees the full evidence picture, not just the closing summary."""
        notes: list[str] = []
        for i, e in enumerate(evidence, start=1):
            parts = []
            if e.get("caption"):
                parts.append(e["caption"])
            if e.get("damage_types"):
                parts.append("damage: " + ", ".join(e["damage_types"]))
            if e.get("supports_codes"):
                parts.append("candidate codes: " + ", ".join(e["supports_codes"]))
            if e.get("transcript"):
                parts.append(f'foreman note: {e["transcript"]}')
            if parts:
                notes.append(f"Photo {i}: " + "; ".join(parts))
        segments = [closing or ""]
        if notes:
            segments.append("Per-photo evidence:\n" + "\n".join(notes))
        return "\n\n".join(s for s in segments if s).strip()

    @staticmethod
    def _link_evidence(items: list[dict], evidence: list[dict]) -> list[dict]:
        """Attach the supporting photo URLs to each line item (photo -> line-item linkage)."""
        for item in items:
            code = (item.get("code") or "").strip().upper()
            if not code:
                continue
            urls = [e["url"] for e in evidence
                    if code in [c.strip().upper() for c in (e.get("supports_codes") or [])]]
            if urls:
                item["photo_urls"] = urls
        return items

    # --- Photo quiet-timer (single worker; durable scheduler needed to scale) ----

    def _reset_photo_timer(self, phone: str) -> None:
        if not self.auto_advance:
            return
        self._cancel_photo_timer(phone)
        self._photo_timers[phone] = asyncio.create_task(self._photo_countdown(phone))

    def _cancel_photo_timer(self, phone: str) -> None:
        task = self._photo_timers.pop(phone, None)
        if task:
            task.cancel()

    async def _photo_countdown(self, phone: str) -> None:
        try:
            await asyncio.sleep(PHOTO_QUIET_SECONDS)
            crew = await self.repo.get_crew_by_phone(phone)
            session = await self.repo.get_active_session(crew.crew_id) if crew else None
            if not session or session.current_state != State.PHOTOS:
                return
            # After the quiet gap with no new photo/voice, send ONE button prompt so the
            # foreman can add more or continue without typing.
            n = len(session.approved_photos)
            self.sender.send_template(
                f"whatsapp:{phone}", "codeverity_photos_done", {"1": str(n)},
            )
            await asyncio.sleep(PHOTO_GRACE_SECONDS)
            await self._finish_photos(phone)
        except asyncio.CancelledError:
            pass

    async def _finish_photos(self, phone: str) -> None:
        """Advance from photos to the voice step. Called by the timer (or directly in tests)."""
        # Take the same per-phone lock as handle() so the auto-advance can't fire between a
        # photo webhook appending and committing (live runs only; tests call directly).
        if not self.auto_advance:
            return await self._finish_photos_inner(phone)
        async with self._locks.setdefault(phone, asyncio.Lock()):
            return await self._finish_photos_inner(phone)

    async def _finish_photos_inner(self, phone: str) -> None:
        crew = await self.repo.get_crew_by_phone(phone)
        session = await self.repo.get_active_session(crew.crew_id) if crew else None
        if not session or session.current_state != State.PHOTOS:
            return
        to = f"whatsapp:{phone}"
        if len(session.approved_photos) < PHOTO_MIN:
            self.sender.send_text(to, "Please send at least one photo before we continue.")
            self._reset_photo_timer(phone)
            return
        n = len(session.approved_photos)
        await self.repo.update_session(session.session_id, current_state=State.VOICE)
        self._cancel_photo_timer(phone)
        self._photo_hashes.pop(phone, None)
        self.sender.send_text(
            to, f"All {n} photos received. Please record one closing voice note describing "
            "the overall scope of work.")

    # --- State 4/5: voice note -> extraction -> confirm -------------------------

    async def _on_voice(self, inbound, crew, session) -> list[OutboundAction]:
        # Late photo after we advanced — re-open the photo step and append it (forgiving).
        if any((ct or "").startswith("image") for ct in inbound.media_content_types):
            await self.repo.update_session(session.session_id, current_state=State.PHOTOS)
            session.current_state = State.PHOTOS
            return await self._on_photos(inbound, crew, session)
        if inbound.num_media > 0:
            audio = await self.services.store_media(inbound.media_urls[0], inbound.media_content_types[0])
            transcript = await self.services.transcribe(audio)
            # Run the deferred per-photo vision captions now (kept off the fast intake path),
            # then extract against the closing note + every caption/voice note, and link each
            # line item back to the photos that evidence it.
            await self._caption_pending(session)
            augmented = self._augment_transcript(transcript, session.photo_evidence)
            items = await self.services.extract_line_items(augmented)
            items = self._link_evidence(items, session.photo_evidence)
            await self.repo.update_session(
                session.session_id,
                voice_note_url=audio,
                transcription_text=transcript,
                structured_line_items=items,
            )
            linked = sum(1 for it in items if it.get("photo_urls"))
            summary = f"We captured {len(items)} line item(s) from your inspection"
            if linked:
                summary += f", {linked} backed by photo evidence"
            summary += ". Would you like to submit this package?"
            return [OutboundAction(
                template="codeverity_voice_confirm",
                variables={"1": summary},
            )]
        if inbound.button_payload == "submit_package":
            return await self._submit(crew, session)
        if inbound.button_payload in {"rerecord_voice", "add_note"}:
            return [OutboundAction(template="codeverity_voice_confirm",
                                   variables={"1": "Please record your voice note now."})]
        return [OutboundAction(
            template="codeverity_voice_confirm",
            variables={"1": "Please record a voice note describing the scope, then tap Submit package."},
        )]

    async def _caption_pending(self, session) -> None:
        """Vision-caption any stored photos that don't have a caption yet (deferred from the
        intake loop for speed). Resilient: a caption failure leaves an empty caption."""
        evidence = list(session.photo_evidence)
        changed = False
        for e in evidence:
            if e.get("caption"):
                continue
            cap = await self.services.caption_photo(e["url"]) or {}
            if cap:
                e["caption"] = cap.get("caption") or ""
                e["damage_types"] = cap.get("damage_types") or []
                e["supports_codes"] = cap.get("supports_codes") or []
                e["quality"] = cap.get("quality")
                e["claim_relevance"] = cap.get("claim_relevance")
                changed = True
        if changed:
            await self.repo.update_session(session.session_id, photo_evidence=evidence)
            session.photo_evidence = evidence

    # --- State 6: bounty lock + PDF + CRM dispatch ------------------------------

    async def _submit(self, crew, session) -> list[OutboundAction]:
        job = await self._resolve_job(crew, session)
        citation = "Municipal code pending"
        if job:
            citation = job.municipal_code_summary or f"{job.city} municipal roofing code"

        pdf_payload = {
            "claim_number": (await self._claim_number(crew, session)),
            "address": job.property_address if job else "Address pending",
            "building_code_citation": citation,
            "line_items": session.structured_line_items,
            "photos": list(session.approved_photos),
            "photo_evidence": list(session.photo_evidence),
        }
        pdf_url = await self.services.compile_pdf(pdf_payload)

        # Bounty is NOT credited here. The office reviews and credits it on approval
        # (spec R8: earned on approval, not submission). CRM dispatch also happens on
        # operator approval (decision D1), not automatically from the field.
        await self.repo.update_session(session.session_id, pdf_url=pdf_url,
                                       current_state=State.COMPLETE)

        # Push the completed inspection to the live operator console for review.
        if self.on_event is not None:
            card = await self.repo.get_inspection(session.session_id)
            await self.on_event({"type": "inspection.completed", "data": card})

        return [OutboundAction(text=(
            "Your package has been submitted. Our office will review it and approve your "
            "$25 bounty shortly. Thank you."
        ))]

    async def _resolve_job(self, crew, session):
        if session.job_id and crew.company_id:
            for j in await self.repo.list_jobsites(crew.company_id):
                if j.job_id == session.job_id:
                    return j
        return None

    async def _claim_number(self, crew, session) -> str:
        if session.job_id and crew.company_id:
            jobs = await self.repo.list_jobsites(crew.company_id)
            for j in jobs:
                if j.job_id == session.job_id and j.claim_number:
                    return j.claim_number
        return "PENDING"
