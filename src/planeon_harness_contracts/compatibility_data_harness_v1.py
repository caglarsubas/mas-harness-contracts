"""Clean-room compatibility envelope for the observed data.harness/v1 contracts."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from planeon_harness_contracts.canonical import canonical_json_bytes, canonical_sha256
from planeon_harness_contracts.errors import CompilationError


API_VERSION = "harness.planeon.ai/v1alpha1"
CANONICAL_KIND = "DataHarnessCompatibilityDocument"
CONVERSION_PROFILE = "data-harness-v1-lossless-envelope/v1"
MAPPING_SCHEMA_VERSION = "harness.planeon.ai/data-harness-v1-mappings/v1"
DEPRECATION_SCHEMA_VERSION = "harness.planeon.ai/data-harness-v1-deprecation/v1"
FIXTURE_SCHEMA_VERSION = "harness.planeon.ai/data-harness-v1-fixture/v1"
OBSERVATION_SHA256 = "sha256:5c559a6ef3d59fa40e74ab2fb36603752751f523249da884f8e0d8daa06cfe10"
SOURCE_REPOSITORY = "git@github.com:caglarsubas/data-source-harness.git"
SOURCE_COMMIT = "858281f4b845ffacfe05cdb2c40a402c237d4c54"
WARNING_CODES = (
    "LEGACY_DATA_HARNESS_V1_DEPRECATED",
    "MIGRATE_TO_HARNESS_PLANEON_AI_V1ALPHA1",
)
INTENTIONAL_LOSS_CODES = (
    "CANONICAL_COMPATIBILITY_METADATA_NOT_EMITTED_TO_LEGACY",
    "CANONICAL_STATE_VIEW_NOT_EMITTED_TO_LEGACY",
)
SUPPORT_WINDOW = MappingProxyType(
    {
        "status": "DEPRECATED",
        "firstSupportedRelease": "0.1.0",
        "supportedSeries": "0.x",
        "removalNotBeforeRelease": "1.0.0",
        "minimumNoticeDays": 180,
    }
)
SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class CompatibilityError(ValueError):
    """One deterministic compatibility refusal without tenant payload output."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class StateMapping:
    """One observed legacy enum and its stable canonical view tokens."""

    schema_pointer: str
    values: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ContractDefinition:
    """Distilled structural facts for one supported legacy contract."""

    slug: str
    schema_id: str
    schema_version: str
    source_path: str
    git_object: str
    source_sha256: str
    allowed_fields: tuple[str, ...]
    required_fields: tuple[str, ...]
    field_types: tuple[tuple[str, tuple[str, ...]], ...]
    const_fields: tuple[tuple[str, str], ...]
    enum_fields: tuple[tuple[str, tuple[str, ...]], ...]
    state_mappings: tuple[StateMapping, ...]


# Replaced mechanically from the merged, source-free MET-002 observation report.
CONTRACT_DEFINITIONS: tuple[ContractDefinition, ...] = (
    ContractDefinition(
        slug='action-preview',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/action-preview.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/action-preview.schema.json',
        git_object='2e2c2ee16657105fcfea04aeebc09457cac31075',
        source_sha256='303598f0660b8525c735876c93b307cb36d76aa308ea7fcadfbbe6114d3f6033',
        allowed_fields=('actionDigest', 'actionId', 'allowed', 'approvalRequired', 'createdAt', 'effects', 'expiresAt', 'policyDecisionId', 'policyDigest', 'previewId', 'schemaVersion'),
        required_fields=('actionDigest', 'actionId', 'allowed', 'approvalRequired', 'createdAt', 'effects', 'expiresAt', 'policyDecisionId', 'policyDigest', 'previewId', 'schemaVersion'),
        field_types=(
            ('actionDigest', ('string',)),
            ('actionId', ('string',)),
            ('allowed', ('boolean',)),
            ('approvalRequired', ('boolean',)),
            ('createdAt', ('string',)),
            ('effects', ('array',)),
            ('expiresAt', ('string',)),
            ('policyDecisionId', ('string',)),
            ('policyDigest', ('string',)),
            ('previewId', ('string',)),
            ('schemaVersion', ('string',)),
        ),
        const_fields=(('schemaVersion', 'data.harness/v1'),),
        enum_fields=(),
        state_mappings=(
        ),
    ),
    ContractDefinition(
        slug='bounded-query-plan',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/bounded-query-plan.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/bounded-query-plan.schema.json',
        git_object='6b5524737ef62e93d24d6c0a9293d922d3eb7947',
        source_sha256='cc91280adadb55efcd5c613c7c6acd3bfbf18925f0d853ceea6bf6963818893b',
        allowed_fields=('assetIds', 'deadlineMs', 'estimatedRows', 'fields', 'filters', 'limit', 'purpose', 'relationships', 'schemaVersion', 'sourceId'),
        required_fields=('assetIds', 'deadlineMs', 'estimatedRows', 'fields', 'filters', 'limit', 'purpose', 'relationships', 'schemaVersion', 'sourceId'),
        field_types=(
            ('assetIds', ('array',)),
            ('deadlineMs', ('integer',)),
            ('estimatedRows', ('integer',)),
            ('fields', ('object',)),
            ('filters', ('object',)),
            ('limit', ('integer',)),
            ('purpose', ('string',)),
            ('relationships', ('array',)),
            ('schemaVersion', ('string',)),
            ('sourceId', ('string',)),
        ),
        const_fields=(('schemaVersion', 'data.harness/v1'),),
        enum_fields=(),
        state_mappings=(
        ),
    ),
    ContractDefinition(
        slug='checkpoint-token',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/checkpoint-token.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/checkpoint-token.schema.json',
        git_object='3bf9b60c1d146fffb5add2119b9d35e8fc49ce59',
        source_sha256='1b4ee5e02cc4c9dcf36a7f0cde84aa146e18054383081d414aef1b99eb775536',
        allowed_fields=('connectorVersion', 'kind', 'observedAt', 'position', 'schemaVersion', 'sourceId', 'streamId'),
        required_fields=('connectorVersion', 'kind', 'observedAt', 'position', 'schemaVersion', 'sourceId', 'streamId'),
        field_types=(
            ('connectorVersion', ('string',)),
            ('kind', ('string',)),
            ('observedAt', ('string',)),
            ('position', ('string',)),
            ('schemaVersion', ('string',)),
            ('sourceId', ('string',)),
            ('streamId', ('string',)),
        ),
        const_fields=(('kind', 'CheckpointToken'), ('schemaVersion', 'data.harness/v1')),
        enum_fields=(),
        state_mappings=(
        ),
    ),
    ContractDefinition(
        slug='connector-worker-profile',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/connector-worker-profile.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/connector-worker-profile.schema.json',
        git_object='fbd3786d03ae5269717a7de4e65128d850aa7ce5',
        source_sha256='2328ce63f5abbb56e2506dc89f3cedb255743d580b3ecd2d59f24cacbef4bd7b',
        allowed_fields=('certificationStatus', 'connectorId', 'credentialReferences', 'entrypointDigest', 'imageDigest', 'limits', 'networkMode', 'runtimeMode', 'schemaVersion', 'workerId'),
        required_fields=('certificationStatus', 'connectorId', 'credentialReferences', 'entrypointDigest', 'imageDigest', 'limits', 'networkMode', 'runtimeMode', 'schemaVersion', 'workerId'),
        field_types=(
            ('certificationStatus', ('string',)),
            ('connectorId', ('string',)),
            ('credentialReferences', ('array',)),
            ('entrypointDigest', ('string',)),
            ('imageDigest', ('string', 'null')),
            ('limits', ('object',)),
            ('networkMode', ('string',)),
            ('runtimeMode', ('string',)),
            ('schemaVersion', ('string',)),
            ('workerId', ('string',)),
        ),
        const_fields=(('schemaVersion', 'data.harness/v1'),),
        enum_fields=(('certificationStatus', ('process-isolation-only', 'image-pinned')), ('networkMode', ('host', 'none', 'allowlist')), ('runtimeMode', ('process', 'container'))),
        state_mappings=(
        ),
    ),
    ContractDefinition(
        slug='coverage-statement',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/coverage-statement.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/coverage-statement.schema.json',
        git_object='0952d5555616909e505e233cd3f2a06f41b16524',
        source_sha256='27e41660bfe988ec984afa3bc271c835c62ec04c6b6dc08f018bf423469b75bb',
        allowed_fields=('excluded', 'expectedSources', 'generatedAt', 'included', 'kind', 'requestId', 'schemaVersion'),
        required_fields=('excluded', 'generatedAt', 'included', 'kind', 'requestId', 'schemaVersion'),
        field_types=(
            ('excluded', ('array',)),
            ('expectedSources', ('array',)),
            ('generatedAt', ('string',)),
            ('included', ('array',)),
            ('kind', ('string',)),
            ('requestId', ('string',)),
            ('schemaVersion', ('string',)),
        ),
        const_fields=(('kind', 'CoverageStatement'), ('schemaVersion', 'data.harness/v1')),
        enum_fields=(),
        state_mappings=(
        ),
    ),
    ContractDefinition(
        slug='cross-plane-evidence-set',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/cross-plane-evidence-set.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/cross-plane-evidence-set.schema.json',
        git_object='ff2c9dfe0bc5e8e70732a5aaa0fa0a4cc5aa3f33',
        source_sha256='d39e00f0349ea746f778efbc128ed77bb35f5665b80491b3a3c118efdb552534',
        allowed_fields=('combinedRuntimeAccepted', 'components', 'generatedAt', 'releaseSet', 'schemaVersion'),
        required_fields=('combinedRuntimeAccepted', 'components', 'generatedAt', 'releaseSet', 'schemaVersion'),
        field_types=(
            ('combinedRuntimeAccepted', ('boolean',)),
            ('components', ('array',)),
            ('generatedAt', ('string',)),
            ('releaseSet', ('string',)),
            ('schemaVersion', ('string',)),
        ),
        const_fields=(('schemaVersion', 'data.harness/v1'),),
        enum_fields=(),
        state_mappings=(
            StateMapping(schema_pointer='/$defs/claim/allOf/0/if/properties/status', values=(('passed', 'PASSED'), ('failed', 'FAILED'))),
            StateMapping(schema_pointer='/$defs/claim/allOf/1/if/properties/status', values=(('missing', 'MISSING'), ('not-applicable', 'NOT_APPLICABLE'))),
            StateMapping(schema_pointer='/$defs/claim/properties/status', values=(('missing', 'MISSING'), ('passed', 'PASSED'), ('failed', 'FAILED'), ('not-applicable', 'NOT_APPLICABLE'))),
        ),
    ),
    ContractDefinition(
        slug='data-batch',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/data-batch.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/data-batch.schema.json',
        git_object='aaf77198b1ef680d1f6fa8deaaca1d198f1796a8',
        source_sha256='d6effa86bf676a9fc630cf6b27c72373e19160947aaf827a8f88bbfa6177af62',
        allowed_fields=('batchKind', 'byteCount', 'kind', 'lineage', 'payload', 'rowCount', 'schemaVersion', 'sourceVersions'),
        required_fields=('batchKind', 'kind', 'lineage', 'payload', 'schemaVersion', 'sourceVersions'),
        field_types=(
            ('batchKind', ('string',)),
            ('byteCount', ('integer', 'null')),
            ('kind', ('string',)),
            ('lineage', ('array',)),
            ('payload', ()),
            ('rowCount', ('integer', 'null')),
            ('schemaVersion', ('string',)),
            ('sourceVersions', ('array',)),
        ),
        const_fields=(('kind', 'DataBatch'), ('schemaVersion', 'data.harness/v1')),
        enum_fields=(('batchKind', ('arrow', 'document', 'graph', 'event', 'binary')),),
        state_mappings=(
        ),
    ),
    ContractDefinition(
        slug='data-source-connector-profile',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/data-source-connector-profile.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/data-source-connector-profile.schema.json',
        git_object='224728dadb9c9829494c4db04fd9c90833c7bc30',
        source_sha256='7de0463d00af04389267a722d55cb25efbb2d79ceb8ac289af1d5a0bd348f898',
        allowed_fields=('authMethods', 'capabilities', 'connectorId', 'consistency', 'dataModels', 'kind', 'limits', 'runtimeMode', 'schemaVersion', 'sdkApi', 'version'),
        required_fields=('authMethods', 'capabilities', 'connectorId', 'consistency', 'dataModels', 'kind', 'limits', 'runtimeMode', 'schemaVersion', 'sdkApi', 'version'),
        field_types=(
            ('authMethods', ('array',)),
            ('capabilities', ('array',)),
            ('connectorId', ('string',)),
            ('consistency', ('object',)),
            ('dataModels', ('array',)),
            ('kind', ('string',)),
            ('limits', ('object',)),
            ('runtimeMode', ('string',)),
            ('schemaVersion', ('string',)),
            ('sdkApi', ('string',)),
            ('version', ('string',)),
        ),
        const_fields=(('kind', 'DataSourceConnectorProfile'), ('schemaVersion', 'data.harness/v1'), ('sdkApi', 'harness.connector/v1')),
        enum_fields=(('runtimeMode', ('process', 'container', 'wasm', 'remote')),),
        state_mappings=(
        ),
    ),
    ContractDefinition(
        slug='deployment-profile',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/deployment-profile.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/deployment-profile.schema.json',
        git_object='7d4751d82edb260498ec85487e5c015811b8228a',
        source_sha256='0ce0977f5df23bf1d07a96b3fecff2e276826ce43a69097f947864bd56b1b54b',
        allowed_fields=('allowedHosts', 'artifactMirrorRequired', 'dnsEnabled', 'externalTelemetry', 'kind', 'mode', 'profileId', 'schemaVersion'),
        required_fields=('allowedHosts', 'artifactMirrorRequired', 'dnsEnabled', 'externalTelemetry', 'kind', 'mode', 'profileId', 'schemaVersion'),
        field_types=(
            ('allowedHosts', ('array',)),
            ('artifactMirrorRequired', ('boolean',)),
            ('dnsEnabled', ('boolean',)),
            ('externalTelemetry', ('boolean',)),
            ('kind', ('string',)),
            ('mode', ('string',)),
            ('profileId', ('string',)),
            ('schemaVersion', ('string',)),
        ),
        const_fields=(('kind', 'DeploymentProfile'), ('schemaVersion', 'data.harness/v1')),
        enum_fields=(('mode', ('connected', 'self-hosted', 'air-gapped', 'local-laptop')),),
        state_mappings=(
            StateMapping(schema_pointer='/properties/mode', values=(('connected', 'CONNECTED'), ('self-hosted', 'SELF_HOSTED'), ('air-gapped', 'AIR_GAPPED'), ('local-laptop', 'LOCAL_LAPTOP'))),
        ),
    ),
    ContractDefinition(
        slug='disconnected-runtime-readiness',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/disconnected-runtime-readiness.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/disconnected-runtime-readiness.schema.json',
        git_object='5231d84eb1d1d357adb260c38a7298d80b860f60',
        source_sha256='418f56192c5e088641587183afb1bcacd54b7b8eb5f5b2b30d0d735d2077c5a8',
        allowed_fields=('artifactIntegrity', 'blockers', 'bundleDigest', 'deployed', 'imageDigestsResolved', 'mirrorVerified', 'schemaVersion', 'stakeholderAccepted', 'wheelhouseComplete', 'zeroEgressRuntimeVerified'),
        required_fields=('artifactIntegrity', 'blockers', 'bundleDigest', 'deployed', 'imageDigestsResolved', 'mirrorVerified', 'schemaVersion', 'stakeholderAccepted', 'wheelhouseComplete', 'zeroEgressRuntimeVerified'),
        field_types=(
            ('artifactIntegrity', ('boolean',)),
            ('blockers', ('array',)),
            ('bundleDigest', ('string',)),
            ('deployed', ('boolean',)),
            ('imageDigestsResolved', ('boolean',)),
            ('mirrorVerified', ('boolean',)),
            ('schemaVersion', ('string',)),
            ('stakeholderAccepted', ('boolean',)),
            ('wheelhouseComplete', ('boolean',)),
            ('zeroEgressRuntimeVerified', ('boolean',)),
        ),
        const_fields=(('schemaVersion', 'data.harness/v1'),),
        enum_fields=(),
        state_mappings=(
        ),
    ),
    ContractDefinition(
        slug='durable-action-record',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/durable-action-record.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/durable-action-record.schema.json',
        git_object='f55ed3ad2a78633877f64bd31738c867e23cf4c9',
        source_sha256='ba91aaf9ceb6fb2fbe422ffb50634fedb3f2e5ecae9781a081ccb32ad26a6322',
        allowed_fields=('actionDigest', 'actionId', 'attempts', 'idempotencyKey', 'journalDigest', 'policyDecisionId', 'receiptId', 'schemaVersion', 'sourceId', 'sourceVersion', 'startedAt', 'state', 'updatedAt'),
        required_fields=('actionDigest', 'actionId', 'attempts', 'idempotencyKey', 'journalDigest', 'policyDecisionId', 'receiptId', 'schemaVersion', 'sourceId', 'sourceVersion', 'startedAt', 'state', 'updatedAt'),
        field_types=(
            ('actionDigest', ('string',)),
            ('actionId', ('string',)),
            ('attempts', ('integer',)),
            ('idempotencyKey', ('string',)),
            ('journalDigest', ('string',)),
            ('policyDecisionId', ('string',)),
            ('receiptId', ('string', 'null')),
            ('schemaVersion', ('string',)),
            ('sourceId', ('string',)),
            ('sourceVersion', ('string', 'null')),
            ('startedAt', ('string',)),
            ('state', ('string',)),
            ('updatedAt', ('string',)),
        ),
        const_fields=(('schemaVersion', 'data.harness/v1'),),
        enum_fields=(('state', ('prepared', 'executing', 'executed', 'failed', 'reconciliation-required')),),
        state_mappings=(
            StateMapping(schema_pointer='/properties/state', values=(('prepared', 'PREPARED'), ('executing', 'EXECUTING'), ('executed', 'EXECUTED'), ('failed', 'FAILED'), ('reconciliation-required', 'RECONCILIATION_REQUIRED'))),
        ),
    ),
    ContractDefinition(
        slug='entity-redirect',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/entity-redirect.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/entity-redirect.schema.json',
        git_object='becdf6103454b1688df58b5d5d3ac9d6804babbb',
        source_sha256='a42f53b998f12916006a1c0c4c5e26e7574dc552f6423b464128fd4236217465',
        allowed_fields=('assertedAt', 'fromEntityId', 'kind', 'lineage', 'reason', 'redirectId', 'schemaVersion', 'toEntityId'),
        required_fields=('assertedAt', 'fromEntityId', 'kind', 'lineage', 'reason', 'redirectId', 'schemaVersion', 'toEntityId'),
        field_types=(
            ('assertedAt', ('string',)),
            ('fromEntityId', ('string',)),
            ('kind', ('string',)),
            ('lineage', ('array',)),
            ('reason', ('string',)),
            ('redirectId', ('string',)),
            ('schemaVersion', ('string',)),
            ('toEntityId', ('string',)),
        ),
        const_fields=(('kind', 'EntityRedirect'), ('schemaVersion', 'data.harness/v1')),
        enum_fields=(),
        state_mappings=(
        ),
    ),
    ContractDefinition(
        slug='freshness-observation',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/freshness-observation.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/freshness-observation.schema.json',
        git_object='910aee753b125b0a0bc11ec2eb24801f790408e7',
        source_sha256='3852082f9370193a74ff557b5cccb53d151e84ec3901ca5d51b8346590496bb5',
        allowed_fields=('assessment', 'assetId', 'observedAt', 'schemaVersion', 'sourceEventTime', 'sourceId', 'watermark'),
        required_fields=('assessment', 'assetId', 'observedAt', 'schemaVersion', 'sourceEventTime', 'sourceId', 'watermark'),
        field_types=(
            ('assessment', ('object',)),
            ('assetId', ('string',)),
            ('observedAt', ('string',)),
            ('schemaVersion', ('string',)),
            ('sourceEventTime', ('string',)),
            ('sourceId', ('string',)),
            ('watermark', ('string',)),
        ),
        const_fields=(('schemaVersion', 'data.harness/v1'),),
        enum_fields=(),
        state_mappings=(
        ),
    ),
    ContractDefinition(
        slug='industry-domain-pack-manifest',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/industry-domain-pack-manifest.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/industry-domain-pack-manifest.schema.json',
        git_object='2f4ec03aa5689f1014b210d9a25b51a14c8c074b',
        source_sha256='73281bf15fc5b74ac622bd5cb2c24cd8bc429ac31e474ef2cca04ca523654bf3',
        allowed_fields=('acceptanceScenarios', 'domains', 'industry', 'kind', 'mockDatasets', 'packId', 'schemaVersion', 'technologyExamples', 'version'),
        required_fields=('acceptanceScenarios', 'domains', 'industry', 'kind', 'mockDatasets', 'packId', 'schemaVersion', 'technologyExamples', 'version'),
        field_types=(
            ('acceptanceScenarios', ('array',)),
            ('domains', ('array',)),
            ('industry', ('string',)),
            ('kind', ('string',)),
            ('mockDatasets', ('array',)),
            ('packId', ('string',)),
            ('schemaVersion', ('string',)),
            ('technologyExamples', ('array',)),
            ('version', ('string',)),
        ),
        const_fields=(('kind', 'IndustryDomainPackManifest'), ('schemaVersion', 'data.harness/v1')),
        enum_fields=(),
        state_mappings=(
        ),
    ),
    ContractDefinition(
        slug='live-acceptance-campaign',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/live-acceptance-campaign.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/live-acceptance-campaign.schema.json',
        git_object='4ff4d3a220f6a3f7a0af0d4f827f79759779b1de',
        source_sha256='d051b33b2d836dcf795e0bf5cf89307e6e535007f49a24ff481029ec0d93be13',
        allowed_fields=('accepted', 'artifacts', 'blockers', 'campaignId', 'costBoundary', 'evidence', 'generatedAt', 'releaseSet', 'releaseSetDigest', 'schemaVersion', 'sources'),
        required_fields=('accepted', 'artifacts', 'blockers', 'campaignId', 'costBoundary', 'evidence', 'generatedAt', 'releaseSet', 'releaseSetDigest', 'schemaVersion', 'sources'),
        field_types=(
            ('accepted', ('boolean',)),
            ('artifacts', ('array',)),
            ('blockers', ('array',)),
            ('campaignId', ('string',)),
            ('costBoundary', ()),
            ('evidence', ('array',)),
            ('generatedAt', ('string',)),
            ('releaseSet', ('string',)),
            ('releaseSetDigest', ()),
            ('schemaVersion', ('string',)),
            ('sources', ('array',)),
        ),
        const_fields=(('schemaVersion', 'data.harness/v1'),),
        enum_fields=(),
        state_mappings=(
            StateMapping(schema_pointer='/$defs/evidence/properties/status', values=(('passed', 'PASSED'), ('failed', 'FAILED'))),
        ),
    ),
    ContractDefinition(
        slug='local-cross-plane-evidence',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/local-cross-plane-evidence.schema.json',
        schema_version='data.harness.local-cross-plane-evidence/v1',
        source_path='schemas/v1/local-cross-plane-evidence.schema.json',
        git_object='ae4206d805d9b28f27989fe5b6ede4cb50230d67',
        source_sha256='136218e272ae70434ff8130b7701b72340588eb55eacd76615d49d75105bd4aa',
        allowed_fields=('campaignId', 'checks', 'components', 'externalResourcesCreated', 'generatedAt', 'passed', 'rerank', 'runtimeReceipt', 'schemaVersion'),
        required_fields=('campaignId', 'checks', 'components', 'externalResourcesCreated', 'generatedAt', 'passed', 'rerank', 'runtimeReceipt', 'schemaVersion'),
        field_types=(
            ('campaignId', ('string',)),
            ('checks', ('array',)),
            ('components', ('array',)),
            ('externalResourcesCreated', ('array',)),
            ('generatedAt', ('string',)),
            ('passed', ('boolean',)),
            ('rerank', ('object',)),
            ('runtimeReceipt', ('object',)),
            ('schemaVersion', ('string',)),
        ),
        const_fields=(('schemaVersion', 'data.harness.local-cross-plane-evidence/v1'),),
        enum_fields=(),
        state_mappings=(
        ),
    ),
    ContractDefinition(
        slug='local-harness-runtime-evidence',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/local-harness-runtime-evidence.schema.json',
        schema_version='data.harness.local-harness-runtime-evidence/v1',
        source_path='schemas/v1/local-harness-runtime-evidence.schema.json',
        git_object='622b4ce766847998cce9a3cdc7c04fb82e14efda',
        source_sha256='66df7eacef52cbba66776d851b207cbffde3d00e5f63dbe5c21f6b9b25ba4518',
        allowed_fields=('artifactDigest', 'baseImageDigest', 'campaignId', 'checks', 'externalResourcesCreated', 'generatedAt', 'harnessVersion', 'networkMode', 'passed', 'revision', 'schemaVersion', 'sourceRecordCounts', 'wheelhouseDigest'),
        required_fields=('artifactDigest', 'baseImageDigest', 'campaignId', 'checks', 'externalResourcesCreated', 'generatedAt', 'harnessVersion', 'networkMode', 'passed', 'revision', 'schemaVersion', 'sourceRecordCounts', 'wheelhouseDigest'),
        field_types=(
            ('artifactDigest', ()),
            ('baseImageDigest', ()),
            ('campaignId', ('string',)),
            ('checks', ('array',)),
            ('externalResourcesCreated', ('array',)),
            ('generatedAt', ('string',)),
            ('harnessVersion', ('string',)),
            ('networkMode', ('string',)),
            ('passed', ('boolean',)),
            ('revision', ('string',)),
            ('schemaVersion', ('string',)),
            ('sourceRecordCounts', ('object',)),
            ('wheelhouseDigest', ()),
        ),
        const_fields=(('campaignId', 'phase7-white-goods-local-harness-runtime'), ('networkMode', 'compose-internal'), ('schemaVersion', 'data.harness.local-harness-runtime-evidence/v1')),
        enum_fields=(),
        state_mappings=(
        ),
    ),
    ContractDefinition(
        slug='local-image-lock',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/local-image-lock.schema.json',
        schema_version='data.harness.local-image-lock/v1',
        source_path='schemas/v1/local-image-lock.schema.json',
        git_object='cdfac4e35bb81617e3fe82377f39683759e8b565',
        source_sha256='cebdb2169a6975b26b300d6d0218d0869774dfeb91b6ff4214818ad51e3d422d',
        allowed_fields=('images', 'platform', 'schemaVersion'),
        required_fields=('images', 'platform', 'schemaVersion'),
        field_types=(
            ('images', ('array',)),
            ('platform', ()),
            ('schemaVersion', ('string',)),
        ),
        const_fields=(('schemaVersion', 'data.harness.local-image-lock/v1'),),
        enum_fields=(),
        state_mappings=(
        ),
    ),
    ContractDefinition(
        slug='local-source-evidence',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/local-source-evidence.schema.json',
        schema_version='data.harness.local-source-evidence/v1',
        source_path='schemas/v1/local-source-evidence.schema.json',
        git_object='58eca9ff7dcbdbd6466092a01755d6206d847240',
        source_sha256='e7ffdde7b76c1b4ed809cbd01fcd804d831f5577b15f5d99b459f8313851678a',
        allowed_fields=('campaignId', 'checks', 'dockerContext', 'dockerEndpointKind', 'externalResourcesCreated', 'generatedAt', 'passed', 'schemaVersion', 'sources'),
        required_fields=('campaignId', 'checks', 'dockerContext', 'dockerEndpointKind', 'externalResourcesCreated', 'generatedAt', 'passed', 'schemaVersion', 'sources'),
        field_types=(
            ('campaignId', ('string',)),
            ('checks', ('array',)),
            ('dockerContext', ('string',)),
            ('dockerEndpointKind', ('string',)),
            ('externalResourcesCreated', ('array',)),
            ('generatedAt', ('string',)),
            ('passed', ('boolean',)),
            ('schemaVersion', ('string',)),
            ('sources', ('array',)),
        ),
        const_fields=(('schemaVersion', 'data.harness.local-source-evidence/v1'),),
        enum_fields=(('dockerEndpointKind', ('unix', 'npipe')),),
        state_mappings=(
        ),
    ),
    ContractDefinition(
        slug='northbound-tool-catalog',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/northbound-tool-catalog.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/northbound-tool-catalog.schema.json',
        git_object='525535b850f35ad44b40b874c1c114ce55e4dd24',
        source_sha256='12dfc196abf1ae35d6319ab3657967e7c2f3742726bb2c95bca4f6a0feecb0b5',
        allowed_fields=('catalogDigest', 'protocolVersion', 'schemaVersion', 'tools'),
        required_fields=('catalogDigest', 'protocolVersion', 'schemaVersion', 'tools'),
        field_types=(
            ('catalogDigest', ('string',)),
            ('protocolVersion', ('string',)),
            ('schemaVersion', ('string',)),
            ('tools', ('array',)),
        ),
        const_fields=(('protocolVersion', 'data.harness.northbound/v1'), ('schemaVersion', 'data.harness/v1')),
        enum_fields=(),
        state_mappings=(
        ),
    ),
    ContractDefinition(
        slug='promotion-readiness',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/promotion-readiness.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/promotion-readiness.schema.json',
        git_object='d8c42a3f6df70d78e2aa78c6e3d0d328fb3c6bbe',
        source_sha256='1d74749b9af0f1bd6df699938eeb65a64ca69cfe96ffabd57b1c577adc2a635b',
        allowed_fields=('compatibility', 'evidence', 'readyForAdlcDecision', 'releaseSet', 'revision', 'schemaVersion'),
        required_fields=('compatibility', 'evidence', 'readyForAdlcDecision', 'releaseSet', 'revision', 'schemaVersion'),
        field_types=(
            ('compatibility', ('array',)),
            ('evidence', ('array',)),
            ('readyForAdlcDecision', ('boolean',)),
            ('releaseSet', ('string',)),
            ('revision', ('string',)),
            ('schemaVersion', ('string',)),
        ),
        const_fields=(('schemaVersion', 'data.harness/v1'),),
        enum_fields=(),
        state_mappings=(
            StateMapping(schema_pointer='/properties/evidence/items/properties/status', values=(('passed', 'PASSED'), ('failed', 'FAILED'), ('missing', 'MISSING'))),
        ),
    ),
    ContractDefinition(
        slug='protocol-profile-conformance',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/protocol-profile-conformance.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/protocol-profile-conformance.schema.json',
        git_object='54c02da581b17c87af94d9e5849d7944af7dc69a',
        source_sha256='0579230e75c9b20f9a4003a69356b1b338b0a3d2fcbc1b49f8b502d63f42edc9',
        allowed_fields=('checks', 'profileId', 'protocolVersion', 'schemaVersion', 'specification', 'upstreamSuite'),
        required_fields=('checks', 'profileId', 'protocolVersion', 'schemaVersion', 'specification', 'upstreamSuite'),
        field_types=(
            ('checks', ('array',)),
            ('profileId', ('string',)),
            ('protocolVersion', ('string',)),
            ('schemaVersion', ('string',)),
            ('specification', ('string',)),
            ('upstreamSuite', ('object',)),
        ),
        const_fields=(('schemaVersion', 'data.harness/v1'),),
        enum_fields=(),
        state_mappings=(
            StateMapping(schema_pointer='/properties/upstreamSuite/properties/status', values=(('not-run', 'NOT_RUN'), ('passed', 'PASSED'), ('failed', 'FAILED'))),
        ),
    ),
    ContractDefinition(
        slug='reference-lab-manifest',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/reference-lab-manifest.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/reference-lab-manifest.schema.json',
        git_object='bbdc7844c9452450ccdc5a596d14059ea13f662a',
        source_sha256='6a1bb8fd780f324c45b1c632769e0dd790413a2d99870e78b26a36363472ceda',
        allowed_fields=('acceptanceScenarios', 'connectors', 'datasets', 'deploymentProfiles', 'domain', 'industry', 'kind', 'labId', 'schemaVersion'),
        required_fields=('acceptanceScenarios', 'connectors', 'datasets', 'deploymentProfiles', 'domain', 'industry', 'kind', 'labId', 'schemaVersion'),
        field_types=(
            ('acceptanceScenarios', ('array',)),
            ('connectors', ('array',)),
            ('datasets', ('array',)),
            ('deploymentProfiles', ('array',)),
            ('domain', ('string',)),
            ('industry', ('string',)),
            ('kind', ('string',)),
            ('labId', ('string',)),
            ('schemaVersion', ('string',)),
        ),
        const_fields=(('kind', 'ReferenceLabManifest'), ('schemaVersion', 'data.harness/v1')),
        enum_fields=(),
        state_mappings=(
        ),
    ),
    ContractDefinition(
        slug='route-decision',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/route-decision.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/route-decision.schema.json',
        git_object='aa008c72e170ff49f404f3df2cf7775df0133e98',
        source_sha256='832b1f323bfabc3a219ffed30aa0a137eb7680d93d893d6c320386a9515910d3',
        allowed_fields=('reasonCodes', 'requestId', 'routes', 'schemaVersion', 'status', 'uncoveredConcepts'),
        required_fields=('reasonCodes', 'requestId', 'routes', 'schemaVersion', 'status', 'uncoveredConcepts'),
        field_types=(
            ('reasonCodes', ('array',)),
            ('requestId', ('string',)),
            ('routes', ('array',)),
            ('schemaVersion', ('string',)),
            ('status', ('string',)),
            ('uncoveredConcepts', ('array',)),
        ),
        const_fields=(('schemaVersion', 'data.harness/v1'),),
        enum_fields=(('status', ('selected', 'refused', 'escalation_required')),),
        state_mappings=(
            StateMapping(schema_pointer='/allOf/1/if/properties/status', values=(('refused', 'REFUSED'), ('escalation_required', 'ESCALATION_REQUIRED'))),
            StateMapping(schema_pointer='/properties/status', values=(('selected', 'SELECTED'), ('refused', 'REFUSED'), ('escalation_required', 'ESCALATION_REQUIRED'))),
        ),
    ),
    ContractDefinition(
        slug='semantic-assertion',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/semantic-assertion.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/semantic-assertion.schema.json',
        git_object='99a825eb9632cf7ea7874fc6c4e7311c6524128d',
        source_sha256='7c09fa5b8b804149ab8813ba23057831df5992c4b710e945e71bbb87abdae2a8',
        allowed_fields=('assertedAt', 'assertionId', 'confidence', 'kind', 'lineage', 'objectId', 'policyDigest', 'predicate', 'schemaVersion', 'subjectId', 'validFrom', 'validTo'),
        required_fields=('assertedAt', 'assertionId', 'confidence', 'kind', 'lineage', 'objectId', 'policyDigest', 'predicate', 'schemaVersion', 'subjectId', 'validFrom'),
        field_types=(
            ('assertedAt', ('string',)),
            ('assertionId', ('string',)),
            ('confidence', ('number',)),
            ('kind', ('string',)),
            ('lineage', ('array',)),
            ('objectId', ('string',)),
            ('policyDigest', ('string',)),
            ('predicate', ('string',)),
            ('schemaVersion', ('string',)),
            ('subjectId', ('string',)),
            ('validFrom', ('string',)),
            ('validTo', ('string', 'null')),
        ),
        const_fields=(('kind', 'SemanticAssertion'), ('schemaVersion', 'data.harness/v1')),
        enum_fields=(('predicate', ('same_as', 'not_same_as', 'mentions')),),
        state_mappings=(
        ),
    ),
    ContractDefinition(
        slug='semantic-mapping-candidate',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/semantic-mapping-candidate.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/semantic-mapping-candidate.schema.json',
        git_object='83e67efc9cf54c2f4a3510383cb0380d7880528c',
        source_sha256='06396c537a1a378f40d7641263ced091f62b714b157022423ed183756be26dcb',
        allowed_fields=('conceptId', 'confidence', 'lineage', 'mappingId', 'proposedAt', 'rationale', 'schemaDigest', 'schemaVersion', 'status', 'target'),
        required_fields=('conceptId', 'confidence', 'lineage', 'mappingId', 'proposedAt', 'rationale', 'schemaDigest', 'schemaVersion', 'status', 'target'),
        field_types=(
            ('conceptId', ('string',)),
            ('confidence', ('number',)),
            ('lineage', ('array',)),
            ('mappingId', ('string',)),
            ('proposedAt', ('string',)),
            ('rationale', ('string',)),
            ('schemaDigest', ('string',)),
            ('schemaVersion', ('string',)),
            ('status', ('string',)),
            ('target', ('object',)),
        ),
        const_fields=(('schemaVersion', 'data.harness/v1'),),
        enum_fields=(('status', ('proposed', 'approved', 'rejected', 'quarantined')),),
        state_mappings=(
            StateMapping(schema_pointer='/properties/status', values=(('proposed', 'PROPOSED'), ('approved', 'APPROVED'), ('rejected', 'REJECTED'), ('quarantined', 'QUARANTINED'))),
        ),
    ),
    ContractDefinition(
        slug='source-action-capability-profile',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/source-action-capability-profile.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/source-action-capability-profile.schema.json',
        git_object='15d7131f6de78a59de8d279cfb637696266dcc13',
        source_sha256='23bb312e6dd38772cab10e3b4b636a5494d81b5eb829c1e4fe1ada1e2cb113f0',
        allowed_fields=('connectorVersion', 'kind', 'operations', 'schemaVersion', 'sourceId'),
        required_fields=('connectorVersion', 'kind', 'operations', 'schemaVersion', 'sourceId'),
        field_types=(
            ('connectorVersion', ('string',)),
            ('kind', ('string',)),
            ('operations', ('array',)),
            ('schemaVersion', ('string',)),
            ('sourceId', ('string',)),
        ),
        const_fields=(('kind', 'SourceActionCapabilityProfile'), ('schemaVersion', 'data.harness/v1')),
        enum_fields=(),
        state_mappings=(
        ),
    ),
    ContractDefinition(
        slug='source-action-plan',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/source-action-plan.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/source-action-plan.schema.json',
        git_object='c3a808cc79f00826d60d9aa315a64ecc5af16ada',
        source_sha256='d68d6f143879634621e77b6787e3f6eb7ee605d559812a262c88cf8d0611cd9d',
        allowed_fields=('actionId', 'approvalMode', 'assetId', 'compensation', 'idempotencyKey', 'operation', 'parametersDigest', 'preconditionFields', 'preconditionsDigest', 'purpose', 'risk', 'schemaVersion', 'sourceId'),
        required_fields=('actionId', 'approvalMode', 'assetId', 'compensation', 'idempotencyKey', 'operation', 'parametersDigest', 'preconditionFields', 'preconditionsDigest', 'purpose', 'risk', 'schemaVersion', 'sourceId'),
        field_types=(
            ('actionId', ('string',)),
            ('approvalMode', ('string',)),
            ('assetId', ('string',)),
            ('compensation', ()),
            ('idempotencyKey', ('string',)),
            ('operation', ('string',)),
            ('parametersDigest', ('string',)),
            ('preconditionFields', ('array',)),
            ('preconditionsDigest', ('string',)),
            ('purpose', ('string',)),
            ('risk', ('string',)),
            ('schemaVersion', ('string',)),
            ('sourceId', ('string',)),
        ),
        const_fields=(('schemaVersion', 'data.harness/v1'),),
        enum_fields=(('approvalMode', ('none', 'human')), ('risk', ('low', 'medium', 'high'))),
        state_mappings=(
        ),
    ),
    ContractDefinition(
        slug='source-mutation-receipt',
        schema_id='https://prometa.ai/schemas/data-source-harness/v1/source-mutation-receipt.schema.json',
        schema_version='data.harness/v1',
        source_path='schemas/v1/source-mutation-receipt.schema.json',
        git_object='d6deefbbe9054dca650648206c1f57e0dbbcc00e',
        source_sha256='cb24e644364adb7cdcccfe11c76793b5c6162e2af5805ee3fd5acf6a090309bc',
        allowed_fields=('actionDigest', 'actionId', 'auditDigest', 'compensationOf', 'completedAt', 'idempotencyKey', 'policyDecisionId', 'receiptId', 'schemaVersion', 'sourceVersion', 'startedAt', 'state'),
        required_fields=('actionDigest', 'actionId', 'auditDigest', 'compensationOf', 'completedAt', 'idempotencyKey', 'policyDecisionId', 'receiptId', 'schemaVersion', 'sourceVersion', 'startedAt', 'state'),
        field_types=(
            ('actionDigest', ('string',)),
            ('actionId', ('string',)),
            ('auditDigest', ('string',)),
            ('compensationOf', ('string', 'null')),
            ('completedAt', ('string',)),
            ('idempotencyKey', ('string',)),
            ('policyDecisionId', ('string',)),
            ('receiptId', ('string',)),
            ('schemaVersion', ('string',)),
            ('sourceVersion', ('string',)),
            ('startedAt', ('string',)),
            ('state', ('string',)),
        ),
        const_fields=(('schemaVersion', 'data.harness/v1'),),
        enum_fields=(('state', ('executed', 'recovered', 'already-executed', 'compensated', 'failed')),),
        state_mappings=(
            StateMapping(schema_pointer='/properties/state', values=(('executed', 'EXECUTED'), ('recovered', 'RECOVERED'), ('already-executed', 'ALREADY_EXECUTED'), ('compensated', 'COMPENSATED'), ('failed', 'FAILED'))),
        ),
    ),
)


def _definition_index() -> Mapping[str, ContractDefinition]:
    index = {definition.slug: definition for definition in CONTRACT_DEFINITIONS}
    if len(index) != 29 or len(index) != len(CONTRACT_DEFINITIONS):
        raise RuntimeError("compatibility definition set must contain 29 unique contracts")
    for definition in CONTRACT_DEFINITIONS:
        if SLUG_PATTERN.fullmatch(definition.slug) is None:
            raise RuntimeError("compatibility definition contains an invalid slug")
        if not (
            definition.schema_version == "data.harness/v1"
            or (
                definition.schema_version.startswith("data.harness.")
                and definition.schema_version.endswith("/v1")
            )
        ):
            raise RuntimeError(f"compatibility version is invalid: {definition.slug}")
        if definition.source_path != f"schemas/v1/{definition.slug}.schema.json":
            raise RuntimeError(f"compatibility source path is invalid: {definition.slug}")
        if HEX_40.fullmatch(definition.git_object) is None:
            raise RuntimeError(f"compatibility Git object is invalid: {definition.slug}")
        if HEX_64.fullmatch(definition.source_sha256) is None:
            raise RuntimeError(f"compatibility source digest is invalid: {definition.slug}")
        allowed = set(definition.allowed_fields)
        if len(allowed) != len(definition.allowed_fields):
            raise RuntimeError(f"compatibility fields are duplicated: {definition.slug}")
        if not set(definition.required_fields) <= allowed:
            raise RuntimeError(f"compatibility required fields are invalid: {definition.slug}")
        if not {field for field, _ in definition.field_types} <= allowed:
            raise RuntimeError(f"compatibility field types are invalid: {definition.slug}")
        if not {field for field, _ in definition.const_fields} <= allowed:
            raise RuntimeError(f"compatibility constants are invalid: {definition.slug}")
        if dict(definition.const_fields).get("schemaVersion") != definition.schema_version:
            raise RuntimeError(f"compatibility schema version is unpinned: {definition.slug}")
        if not {field for field, _ in definition.enum_fields} <= allowed:
            raise RuntimeError(f"compatibility enums are invalid: {definition.slug}")
    return MappingProxyType(index)


CONTRACTS = _definition_index()


def _state_mapping_document(mapping: StateMapping) -> dict[str, object]:
    return {
        "schemaPointer": mapping.schema_pointer,
        "values": [
            {"legacy": legacy, "canonical": canonical}
            for legacy, canonical in mapping.values
        ],
    }


def mapping_document() -> dict[str, object]:
    """Return the published, deterministic compatibility mapping contract."""

    contracts: list[dict[str, object]] = []
    for definition in CONTRACT_DEFINITIONS:
        contracts.append(
            {
                "contract": definition.slug,
                "supportStatus": "ROUND_TRIP_SUPPORTED",
                "legacySchemaId": definition.schema_id,
                "legacySchemaVersion": definition.schema_version,
                "sourcePath": definition.source_path,
                "sourceGitObject": definition.git_object,
                "sourceSha256": f"sha256:{definition.source_sha256}",
                "allowedFields": list(definition.allowed_fields),
                "requiredFields": list(definition.required_fields),
                "fieldTypes": {
                    field: list(types) for field, types in definition.field_types
                },
                "constFields": dict(definition.const_fields),
                "enumFields": {
                    field: list(values) for field, values in definition.enum_fields
                },
                "stateMappings": [
                    _state_mapping_document(mapping)
                    for mapping in definition.state_mappings
                ],
            }
        )
    return {
        "schemaVersion": MAPPING_SCHEMA_VERSION,
        "apiVersion": API_VERSION,
        "conversionProfile": CONVERSION_PROFILE,
        "observation": {
            "reportSha256": OBSERVATION_SHA256,
            "sourceRepository": SOURCE_REPOSITORY,
            "sourceCommit": SOURCE_COMMIT,
            "sourceCount": 29,
            "copyAuthority": "NONE",
        },
        "fieldMappings": [
            {
                "legacyPointer": "/schemaVersion",
                "canonicalPointer": "/spec/legacySchemaVersion",
                "direction": "BIDIRECTIONAL_EXACT",
            },
            {
                "legacyPointerPattern": "/{topLevelField}",
                "canonicalPointerPattern": "/spec/fields/{topLevelField}",
                "excludes": ["schemaVersion"],
                "direction": "BIDIRECTIONAL_EXACT",
            },
        ],
        "warningCodes": list(WARNING_CODES),
        "intentionalLosses": [
            {
                "code": INTENTIONAL_LOSS_CODES[0],
                "canonicalPointer": "/metadata",
                "reason": "Compatibility provenance is canonical-only and is not a legacy field.",
            },
            {
                "code": INTENTIONAL_LOSS_CODES[1],
                "canonicalPointer": "/spec/normalizedStates",
                "reason": "Normalized state views are derived and are not emitted into legacy JSON.",
            },
        ],
        "contracts": contracts,
    }


def deprecation_document() -> dict[str, object]:
    """Return the closed support window and migration warning contract."""

    return {
        "schemaVersion": DEPRECATION_SCHEMA_VERSION,
        "contractFamily": "data.harness/v1",
        "status": SUPPORT_WINDOW["status"],
        "firstSupportedRelease": SUPPORT_WINDOW["firstSupportedRelease"],
        "supportedSeries": SUPPORT_WINDOW["supportedSeries"],
        "removalNotBeforeRelease": SUPPORT_WINDOW["removalNotBeforeRelease"],
        "minimumNoticeDays": SUPPORT_WINDOW["minimumNoticeDays"],
        "warningCodes": list(WARNING_CODES),
        "replacementApiVersion": API_VERSION,
        "conversionProfile": CONVERSION_PROFILE,
        "supportScope": {
            "contractCount": 29,
            "legacyRoundTrip": "EXACT",
            "canonicalOnlyFieldsReportedAsIntentionalLoss": True,
        },
    }


def _json_type_matches(value: object, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and (not isinstance(value, float) or math.isfinite(value))
        )
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, Mapping)
    return False


def _copy_json(value: object) -> Any:
    return json.loads(canonical_json_bytes(value))


def validate_legacy_document(contract: str, document: Mapping[str, Any]) -> ContractDefinition:
    """Validate the observed root shape without embedding or copying a legacy schema."""

    definition = CONTRACTS.get(contract)
    if definition is None:
        raise CompatibilityError("UNKNOWN_LEGACY_CONTRACT", f"unsupported contract: {contract}")
    fields = set(document)
    missing = sorted(set(definition.required_fields) - fields)
    if missing:
        raise CompatibilityError(
            "LEGACY_REQUIRED_FIELD_MISSING",
            f"{contract} is missing required field {missing[0]}",
        )
    unknown = sorted(fields - set(definition.allowed_fields))
    if unknown:
        raise CompatibilityError(
            "LEGACY_UNKNOWN_FIELD",
            f"{contract} contains unknown field {unknown[0]}",
        )
    for field, expected in definition.const_fields:
        if document.get(field) != expected:
            raise CompatibilityError(
                "LEGACY_CONST_MISMATCH",
                f"{contract}.{field} does not match the observed constant",
            )
    for field, expected in definition.enum_fields:
        if field in document and document[field] not in expected:
            raise CompatibilityError(
                "LEGACY_ENUM_MISMATCH",
                f"{contract}.{field} is outside the observed enum",
            )
    for field, expected_types in definition.field_types:
        if field not in document or not expected_types:
            continue
        if not any(_json_type_matches(document[field], expected) for expected in expected_types):
            raise CompatibilityError(
                "LEGACY_TYPE_MISMATCH",
                f"{contract}.{field} has an incompatible JSON type",
            )
    canonical_json_bytes(document)
    return definition


def _normalized_states(
    definition: ContractDefinition,
    fields: Mapping[str, Any],
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for mapping in definition.state_mappings:
        match = re.fullmatch(r"/properties/([^/]+)", mapping.schema_pointer)
        if match is None:
            continue
        field = match.group(1).replace("~1", "/").replace("~0", "~")
        value = fields.get(field)
        canonical = dict(mapping.values).get(value) if isinstance(value, str) else None
        if canonical is not None:
            result.append(
                {
                    "legacySchemaPointer": mapping.schema_pointer,
                    "legacyValue": value,
                    "canonicalValue": canonical,
                }
            )
    return sorted(result, key=lambda item: item["legacySchemaPointer"])


def convert_legacy_document(contract: str, document: Mapping[str, Any]) -> dict[str, object]:
    """Wrap one validated legacy document in a lossless canonical envelope."""

    definition = validate_legacy_document(contract, document)
    legacy = _copy_json(document)
    fields = {key: value for key, value in legacy.items() if key != "schemaVersion"}
    return {
        "apiVersion": API_VERSION,
        "kind": CANONICAL_KIND,
        "metadata": {
            "contract": definition.slug,
            "conversionProfile": CONVERSION_PROFILE,
            "legacyDocumentDigest": canonical_sha256(legacy),
            "legacySchemaId": definition.schema_id,
            "legacySchemaGitObject": definition.git_object,
            "legacySchemaSha256": f"sha256:{definition.source_sha256}",
            "observationReportSha256": OBSERVATION_SHA256,
        },
        "spec": {
            "legacySchemaVersion": legacy["schemaVersion"],
            "fields": fields,
            "normalizedStates": _normalized_states(definition, fields),
        },
    }


def _intentional_losses() -> list[dict[str, str]]:
    return [
        {
            "code": INTENTIONAL_LOSS_CODES[0],
            "canonicalPointer": "/metadata",
            "reason": "Canonical compatibility provenance is not part of legacy JSON.",
        },
        {
            "code": INTENTIONAL_LOSS_CODES[1],
            "canonicalPointer": "/spec/normalizedStates",
            "reason": "Derived canonical state views are not part of legacy JSON.",
        },
    ]


def restore_legacy_document(canonical: Mapping[str, Any]) -> dict[str, object]:
    """Restore exact legacy JSON and report canonical-only fields intentionally omitted."""

    if set(canonical) != {"apiVersion", "kind", "metadata", "spec"}:
        raise CompatibilityError("CANONICAL_ENVELOPE_INVALID", "canonical envelope fields are closed")
    if canonical.get("apiVersion") != API_VERSION or canonical.get("kind") != CANONICAL_KIND:
        raise CompatibilityError("CANONICAL_ENVELOPE_INVALID", "canonical identity mismatch")
    metadata = canonical.get("metadata")
    spec = canonical.get("spec")
    if not isinstance(metadata, Mapping) or set(metadata) != {
        "contract",
        "conversionProfile",
        "legacyDocumentDigest",
        "legacySchemaId",
        "legacySchemaGitObject",
        "legacySchemaSha256",
        "observationReportSha256",
    }:
        raise CompatibilityError("CANONICAL_ENVELOPE_INVALID", "canonical metadata is not closed")
    if not isinstance(spec, Mapping) or set(spec) != {
        "legacySchemaVersion",
        "fields",
        "normalizedStates",
    }:
        raise CompatibilityError("CANONICAL_ENVELOPE_INVALID", "canonical spec is not closed")
    contract = metadata.get("contract")
    if not isinstance(contract, str) or contract not in CONTRACTS:
        raise CompatibilityError("UNKNOWN_LEGACY_CONTRACT", "canonical contract is unsupported")
    definition = CONTRACTS[contract]
    expected_metadata = {
        "contract": definition.slug,
        "conversionProfile": CONVERSION_PROFILE,
        "legacySchemaId": definition.schema_id,
        "legacySchemaGitObject": definition.git_object,
        "legacySchemaSha256": f"sha256:{definition.source_sha256}",
        "observationReportSha256": OBSERVATION_SHA256,
    }
    for field, expected in expected_metadata.items():
        if metadata.get(field) != expected:
            raise CompatibilityError(
                "CANONICAL_PROVENANCE_MISMATCH",
                f"canonical metadata {field} differs from the mapping authority",
            )
    fields = spec.get("fields")
    if not isinstance(fields, Mapping):
        raise CompatibilityError("CANONICAL_ENVELOPE_INVALID", "canonical fields must be an object")
    legacy: dict[str, Any] = {"schemaVersion": spec.get("legacySchemaVersion")}
    legacy.update(_copy_json(fields))
    validate_legacy_document(contract, legacy)
    if metadata.get("legacyDocumentDigest") != canonical_sha256(legacy):
        raise CompatibilityError("CANONICAL_DOCUMENT_DIGEST_MISMATCH", "canonical fields were changed")
    if spec.get("normalizedStates") != _normalized_states(definition, fields):
        raise CompatibilityError("CANONICAL_STATE_VIEW_MISMATCH", "normalized state view was changed")
    return {
        "document": legacy,
        "report": {
            "accepted": True,
            "contract": contract,
            "direction": "CANONICAL_TO_LEGACY",
            "legacyRoundTrip": "EXACT",
            "warningCodes": list(WARNING_CODES),
            "intentionalLosses": _intentional_losses(),
        },
    }


def round_trip_evidence(contract: str, document: Mapping[str, Any]) -> dict[str, object]:
    """Return digest-only evidence for a complete legacy round trip."""

    canonical = convert_legacy_document(contract, document)
    restored = restore_legacy_document(canonical)
    legacy = _copy_json(document)
    if restored["document"] != legacy:
        raise CompatibilityError("LEGACY_ROUND_TRIP_MISMATCH", "legacy round trip changed the document")
    report = restored["report"]
    assert isinstance(report, dict)
    return {
        **report,
        "direction": "LEGACY_TO_CANONICAL_TO_LEGACY",
        "legacyDocumentDigest": canonical_sha256(legacy),
        "canonicalDocumentDigest": canonical_sha256(canonical),
    }


def _reject_non_finite_json(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _read_json(path: Path) -> object:
    if path.is_symlink() or not path.is_file():
        raise CompatibilityError("FIXTURE_PATH_INVALID", f"fixture is not a regular file: {path.name}")
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_non_finite_json,
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise CompatibilityError(
            "FIXTURE_JSON_INVALID",
            f"fixture is not valid JSON: {path.name}",
        ) from exc


def _fixture_paths(path: Path) -> tuple[Path, ...]:
    if path.is_symlink():
        raise CompatibilityError("FIXTURE_PATH_INVALID", "fixture path must not be a link")
    if path.is_file():
        return (path,)
    if not path.is_dir():
        raise CompatibilityError("FIXTURE_PATH_INVALID", "fixture path does not exist")
    entries = tuple(sorted(path.iterdir(), key=lambda item: item.name))
    if not entries:
        raise CompatibilityError("FIXTURE_PATH_INVALID", "fixture directory is empty")
    for entry in entries:
        if entry.is_symlink() or not entry.is_file() or entry.suffix != ".json":
            raise CompatibilityError("FIXTURE_PATH_INVALID", f"unexpected fixture entry: {entry.name}")
    return entries


def _check_fixture(path: Path) -> dict[str, str]:
    fixture = _read_json(path)
    if not isinstance(fixture, Mapping) or set(fixture) != {
        "schemaVersion",
        "caseId",
        "contract",
        "legacy",
        "expected",
    }:
        raise CompatibilityError("FIXTURE_INVALID", f"fixture fields are closed: {path.name}")
    if fixture.get("schemaVersion") != FIXTURE_SCHEMA_VERSION:
        raise CompatibilityError("FIXTURE_INVALID", f"fixture version mismatch: {path.name}")
    case_id = fixture.get("caseId")
    contract = fixture.get("contract")
    legacy = fixture.get("legacy")
    expected = fixture.get("expected")
    if not isinstance(case_id, str) or SLUG_PATTERN.fullmatch(case_id) is None:
        raise CompatibilityError("FIXTURE_INVALID", f"fixture case ID is invalid: {path.name}")
    if not isinstance(contract, str) or not isinstance(legacy, Mapping):
        raise CompatibilityError("FIXTURE_INVALID", f"fixture contract/document is invalid: {path.name}")
    if not isinstance(expected, Mapping) or set(expected) != {
        "legacyRoundTrip",
        "warningCodes",
        "intentionalLossCodes",
    }:
        raise CompatibilityError("FIXTURE_INVALID", f"fixture expectation is not closed: {path.name}")
    evidence = round_trip_evidence(contract, legacy)
    losses = evidence["intentionalLosses"]
    assert isinstance(losses, list)
    actual = {
        "legacyRoundTrip": evidence["legacyRoundTrip"],
        "warningCodes": evidence["warningCodes"],
        "intentionalLossCodes": [loss["code"] for loss in losses],
    }
    if dict(expected) != actual:
        raise CompatibilityError("FIXTURE_EXPECTATION_MISMATCH", f"fixture evidence differs: {path.name}")
    return {
        "caseId": case_id,
        "contract": contract,
        "legacyDocumentDigest": str(evidence["legacyDocumentDigest"]),
        "canonicalDocumentDigest": str(evidence["canonicalDocumentDigest"]),
    }


def check_fixtures(path: Path) -> dict[str, object]:
    """Check a file or complete flat fixture directory without network access."""

    paths = _fixture_paths(path)
    results = [_check_fixture(fixture_path) for fixture_path in paths]
    case_ids = [result["caseId"] for result in results]
    if len(case_ids) != len(set(case_ids)):
        raise CompatibilityError("DUPLICATE_FIXTURE_CASE", "fixture case IDs must be unique")
    contracts = [result["contract"] for result in results]
    if path.is_dir() and set(contracts) != set(CONTRACTS):
        raise CompatibilityError(
            "FIXTURE_COVERAGE_INCOMPLETE",
            "fixture directory must cover every supported legacy contract",
        )
    return {
        "accepted": True,
        "checked": len(results),
        "supportedContracts": len(CONTRACTS),
        "coverageComplete": set(contracts) == set(CONTRACTS),
        "observationReportSha256": OBSERVATION_SHA256,
        "warningCodes": list(WARNING_CODES),
        "cases": sorted(results, key=lambda item: item["caseId"]),
    }


def compatibility_command(argv: Sequence[str]) -> int:
    """Implement ``harnessctl compatibility check PATH``."""

    parser = argparse.ArgumentParser(prog="harnessctl compatibility")
    subparsers = parser.add_subparsers(dest="action", required=True)
    check_parser = subparsers.add_parser("check", help="check round-trip compatibility fixtures")
    check_parser.add_argument("path", type=Path)
    try:
        arguments = parser.parse_args(tuple(argv))
        if arguments.action != "check":
            raise CompatibilityError("ACTION_UNSUPPORTED", "unsupported compatibility action")
        result = check_fixtures(arguments.path)
    except (CompatibilityError, CompilationError) as exc:
        print(f"compatibility check refused: {exc}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


__all__ = [
    "CompatibilityError",
    "CONTRACTS",
    "convert_legacy_document",
    "restore_legacy_document",
    "round_trip_evidence",
    "mapping_document",
    "deprecation_document",
    "check_fixtures",
    "compatibility_command",
]
