"""Platform-wide AI usage analytics (Phase 12G).

Reads tenant Workspace usage from ``usage_daily_workspace`` (API-attributed
complete UTC days) plus bounded ``usage_events`` scans for interactive Chat
(``api_key_id IS NULL``) and partial-day edges. Does not modify quota
accounting or rollups.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from sqlalchemy import Date, cast, func, or_, select, text, union_all
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.db.models import UsageEvent
from app.documents.repository import ilike_contains_pattern
from app.identity.models import User
from app.platform_admin.authz import require_platform_admin_user
from app.platform_admin.repository import PlatformAdminRepository
from app.platform_admin.schemas import (
    PlatformUsageEventItemOut,
    PlatformUsageEventsResponse,
    PlatformUsageFamilyBreakdownOut,
    PlatformUsagePeakDayOut,
    PlatformUsageSourceBreakdownOut,
    PlatformUsageSummaryOut,
    PlatformUsageTrendPointOut,
    PlatformUsageTrendResponse,
    PlatformUsageWorkspaceItemOut,
    PlatformUsageWorkspacesResponse,
    PlatformWorkspaceUsageSummaryOut,
    PlatformWorkspaceUsageTrendResponse,
)
from app.usage.api_activity import WindowParts, _utc_date, _utc_day_start, split_usage_window
from app.usage.cost_metadata import sanitize_cost_metadata
from app.usage.event_tokens import billed_tokens_expr
from app.usage.models import UsageDailyWorkspace
from app.usage.rollup import utc_today
from app.usage.weights import OPERATION_FAMILY, OpenRouterFamily
from app.workspaces.models import Workspace, WorkspaceKind

SortField = Literal["billed_tokens"]


def parse_usage_sort_field(sort: str) -> SortField:
    normalized = sort.strip().lower()
    if normalized == "billed_tokens":
        return "billed_tokens"
    raise AppError(
        ErrorCategory.VALIDATION,
        "Unsupported usage workspaces sort field.",
        details={"sort": sort, "allowed": ["billed_tokens"]},
    )


@dataclass(frozen=True, slots=True)
class ResolvedRange:
    from_day: date
    to_day: date
    start_at: datetime
    end_at: datetime


class PlatformUsageAnalyticsService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.repo = PlatformAdminRepository(db)

    def _usage_workspace_filter(self, workspace_id: uuid.UUID | None = None):
        """Tenant-wide filter, or a single workspace regardless of kind."""
        clauses = [Workspace.deleted_at.is_(None)]
        if workspace_id is not None:
            clauses.append(Workspace.id == workspace_id)
        else:
            clauses.append(Workspace.kind == WorkspaceKind.TENANT.value)
        return clauses

    def resolve_range(
        self,
        *,
        from_day: date | None,
        to_day: date | None,
    ) -> ResolvedRange:
        today = utc_today()
        end_day = to_day or today
        if end_day > today:
            end_day = today
        if from_day is None:
            from_day = end_day - timedelta(days=int(self.settings.usage_history_default_days) - 1)
        if from_day > end_day:
            raise AppError(
                ErrorCategory.VALIDATION,
                "Invalid usage date range.",
                details={"from": from_day.isoformat(), "to": end_day.isoformat()},
            )
        span_days = (end_day - from_day).days + 1
        if span_days > int(self.settings.usage_history_max_days):
            raise AppError(
                ErrorCategory.VALIDATION,
                "Usage date range exceeds the allowed history window.",
                details={"max_days": int(self.settings.usage_history_max_days)},
            )
        start_at = datetime(from_day.year, from_day.month, from_day.day, tzinfo=UTC)
        end_at = datetime(end_day.year, end_day.month, end_day.day, tzinfo=UTC) + timedelta(days=1)
        return ResolvedRange(from_day=from_day, to_day=end_day, start_at=start_at, end_at=end_at)

    def sliding_range(self, *, hours: int | None = None, days: int | None = None) -> ResolvedRange:
        end = datetime.now(UTC)
        if days is not None:
            start = end - timedelta(days=days)
        elif hours is not None:
            start = end - timedelta(hours=hours)
        else:
            start = end - timedelta(days=30)
        return ResolvedRange(
            from_day=_utc_date(start),
            to_day=_utc_date(end),
            start_at=start,
            end_at=end,
        )

    def _event_billed_tokens(self, event: UsageEvent) -> int:
        meta = event.cost_metadata or {}
        billed = meta.get("billed_tokens")
        if billed is not None:
            return int(billed)
        return int((event.input_tokens or 0) + (event.output_tokens or 0))

    def _window_parts(self, resolved: ResolvedRange) -> WindowParts:
        from app.usage.api_activity import _Window

        custom = _Window(key="custom", start=resolved.start_at, end=resolved.end_at)
        return split_usage_window(custom)

    def _rollup_billed(
        self,
        *,
        complete_days: tuple[date, ...],
        workspace_id: uuid.UUID | None = None,
    ) -> int:
        if not complete_days:
            return 0
        stmt = (
            select(func.coalesce(func.sum(UsageDailyWorkspace.billed_tokens), 0))
            .select_from(UsageDailyWorkspace)
            .join(Workspace, Workspace.id == UsageDailyWorkspace.workspace_id)
            .where(
                UsageDailyWorkspace.day.in_(complete_days),
                *self._usage_workspace_filter(workspace_id),
            )
        )
        return int(self.db.scalar(stmt) or 0)

    def _events_billed(
        self,
        *,
        start: datetime,
        end: datetime,
        workspace_id: uuid.UUID | None = None,
        api_key_only: bool | None = None,
        family: str | None = None,
        operation_type: str | None = None,
        api_key_id: uuid.UUID | None = None,
    ) -> int:
        billed = billed_tokens_expr()
        stmt = (
            select(func.coalesce(func.sum(billed), 0))
            .select_from(UsageEvent)
            .join(Workspace, Workspace.id == UsageEvent.workspace_id)
            .where(
                UsageEvent.created_at >= start,
                UsageEvent.created_at < end,
                *self._usage_workspace_filter(workspace_id),
            )
        )
        if api_key_only is True:
            stmt = stmt.where(UsageEvent.api_key_id.is_not(None))
        elif api_key_only is False:
            stmt = stmt.where(UsageEvent.api_key_id.is_(None))
        if api_key_id is not None:
            stmt = stmt.where(UsageEvent.api_key_id == api_key_id)
        if operation_type:
            stmt = stmt.where(UsageEvent.operation_type == operation_type)
        if family:
            stmt = stmt.where(self._family_predicate(family))
        return int(self.db.scalar(stmt) or 0)

    def _family_predicate(self, family: str):
        allowed_ops = [
            op for op, mapped in OPERATION_FAMILY.items() if mapped.value == family
        ]
        meta_family = UsageEvent.cost_metadata["family"].astext == family
        if allowed_ops:
            return or_(meta_family, UsageEvent.operation_type.in_(allowed_ops))
        return meta_family

    def _total_billed_simple(
        self,
        resolved: ResolvedRange,
        *,
        workspace_id: uuid.UUID | None = None,
    ) -> int:
        """Hybrid rollup + bounded raw scan without double counting."""
        parts = self._window_parts(resolved)
        total = self._rollup_billed(complete_days=parts.complete_days, workspace_id=workspace_id)
        for day in parts.complete_days:
            day_start = _utc_day_start(day)
            day_end = day_start + timedelta(days=1)
            total += self._events_billed(
                start=day_start,
                end=day_end,
                workspace_id=workspace_id,
                api_key_only=False,
            )
        for range_start, range_end in parts.partial_ranges:
            total += self._events_billed(
                start=range_start,
                end=range_end,
                workspace_id=workspace_id,
                api_key_only=None,
            )
        return total

    def active_workspaces(self, resolved: ResolvedRange) -> int:
        return len(self._active_workspace_ids(resolved))

    def _active_workspace_ids(self, resolved: ResolvedRange) -> set[uuid.UUID]:
        billed = billed_tokens_expr()
        parts = self._window_parts(resolved)
        ids: set[uuid.UUID] = set()

        if parts.complete_days:
            ids.update(
                self.db.scalars(
                    select(UsageDailyWorkspace.workspace_id)
                    .join(Workspace, Workspace.id == UsageDailyWorkspace.workspace_id)
                    .where(
                        UsageDailyWorkspace.day.in_(parts.complete_days),
                        UsageDailyWorkspace.billed_tokens > 0,
                        *self._usage_workspace_filter(),
                    )
                    .distinct()
                ).all()
            )

        for day in parts.complete_days:
            day_start = _utc_day_start(day)
            day_end = day_start + timedelta(days=1)
            ids.update(
                self.db.scalars(
                    select(UsageEvent.workspace_id)
                    .join(Workspace, Workspace.id == UsageEvent.workspace_id)
                    .where(
                        UsageEvent.created_at >= day_start,
                        UsageEvent.created_at < day_end,
                        billed > 0,
                        UsageEvent.api_key_id.is_(None),
                        *self._usage_workspace_filter(),
                    )
                    .distinct()
                ).all()
            )
            ids.update(
                self.db.scalars(
                    select(UsageEvent.workspace_id)
                    .join(Workspace, Workspace.id == UsageEvent.workspace_id)
                    .where(
                        UsageEvent.created_at >= day_start,
                        UsageEvent.created_at < day_end,
                        billed > 0,
                        UsageEvent.api_key_id.is_not(None),
                        *self._usage_workspace_filter(),
                    )
                    .distinct()
                ).all()
            )

        for range_start, range_end in parts.partial_ranges:
            ids.update(
                self.db.scalars(
                    select(UsageEvent.workspace_id)
                    .join(Workspace, Workspace.id == UsageEvent.workspace_id)
                    .where(
                        UsageEvent.created_at >= range_start,
                        UsageEvent.created_at < range_end,
                        billed > 0,
                        *self._usage_workspace_filter(),
                    )
                    .distinct()
                ).all()
            )

        return ids

    def summary(
        self,
        actor: User,
        *,
        from_day: date | None,
        to_day: date | None,
    ) -> PlatformUsageSummaryOut:
        require_platform_admin_user(actor)
        resolved = self.resolve_range(from_day=from_day, to_day=to_day)
        total = self._total_billed_simple(resolved)
        span_days = (resolved.to_day - resolved.from_day).days + 1
        avg_daily = int(total / span_days) if span_days else 0
        trend = self._daily_buckets(resolved)
        peak = max(trend, key=lambda row: row.billed_tokens, default=None)
        families = self._family_breakdown(resolved)
        sources = self._source_breakdown(resolved)
        return PlatformUsageSummaryOut(
            from_day=resolved.from_day,
            to_day=resolved.to_day,
            total_billed_tokens=total,
            active_workspaces=self.active_workspaces(resolved),
            average_daily_billed_tokens=avg_daily,
            peak_day=(
                PlatformUsagePeakDayOut(day=peak.date, billed_tokens=peak.billed_tokens)
                if peak and peak.billed_tokens > 0
                else None
            ),
            families=families,
            sources=sources,
        )

    def trend(
        self,
        actor: User,
        *,
        from_day: date | None,
        to_day: date | None,
    ) -> PlatformUsageTrendResponse:
        require_platform_admin_user(actor)
        resolved = self.resolve_range(from_day=from_day, to_day=to_day)
        points = self._daily_buckets(resolved)
        return PlatformUsageTrendResponse(
            from_day=resolved.from_day,
            to_day=resolved.to_day,
            points=points,
        )

    def _active_workspace_counts_by_day(self, resolved: ResolvedRange) -> dict[date, int]:
        billed = billed_tokens_expr()
        parts = self._window_parts(resolved)
        by_day: dict[date, set[uuid.UUID]] = {}

        if parts.complete_days:
            rows = self.db.execute(
                select(UsageDailyWorkspace.day, UsageDailyWorkspace.workspace_id)
                .join(Workspace, Workspace.id == UsageDailyWorkspace.workspace_id)
                .where(
                    UsageDailyWorkspace.day.in_(parts.complete_days),
                    UsageDailyWorkspace.billed_tokens > 0,
                    *self._usage_workspace_filter(),
                )
            ).all()
            for day, ws_id in rows:
                by_day.setdefault(day, set()).add(ws_id)

        for day in parts.complete_days:
            day_start = _utc_day_start(day)
            day_end = day_start + timedelta(days=1)
            for ws_id in self.db.scalars(
                select(UsageEvent.workspace_id)
                .join(Workspace, Workspace.id == UsageEvent.workspace_id)
                .where(
                    UsageEvent.created_at >= day_start,
                    UsageEvent.created_at < day_end,
                    billed > 0,
                    UsageEvent.api_key_id.is_(None),
                    *self._usage_workspace_filter(),
                )
                .distinct()
            ).all():
                by_day.setdefault(day, set()).add(ws_id)
            for ws_id in self.db.scalars(
                select(UsageEvent.workspace_id)
                .join(Workspace, Workspace.id == UsageEvent.workspace_id)
                .where(
                    UsageEvent.created_at >= day_start,
                    UsageEvent.created_at < day_end,
                    billed > 0,
                    UsageEvent.api_key_id.is_not(None),
                    *self._usage_workspace_filter(),
                )
                .distinct()
            ).all():
                by_day.setdefault(day, set()).add(ws_id)

        for range_start, range_end in parts.partial_ranges:
            rows = self.db.execute(
                select(UsageEvent.workspace_id, UsageEvent.created_at)
                .join(Workspace, Workspace.id == UsageEvent.workspace_id)
                .where(
                    UsageEvent.created_at >= range_start,
                    UsageEvent.created_at < range_end,
                    billed > 0,
                    *self._usage_workspace_filter(),
                )
            ).all()
            for ws_id, created_at in rows:
                by_day.setdefault(_utc_date(created_at), set()).add(ws_id)

        return {day: len(ws_set) for day, ws_set in by_day.items()}

    def _daily_buckets(self, resolved: ResolvedRange) -> list[PlatformUsageTrendPointOut]:
        parts = self._window_parts(resolved)
        billed = billed_tokens_expr()
        by_day: dict[date, int] = {}

        if parts.complete_days:
            rollup_rows = self.db.execute(
                select(
                    UsageDailyWorkspace.day,
                    func.coalesce(func.sum(UsageDailyWorkspace.billed_tokens), 0),
                )
                .select_from(UsageDailyWorkspace)
                .join(Workspace, Workspace.id == UsageDailyWorkspace.workspace_id)
                .where(
                    UsageDailyWorkspace.day.in_(parts.complete_days),
                    *self._usage_workspace_filter(),
                )
                .group_by(UsageDailyWorkspace.day)
            ).all()
            for day, amount in rollup_rows:
                by_day[day] = by_day.get(day, 0) + int(amount or 0)

        for day in parts.complete_days:
            day_start = _utc_day_start(day)
            day_end = day_start + timedelta(days=1)
            interactive_total = self._events_billed(
                start=day_start,
                end=day_end,
                api_key_only=False,
            )
            if interactive_total:
                by_day[day] = by_day.get(day, 0) + interactive_total

        for range_start, range_end in parts.partial_ranges:
            partial_rows = self.db.execute(
                select(
                    cast(UsageEvent.created_at, Date),
                    func.coalesce(func.sum(billed), 0),
                )
                .select_from(UsageEvent)
                .join(Workspace, Workspace.id == UsageEvent.workspace_id)
                .where(
                    UsageEvent.created_at >= range_start,
                    UsageEvent.created_at < range_end,
                    *self._usage_workspace_filter(),
                )
                .group_by(cast(UsageEvent.created_at, Date))
            ).all()
            for day, amount in partial_rows:
                by_day[day] = by_day.get(day, 0) + int(amount or 0)

        active_counts = self._active_workspace_counts_by_day(resolved)
        points: list[PlatformUsageTrendPointOut] = []
        cursor = resolved.from_day
        while cursor <= resolved.to_day:
            points.append(
                PlatformUsageTrendPointOut(
                    date=cursor,
                    billed_tokens=by_day.get(cursor, 0),
                    active_workspaces=active_counts.get(cursor, 0),
                )
            )
            cursor += timedelta(days=1)
        return points

    def _family_breakdown(self, resolved: ResolvedRange) -> list[PlatformUsageFamilyBreakdownOut]:
        billed = billed_tokens_expr()
        rows = self.db.execute(
            select(
                func.coalesce(UsageEvent.cost_metadata["family"].astext, UsageEvent.operation_type),
                func.coalesce(func.sum(billed), 0),
            )
            .select_from(UsageEvent)
            .join(Workspace, Workspace.id == UsageEvent.workspace_id)
            .where(
                UsageEvent.created_at >= resolved.start_at,
                UsageEvent.created_at < resolved.end_at,
                *self._usage_workspace_filter(),
            )
            .group_by(text("1"))
        ).all()
        totals: dict[str, int] = {}
        for raw_family, amount in rows:
            family = self._normalize_family(str(raw_family or ""))
            totals[family] = totals.get(family, 0) + int(amount or 0)
        total = sum(totals.values()) or 0
        return [
            PlatformUsageFamilyBreakdownOut(
                family=family,
                billed_tokens=tokens,
                percentage=round((tokens / total) * 100, 2) if total else 0.0,
            )
            for family, tokens in sorted(totals.items(), key=lambda item: item[1], reverse=True)
        ]

    def _normalize_family(self, raw: str) -> str:
        if raw in {item.value for item in OpenRouterFamily}:
            return raw
        mapped = OPERATION_FAMILY.get(raw.strip())
        if mapped is not None:
            return mapped.value
        return OpenRouterFamily.CHAT.value

    def _source_breakdown(
        self,
        resolved: ResolvedRange,
        *,
        workspace_id: uuid.UUID | None = None,
    ) -> list[PlatformUsageSourceBreakdownOut]:
        parts = self._window_parts(resolved)
        api_total = self._rollup_billed(
            complete_days=parts.complete_days,
            workspace_id=workspace_id,
        )
        interactive_total = 0
        for day in parts.complete_days:
            day_start = _utc_day_start(day)
            day_end = day_start + timedelta(days=1)
            interactive_total += self._events_billed(
                start=day_start,
                end=day_end,
                workspace_id=workspace_id,
                api_key_only=False,
            )
        for range_start, range_end in parts.partial_ranges:
            api_total += self._events_billed(
                start=range_start,
                end=range_end,
                workspace_id=workspace_id,
                api_key_only=True,
            )
            interactive_total += self._events_billed(
                start=range_start,
                end=range_end,
                workspace_id=workspace_id,
                api_key_only=False,
            )
        total = api_total + interactive_total
        return [
            PlatformUsageSourceBreakdownOut(
                source=source,
                billed_tokens=amount,
                percentage=round((amount / total) * 100, 2) if total else 0.0,
            )
            for source, amount in (("api", api_total), ("interactive", interactive_total))
        ]

    def top_workspaces(
        self,
        actor: User,
        *,
        from_day: date | None,
        to_day: date | None,
        limit: int,
        offset: int,
        search: str | None,
        sort: SortField,
    ) -> PlatformUsageWorkspacesResponse:
        require_platform_admin_user(actor)
        resolved = self.resolve_range(from_day=from_day, to_day=to_day)
        billed = billed_tokens_expr()
        rollup = (
            select(
                UsageDailyWorkspace.workspace_id.label("workspace_id"),
                func.coalesce(func.sum(UsageDailyWorkspace.billed_tokens), 0).label("billed"),
            )
            .join(Workspace, Workspace.id == UsageDailyWorkspace.workspace_id)
            .where(
                UsageDailyWorkspace.day >= resolved.from_day,
                UsageDailyWorkspace.day <= resolved.to_day,
                *self._usage_workspace_filter(),
            )
            .group_by(UsageDailyWorkspace.workspace_id)
        ).subquery("rollup_usage")
        interactive = (
            select(
                UsageEvent.workspace_id.label("workspace_id"),
                func.coalesce(func.sum(billed), 0).label("billed"),
            )
            .join(Workspace, Workspace.id == UsageEvent.workspace_id)
            .where(
                UsageEvent.created_at >= resolved.start_at,
                UsageEvent.created_at < resolved.end_at,
                UsageEvent.api_key_id.is_(None),
                *self._usage_workspace_filter(),
            )
            .group_by(UsageEvent.workspace_id)
        ).subquery("interactive_usage")
        rollup_days = (
            select(
                UsageDailyWorkspace.workspace_id.label("workspace_id"),
                UsageDailyWorkspace.day.label("day"),
            )
            .join(Workspace, Workspace.id == UsageDailyWorkspace.workspace_id)
            .where(
                UsageDailyWorkspace.day >= resolved.from_day,
                UsageDailyWorkspace.day <= resolved.to_day,
                UsageDailyWorkspace.billed_tokens > 0,
                *self._usage_workspace_filter(),
            )
        )
        interactive_days = (
            select(
                UsageEvent.workspace_id.label("workspace_id"),
                cast(UsageEvent.created_at, Date).label("day"),
            )
            .join(Workspace, Workspace.id == UsageEvent.workspace_id)
            .where(
                UsageEvent.created_at >= resolved.start_at,
                UsageEvent.created_at < resolved.end_at,
                UsageEvent.api_key_id.is_(None),
                billed > 0,
                *self._usage_workspace_filter(),
            )
        )
        api_days = (
            select(
                UsageEvent.workspace_id.label("workspace_id"),
                cast(UsageEvent.created_at, Date).label("day"),
            )
            .join(Workspace, Workspace.id == UsageEvent.workspace_id)
            .where(
                UsageEvent.created_at >= resolved.start_at,
                UsageEvent.created_at < resolved.end_at,
                UsageEvent.api_key_id.is_not(None),
                billed > 0,
                *self._usage_workspace_filter(),
            )
        )
        usage_days = union_all(rollup_days, interactive_days, api_days).subquery("usage_days")
        active_days = (
            select(
                usage_days.c.workspace_id,
                func.count(func.distinct(usage_days.c.day)).label("active_days"),
            )
            .group_by(usage_days.c.workspace_id)
        ).subquery("active_days")
        combined = (
            select(
                Workspace.id,
                Workspace.name,
                Workspace.slug,
                Workspace.status,
                (
                    func.coalesce(rollup.c.billed, 0) + func.coalesce(interactive.c.billed, 0)
                ).label("billed_tokens"),
                func.coalesce(active_days.c.active_days, 0).label("active_days"),
            )
            .select_from(Workspace)
            .outerjoin(rollup, rollup.c.workspace_id == Workspace.id)
            .outerjoin(interactive, interactive.c.workspace_id == Workspace.id)
            .outerjoin(active_days, active_days.c.workspace_id == Workspace.id)
            .where(*self._usage_workspace_filter())
        )
        if search:
            pattern = ilike_contains_pattern(search)
            combined = combined.where(
                or_(Workspace.name.ilike(pattern), Workspace.slug.ilike(pattern))
            )
        combined = combined.where(
            (func.coalesce(rollup.c.billed, 0) + func.coalesce(interactive.c.billed, 0)) > 0
        )
        total = int(
            self.db.scalar(select(func.count()).select_from(combined.subquery("ranked"))) or 0
        )
        platform_total = self._total_billed_simple(resolved) or 0
        order = combined.order_by(text("billed_tokens DESC"), Workspace.name.asc())
        rows = self.db.execute(order.limit(limit).offset(offset)).all()
        workspace_ids = [row[0] for row in rows]
        subs = self.repo.subscription_summaries(workspace_ids)
        items: list[PlatformUsageWorkspaceItemOut] = []
        for row in rows:
            ws_id, name, slug, status, billed_tokens, active_days = row
            sub_pair = subs.get(ws_id)
            plan_code = plan_name = None
            if sub_pair is not None:
                _, plan = sub_pair
                plan_code = plan.code
                plan_name = plan.name
            items.append(
                PlatformUsageWorkspaceItemOut(
                    workspace_id=ws_id,
                    workspace_name=name,
                    workspace_slug=slug,
                    workspace_status=status,
                    billed_tokens=int(billed_tokens or 0),
                    percentage_of_platform_usage=(
                        round((int(billed_tokens or 0) / platform_total) * 100, 2)
                        if platform_total
                        else 0.0
                    ),
                    active_days=int(active_days or 0),
                    current_plan_code=plan_code,
                    current_plan_name=plan_name,
                )
            )
        return PlatformUsageWorkspacesResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            from_day=resolved.from_day,
            to_day=resolved.to_day,
            platform_total_billed_tokens=platform_total,
        )

    def list_events(
        self,
        actor: User,
        *,
        from_day: date,
        to_day: date,
        limit: int,
        offset: int,
        workspace_id: uuid.UUID | None,
        family: str | None,
        operation_type: str | None,
        api_key_id: uuid.UUID | None,
    ) -> PlatformUsageEventsResponse:
        require_platform_admin_user(actor)
        resolved = self.resolve_range(from_day=from_day, to_day=to_day)
        stmt = (
            select(
                UsageEvent,
                Workspace.name,
                Workspace.slug,
            )
            .join(Workspace, Workspace.id == UsageEvent.workspace_id)
            .where(
                UsageEvent.created_at >= resolved.start_at,
                UsageEvent.created_at < resolved.end_at,
                *self._usage_workspace_filter(workspace_id),
            )
        )
        if family:
            stmt = stmt.where(self._family_predicate(family))
        if operation_type:
            stmt = stmt.where(UsageEvent.operation_type == operation_type)
        if api_key_id is not None:
            stmt = stmt.where(UsageEvent.api_key_id == api_key_id)
        total = int(
            self.db.scalar(select(func.count()).select_from(stmt.subquery("usage_events_filtered")))
            or 0
        )
        rows = self.db.execute(
            stmt.order_by(UsageEvent.created_at.desc(), UsageEvent.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        items = [
            PlatformUsageEventItemOut(
                id=event.id,
                created_at=event.created_at,
                workspace_id=event.workspace_id,
                workspace_name=ws_name,
                workspace_slug=ws_slug,
                user_id=event.user_id,
                expert_id=event.expert_id,
                api_key_id=event.api_key_id,
                family=self._normalize_family(
                    str((event.cost_metadata or {}).get("family") or event.operation_type or "")
                ),
                operation_type=event.operation_type,
                input_tokens=event.input_tokens,
                output_tokens=event.output_tokens,
                billed_tokens=self._event_billed_tokens(event),
                cost_metadata=sanitize_cost_metadata(event.cost_metadata) or {},
            )
            for event, ws_name, ws_slug in rows
        ]
        return PlatformUsageEventsResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            from_day=resolved.from_day,
            to_day=resolved.to_day,
        )

    def workspace_summary(
        self,
        actor: User,
        workspace_id: uuid.UUID,
        *,
        from_day: date | None,
        to_day: date | None,
    ) -> PlatformWorkspaceUsageSummaryOut:
        require_platform_admin_user(actor)
        workspace = self.repo.get_workspace(workspace_id)
        if workspace is None:
            raise AppError(ErrorCategory.WORKSPACE_NOT_FOUND, "Workspace not found.")
        resolved = self.resolve_range(from_day=from_day, to_day=to_day)
        total = self._total_billed_simple(resolved, workspace_id=workspace_id)
        return PlatformWorkspaceUsageSummaryOut(
            workspace_id=workspace.id,
            workspace_name=workspace.name,
            workspace_slug=workspace.slug,
            workspace_status=workspace.status,
            workspace_kind=workspace.kind,
            from_day=resolved.from_day,
            to_day=resolved.to_day,
            total_billed_tokens=total,
            families=self._family_breakdown_for_workspace(resolved, workspace_id),
            sources=self._source_breakdown(resolved, workspace_id=workspace_id),
        )

    def workspace_trend(
        self,
        actor: User,
        workspace_id: uuid.UUID,
        *,
        from_day: date | None,
        to_day: date | None,
    ) -> PlatformWorkspaceUsageTrendResponse:
        require_platform_admin_user(actor)
        workspace = self.repo.get_workspace(workspace_id)
        if workspace is None:
            raise AppError(ErrorCategory.WORKSPACE_NOT_FOUND, "Workspace not found.")
        resolved = self.resolve_range(from_day=from_day, to_day=to_day)
        points = self._daily_buckets_for_workspace(resolved, workspace_id)
        return PlatformWorkspaceUsageTrendResponse(
            workspace_id=workspace.id,
            from_day=resolved.from_day,
            to_day=resolved.to_day,
            points=points,
        )

    def _daily_buckets_for_workspace(
        self, resolved: ResolvedRange, workspace_id: uuid.UUID
    ) -> list[PlatformUsageTrendPointOut]:
        rollup_rows = self.db.execute(
            select(
                UsageDailyWorkspace.day,
                func.coalesce(func.sum(UsageDailyWorkspace.billed_tokens), 0),
            )
            .where(
                UsageDailyWorkspace.workspace_id == workspace_id,
                UsageDailyWorkspace.day >= resolved.from_day,
                UsageDailyWorkspace.day <= resolved.to_day,
            )
            .group_by(UsageDailyWorkspace.day)
        ).all()
        by_day = {row[0]: int(row[1] or 0) for row in rollup_rows}
        billed = billed_tokens_expr()
        interactive_rows = self.db.execute(
            select(cast(UsageEvent.created_at, Date), func.coalesce(func.sum(billed), 0))
            .where(
                UsageEvent.workspace_id == workspace_id,
                UsageEvent.created_at >= resolved.start_at,
                UsageEvent.created_at < resolved.end_at,
                UsageEvent.api_key_id.is_(None),
            )
            .group_by(cast(UsageEvent.created_at, Date))
        ).all()
        for day, amount in interactive_rows:
            by_day[day] = by_day.get(day, 0) + int(amount or 0)
        parts = self._window_parts(resolved)
        for range_start, range_end in parts.partial_ranges:
            partial_rows = self.db.execute(
                select(
                    cast(UsageEvent.created_at, Date),
                    func.coalesce(func.sum(billed_tokens_expr()), 0),
                )
                .select_from(UsageEvent)
                .where(
                    UsageEvent.workspace_id == workspace_id,
                    UsageEvent.created_at >= range_start,
                    UsageEvent.created_at < range_end,
                )
                .group_by(cast(UsageEvent.created_at, Date))
            ).all()
            for day, amount in partial_rows:
                by_day[day] = by_day.get(day, 0) + int(amount or 0)
        points: list[PlatformUsageTrendPointOut] = []
        cursor = resolved.from_day
        while cursor <= resolved.to_day:
            value = by_day.get(cursor, 0)
            points.append(
                PlatformUsageTrendPointOut(
                    date=cursor,
                    billed_tokens=value,
                    active_workspaces=1 if value > 0 else 0,
                )
            )
            cursor += timedelta(days=1)
        return points

    def _family_breakdown_for_workspace(
        self, resolved: ResolvedRange, workspace_id: uuid.UUID
    ) -> list[PlatformUsageFamilyBreakdownOut]:
        billed = billed_tokens_expr()
        rows = self.db.execute(
            select(
                func.coalesce(UsageEvent.cost_metadata["family"].astext, UsageEvent.operation_type),
                func.coalesce(func.sum(billed), 0),
            )
            .where(
                UsageEvent.workspace_id == workspace_id,
                UsageEvent.created_at >= resolved.start_at,
                UsageEvent.created_at < resolved.end_at,
            )
            .group_by(text("1"))
        ).all()
        totals: dict[str, int] = {}
        for raw_family, amount in rows:
            family = self._normalize_family(str(raw_family or ""))
            totals[family] = totals.get(family, 0) + int(amount or 0)
        total = sum(totals.values()) or 0
        return [
            PlatformUsageFamilyBreakdownOut(
                family=family,
                billed_tokens=tokens,
                percentage=round((tokens / total) * 100, 2) if total else 0.0,
            )
            for family, tokens in sorted(totals.items(), key=lambda item: item[1], reverse=True)
        ]

    def _source_breakdown_for_workspace(
        self, resolved: ResolvedRange, workspace_id: uuid.UUID
    ) -> list[PlatformUsageSourceBreakdownOut]:
        return self._source_breakdown(resolved, workspace_id=workspace_id)

    def period_total_billed(self, *, hours: int | None = None, days: int | None = None) -> int:
        resolved = self.sliding_range(hours=hours, days=days)
        return self._total_billed_simple(resolved)