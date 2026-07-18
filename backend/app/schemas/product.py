"""Product Catalog / OpenContent 合同（方案07 §19.5）。

冻结字段名与交付文档12一致；本文件只做请求/响应模型，不含业务。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class FileAssociation(BaseModel):
    associationId: str
    contentTypes: list[str] = Field(default_factory=list)
    extensions: list[str] = Field(default_factory=list)
    mimeTypes: list[str] = Field(default_factory=list)
    modes: list[str] = Field(default_factory=lambda: ["view"])
    adapterId: str = ""
    priority: int = 0
    readOnlyFormats: list[str] = Field(default_factory=list)


class ProductUiContractShell(BaseModel):
    useAppWindowFrame: bool = True
    sidebar: Literal["required", "optional", "none"] = "optional"
    toolbar: Literal["required", "optional", "none"] = "required"
    statusbar: Literal["required", "optional", "none"] = "none"


class ProductUiContract(BaseModel):
    """Frontend App UI Kit contract (mac-app-v1). Backend only stores/passthrough."""

    kit: Literal["mac-app-v1"] = "mac-app-v1"
    layout: Literal["finder", "document", "chat", "settings", "dashboard", "utility"]
    shell: ProductUiContractShell | None = None
    feedback: Literal["desktop-kit"] = "desktop-kit"
    density: Literal["comfortable", "compact"] = "comfortable"


class ProductManifestV1(BaseModel):
    schemaVersion: str = "ProductManifestV1"
    productId: str
    version: str = "1.0.0"
    displayName: str
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    category: str = ""
    iconSet: dict[str, Any] = Field(default_factory=dict)
    entryComponentKey: str
    workspaceKind: str = "DocumentWorkspace"
    uiContract: ProductUiContract | None = None
    visibility: dict[str, Any] = Field(default_factory=dict)
    permissionPolicy: dict[str, Any] = Field(default_factory=dict)
    requiredCapabilities: list[dict[str, Any]] = Field(default_factory=list)
    fileAssociations: list[FileAssociation] = Field(default_factory=list)
    createDocumentTypes: list[dict[str, Any]] = Field(default_factory=list)
    windowPolicy: dict[str, Any] = Field(default_factory=dict)
    activationPolicy: dict[str, Any] = Field(default_factory=dict)
    deepLinks: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    frameworkCompatibility: dict[str, Any] = Field(default_factory=dict)
    legacyAppKeys: list[str] = Field(default_factory=list)


class OpenContentSource(BaseModel):
    fileId: int | None = None
    packageId: int | None = None
    versionId: int | None = None
    deepLink: str | None = None


class OpenContentIntentV1(BaseModel):
    resolverVersion: str = "v1"
    requestId: str = ""
    source: OpenContentSource
    requestedMode: Literal["view", "edit"] = "view"
    preferredProductId: str | None = None
    activation: Literal["reuse-tab", "new-tab", "new-window"] = "reuse-tab"
    expectedVersionId: int | None = None
    lockToken: str | None = None
    origin: dict[str, Any] = Field(default_factory=dict)


class CreateDraftRequest(BaseModel):
    productId: str = "office"
    contentType: str = "document"
    extension: str = "docx"
    title: str = "未命名文档"
    adapterId: str | None = None


class ContentSaveRequest(BaseModel):
    expectedVersionId: int | None = None
    idempotencyKey: str | None = None
    lockToken: str | None = None
    content: dict[str, Any] | None = None
    summary: str | None = None
    # autosave=True 只新增 version，不产生 File（§19.6）
    autosave: bool = True


class ContentSaveAsRequest(BaseModel):
    expectedVersionId: int | None = None
    lockToken: str | None = None
    title: str
    parentFolderId: int | None = None
    content: dict[str, Any] | None = None


class ContentLockRequest(BaseModel):
    baseVersionId: int | None = None
    ttlSeconds: int = 300


class ContentLockRenewRequest(BaseModel):
    token: str
    ttlSeconds: int = 300


class ContentExportRequest(BaseModel):
    format: str | None = None


class ContentPublishRequest(BaseModel):
    targetFileId: int | None = None
    conflictPolicy: str = "create_version"

