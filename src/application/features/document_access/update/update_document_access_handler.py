from datetime import (
    datetime,
    timezone,
)

from src.application.common.exceptions.conflict_exception import (
    ConflictException,
)
from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.interfaces.file_storage import (
    FileStorage,
)
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.document_access.update.update_document_access_command import (
    UpdateDocumentAccessCommand,
)
from src.domain.enums.document_access_scope import (
    DocumentAccessScope,
)
from src.domain.repositories.department_repository import (
    DepartmentRepository,
)
from src.domain.repositories.document_department_repository import (
    DocumentDepartmentRepository,
)
from src.domain.repositories.document_digitization_repository import (
    DocumentDigitizationRepository,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)
from src.domain.repositories.document_version_repository import (
    DocumentVersionRepository,
)
from src.application.common.interfaces.rag_index_service import (
    RagIndexService,
)
from src.infrastructure.storage.object_key import (
    ObjectKeyBuilder,
)


class UpdateDocumentAccessHandler(
    RequestHandler[
        UpdateDocumentAccessCommand,
        bool,
    ]
):
    def __init__(
        self,
        document_repository: (
            DocumentRepository
        ),
        department_repository: (
            DepartmentRepository
        ),
        document_department_repository: (
            DocumentDepartmentRepository
        ),
        digitization_repository: (
            DocumentDigitizationRepository
        ),
        document_version_repository: (
            DocumentVersionRepository
        ),
        file_storage: FileStorage,
        object_key_builder: ObjectKeyBuilder,
        rag_index_service: (
            RagIndexService
        ),
        unit_of_work: UnitOfWork,
    ) -> None:
        self._document_repository = (
            document_repository
        )

        self._department_repository = (
            department_repository
        )

        self._document_department_repository = (
            document_department_repository
        )

        self._digitization_repository = (
            digitization_repository
        )

        self._document_version_repository = (
            document_version_repository
        )

        self._file_storage = file_storage

        self._object_key_builder = (
            object_key_builder
        )

        self._rag_index_service = (
            rag_index_service
        )

        self._unit_of_work = (
            unit_of_work
        )

    async def handle(
        self,
        request: (
            UpdateDocumentAccessCommand
        ),
    ) -> bool:
        document = await (
            self._document_repository
            .get_by_id(
                request.document_id
            )
        )

        if document is None:
            raise NotFoundException(
                "Document not found."
            )

        department_ids = list(
            dict.fromkeys(
                request.department_ids
            )
        )

        department_codes: list[
            str
        ] = []

        if (
            request.access_scope
            == (
                DocumentAccessScope
                .DEPARTMENT
            )
            and not department_ids
        ):
            raise ConflictException(
                "Department access "
                "requires at least "
                "one department."
            )

        for department_id in (
            department_ids
        ):
            department = await (
                self._department_repository
                .get_by_id(
                    department_id
                )
            )

            if department is None:
                raise NotFoundException(
                    "Department not found."
                )

            if not department.is_active:
                raise ConflictException(
                    "Department is inactive."
                )

            department_codes.append(
                department.code
                .strip()
                .upper()
            )

        if (
            request.access_scope
            == DocumentAccessScope.PUBLIC
        ):
            department_ids = []
            department_codes = []

        document.access_scope = (
            request.access_scope
        )

        document.updated_at = (
            datetime.now(
                timezone.utc
            )
        )

        await (
            self._document_repository
            .update(document)
        )

        await (
            self
            ._document_department_repository
            .replace_departments(
                document_id=(
                    document.id
                ),
                department_ids=(
                    department_ids
                ),
            )
        )

        allowed_units = (
            ["*"]
            if (
                request.access_scope
                == (
                    DocumentAccessScope
                    .PUBLIC
                )
            )
            else department_codes
        )

        await (
            self._digitization_repository
            .update_document_access_metadata(
                document_id=(
                    document.id
                ),
                access_scope=(
                    document
                    .access_scope
                    .value
                ),
                allowed_units=(
                    allowed_units
                ),
            )
        )

        await (
            self._unit_of_work
            .save_changes()
        )

        # ─── Phase 2: R2 mirror ──────────────────────────────────────
        # When the tenant segment implied by the new access_scope differs
        # from the one encoded in the current R2 object_key, we must copy
        # the object to the new key and update the DB reference.  We do
        # this AFTER the Neon commit so that the DB is always consistent
        # (the sweep script can recover any R2 drift later).
        #
        # Steps:
        #   1. Resolve the first bound department code (for DEPARTMENT scope).
        #   2. Fetch all versions for the document.
        #   3. For each version whose key would change:
        #        a. Pre-flight: old_key must exist, new_key must be absent.
        #        b. Server-side copy (no local download).
        #        c. Update document_versions.object_key in DB.
        #   4. The old key is kept in R2 — sweep_r2_orphans.py cleans it up.

        first_dept = (
            department_codes[0].lower()
            if department_codes
            else None
        )

        versions = await (
            self._document_version_repository
            .list_by_document_id(
                request.document_id
            )
        )

        for version in versions:
            new_key = (
                self._object_key_builder
                .for_version(
                    document_number=(
                        document.document_number
                    ),
                    version_number=(
                        version.version_number
                    ),
                    tenant_code=first_dept,
                    access_scope=(
                        document.access_scope.value
                    ),
                )
            )

            if new_key == version.object_key:
                continue

            old_key = version.object_key

            # Pre-flight: source must exist in storage. Without it the
            # operation cannot complete, so we abort with 409 BEFORE
            # we touch Neon. (Neon has already been committed in the
            # previous phase, so the rollback story is to flip the
            # DB rows back via ops/sync_r2_for_access_change.py.)
            old_meta = await (
                self._file_storage
                .head_object(old_key)
            )
            if old_meta is None:
                raise ConflictException(
                    f"Cannot change access scope: "
                    f"source PDF not found in storage "
                    f"(key={old_key}). "
                    f"Restore the file before retrying."
                )

            new_meta = await (
                self._file_storage
                .head_object(new_key)
            )

            # Destination may already exist (e.g. we are migrating
            # back to PUBLIC after a previous DEPARTMENT round-trip;
            # or the pre-reset state left a same-name orphan in R2).
            # Two cases:
            #   * Same content (size + ETag match) → already aligned,
            #     skip the copy, just re-point the DB.
            #   * Different content (different ETag) → another
            #     document lives at this key. Refuse with 409 rather
            #     than overwriting somebody else's file.
            if new_meta is not None:
                same_etag = (
                    old_meta.get("ETag")
                    == new_meta.get("ETag")
                )
                same_size = (
                    old_meta.get("ContentLength")
                    == new_meta.get("ContentLength")
                )
                if same_etag or same_size:
                    # Already aligned (the same content lives at
                    # new_key from a prior round-trip). Update DB.
                    await (
                        self._document_repository
                        .update_object_key(
                            version_id=(
                                version.id
                            ),
                            new_key=new_key,
                        )
                    )
                    continue
                raise ConflictException(
                    f"Cannot change access scope: "
                    f"another document already occupies "
                    f"the target key in storage with "
                    f"different content (key={new_key})."
                )

            # New key absent; safe to copy. boto3's copy_object
            # server-side duplicates the bytes (no local download).
            await (
                self._file_storage
                .copy_object(
                    source_key=old_key,
                    dest_key=new_key,
                )
            )

            # Update DB so subsequent requests resolve the new key.
            await (
                self._document_repository
                .update_object_key(
                    version_id=version.id,
                    new_key=new_key,
                )
            )

        # ─── Phase 3: Qdrant payload sync ───────────────────────────
        # Runs after R2 so Qdrant payload reflects the correct tenant_id.
        await (
            self._rag_index_service
            .update_document_access(
                document_id=(
                    document.id
                ),
                access_scope=(
                    document.access_scope
                ),
                allowed_units=(
                    allowed_units
                ),
            )
        )

        return True