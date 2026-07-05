"""Pydantic v2 models for UBOS Phase 0 + Phase 1."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _validate_email(v: Any) -> str:
    if not isinstance(v, str):
        raise ValueError("must be a string")
    s = v.strip().lower()
    if not re.match(r"^[a-z0-9!#$%&'*+/=?^_`{|}~.-]+@[a-z0-9-]+(\.[a-z0-9-]+)+$", s):
        raise ValueError("value is not a valid email address")
    return s


# Permissive email type that accepts reserved TLDs like `.test` (used by our
# seed accounts) while still enforcing basic shape.
Email = Annotated[str, BeforeValidator(_validate_email)]

# ── Phase 0 field types ──
FIELD_TYPES = (
    "text", "longtext", "richtext", "number", "currency",
    "date", "datetime", "boolean", "dropdown", "multi_select",
    "email", "phone", "url", "image", "file", "relation",
)
FieldType = Literal[
    "text", "longtext", "richtext", "number", "currency",
    "date", "datetime", "boolean", "dropdown", "multi_select",
    "email", "phone", "url", "image", "file", "relation",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


def strip_id(doc: dict | None) -> dict | None:
    if doc is None:
        return doc
    doc = dict(doc)
    if "_id" in doc:
        doc["id"] = doc.pop("_id")
    doc.pop("password_hash", None)
    return doc


# ─────────────────────── Entity Types ───────────────────────
class EntityTypeBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    key: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    name_singular: str = Field(..., min_length=1, max_length=120)
    name_plural: str = Field(..., min_length=1, max_length=120)
    icon: str | None = "Box"
    color: str | None = "#0f766e"
    description: str | None = Field(default=None, max_length=1000)


class EntityTypeCreate(EntityTypeBase):
    pass


class EntityTypeUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name_singular: str | None = None
    name_plural: str | None = None
    icon: str | None = None
    color: str | None = None
    description: str | None = None


class EntityType(EntityTypeBase):
    id: str = Field(default_factory=_uuid, alias="_id")
    org_id: str
    is_system: bool = False
    record_counter: int = 0
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    deleted_at: str | None = None
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


# ─────────────────────── Field Definitions ───────────────────────
class FieldDefBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    key: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(..., min_length=1, max_length=200)
    type: FieldType
    config: dict[str, Any] = Field(default_factory=dict)
    required: bool = False
    unique: bool = False
    order: int = 0
    group: str | None = None
    help_text: str | None = None


class FieldDefCreate(FieldDefBase):
    pass


class FieldDefUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    label: str | None = None
    config: dict[str, Any] | None = None
    required: bool | None = None
    unique: bool | None = None
    order: int | None = None
    group: str | None = None
    help_text: str | None = None


class FieldDef(FieldDefBase):
    id: str = Field(default_factory=_uuid, alias="_id")
    org_id: str
    entity_type_id: str
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    deleted_at: str | None = None
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class ReorderPayload(BaseModel):
    order: list[str]


# ─────────────────────── Records ───────────────────────
class RecordCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str | None = None
    description: str | None = None
    fields: dict[str, Any] = Field(default_factory=dict)
    category_ids: list[str] = Field(default_factory=list)
    tag_ids: list[str] = Field(default_factory=list)


class RecordUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str | None = None
    description: str | None = None
    fields: dict[str, Any] | None = None
    category_ids: list[str] | None = None
    tag_ids: list[str] | None = None


class Record(BaseModel):
    id: str = Field(default_factory=_uuid, alias="_id")
    org_id: str
    entity_type_id: str
    title: str | None = None
    description: str | None = None
    fields: dict[str, Any] = Field(default_factory=dict)
    category_ids: list[str] = Field(default_factory=list)
    tag_ids: list[str] = Field(default_factory=list)
    record_number: str
    qr_payload: str | None = None
    search_text: str = ""
    version: int = 1
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    deleted_at: str | None = None
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


# ─────────────────────── Views ───────────────────────
class FilterCondition(BaseModel):
    field: str
    op: Literal["eq","ne","contains","gt","lt","gte","lte","between","in","not_in","is_empty","is_not_empty"]
    value: Any = None


class SortSpec(BaseModel):
    field: str
    dir: Literal["asc","desc"] = "asc"


class ViewCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    layout: Literal["table","gallery","grid","card","list"] = "table"
    filters: list[FilterCondition] = Field(default_factory=list)
    category_ids: list[str] = Field(default_factory=list)
    tag_ids: list[str] = Field(default_factory=list)
    q: str | None = None
    sort: list[SortSpec] = Field(default_factory=list)
    visible_fields: list[str] = Field(default_factory=list)
    column_widths: dict[str, int] = Field(default_factory=dict)
    is_shared: bool = False


class ViewUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str | None = None
    description: str | None = None
    layout: Literal["table","gallery","grid","card","list"] | None = None
    filters: list[FilterCondition] | None = None
    category_ids: list[str] | None = None
    tag_ids: list[str] | None = None
    q: str | None = None
    sort: list[SortSpec] | None = None
    visible_fields: list[str] | None = None
    column_widths: dict[str, int] | None = None
    is_shared: bool | None = None


class BulkAction(BaseModel):
    ids: list[str] = Field(min_length=1)
    action: Literal["assign_categories","assign_tags","delete"]
    payload: dict[str, Any] = Field(default_factory=dict)


class CommentPayload(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class RestorePayload(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


# ─────────────────────── Users, Orgs, Memberships ───────────────────────
class UserRegister(BaseModel):
    email: Email
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=120)


class UserLogin(BaseModel):
    email: Email
    password: str


class ChangePassword(BaseModel):
    current: str
    new: str = Field(min_length=8, max_length=128)


class ForgotPassword(BaseModel):
    email: Email


class ResetPassword(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class RefreshPayload(BaseModel):
    refresh_token: str


class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-z0-9-]+$")


class OrgUpdate(BaseModel):
    name: str | None = None
    settings: dict[str, Any] | None = None


class MemberRoleUpdate(BaseModel):
    role_name: Literal["owner", "admin", "editor", "viewer"]


class GoogleExchange(BaseModel):
    code: str


# ─────────────────────── Categories ───────────────────────
class CategoryBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(min_length=1, max_length=120)
    parent_id: str | None = None
    description: str | None = Field(default=None, max_length=1000)
    color: str | None = None
    icon: str | None = None


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str | None = None
    description: str | None = None
    color: str | None = None
    icon: str | None = None


class CategoryMove(BaseModel):
    new_parent_id: str | None = None


class CategoryReorder(BaseModel):
    new_order: int


# ─────────────────────── Tags ───────────────────────
class TagCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(min_length=1, max_length=80)
    entity_type_id: str | None = None
    color: str | None = None


class TagUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str | None = None
    color: str | None = None


# ─────────────────────── Relationship Definitions ───────────────────────
class RelDefCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    to_entity_type_id: str
    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    from_label: str = Field(min_length=1, max_length=120)
    to_label: str = Field(min_length=1, max_length=120)
    cardinality: Literal["one_to_one", "one_to_many", "many_to_many"] = "one_to_many"
    required: bool = False
    cascade_delete: bool = False
    description: str | None = None


class RelDefUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    from_label: str | None = None
    to_label: str | None = None
    cardinality: Literal["one_to_one", "one_to_many", "many_to_many"] | None = None
    required: bool | None = None
    cascade_delete: bool | None = None
    description: str | None = None


# ─────────────────────── Templates ───────────────────────
class TemplateApplyBody(BaseModel):
    conflict_policy: Literal["skip", "rename", "error"] = "skip"
    dry_run: bool = False
