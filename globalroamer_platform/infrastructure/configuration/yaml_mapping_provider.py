from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from globalroamer_platform.domain.models.mapping_definition import (
    MappingConfiguration,
    MappingDefinition,
)


class MappingConfigurationError(RuntimeError):
    """
    Raised when a mapping configuration file cannot be loaded or validated.
    """


class YamlMappingConfigurationProvider:
    """
    Load and validate trace mapping configuration from YAML.

    Responsibilities:

    - read a YAML file;
    - validate its top-level structure;
    - convert mapping entries into MappingDefinition objects;
    - return an immutable MappingConfiguration.

    The provider does not execute mappings and contains no trace-processing
    business logic.
    """

    def __init__(
        self,
        *,
        path: Path,
    ) -> None:
        normalized_path = Path(path)

        if not str(normalized_path).strip():
            raise ValueError(
                "Mapping configuration path must not be empty"
            )

        self._path = normalized_path
        self._cached_configuration: MappingConfiguration | None = None

    @property
    def path(self) -> Path:
        return self._path

    def get_configuration(
        self,
        *,
        reload: bool = False,
    ) -> MappingConfiguration:
        """
        Return the validated mapping configuration.

        The loaded configuration is cached by default. Pass reload=True
        when the caller explicitly needs to reread the YAML file.
        """

        if (
            self._cached_configuration is not None
            and not reload
        ):
            return self._cached_configuration

        raw_configuration = self._load_yaml()
        configuration = self._build_configuration(
            raw_configuration
        )

        self._cached_configuration = configuration

        return configuration

    def clear_cache(self) -> None:
        """
        Remove the currently cached configuration.
        """

        self._cached_configuration = None

    def _load_yaml(
        self,
    ) -> Mapping[str, Any]:
        if not self._path.exists():
            raise MappingConfigurationError(
                "Mapping configuration file was not found: "
                f"{self._path}"
            )

        if not self._path.is_file():
            raise MappingConfigurationError(
                "Mapping configuration path is not a file: "
                f"{self._path}"
            )

        try:
            with self._path.open(
                mode="r",
                encoding="utf-8",
            ) as configuration_file:
                loaded = yaml.safe_load(
                    configuration_file
                )

        except yaml.YAMLError as exc:
            raise MappingConfigurationError(
                "Invalid YAML in mapping configuration "
                f"{self._path}: {exc}"
            ) from exc

        except OSError as exc:
            raise MappingConfigurationError(
                "Could not read mapping configuration "
                f"{self._path}: {exc}"
            ) from exc

        if loaded is None:
            raise MappingConfigurationError(
                "Mapping configuration file is empty: "
                f"{self._path}"
            )

        if not isinstance(
            loaded,
            Mapping,
        ):
            raise MappingConfigurationError(
                "Mapping configuration root must be a YAML object"
            )

        return loaded

    def _build_configuration(
        self,
        raw_configuration: Mapping[str, Any],
    ) -> MappingConfiguration:
        version = self._optional_string(
            raw_configuration.get(
                "version"
            ),
            field_name="version",
        )

        description = self._optional_string(
            raw_configuration.get(
                "description"
            ),
            field_name="description",
        )

        raw_definitions = raw_configuration.get(
            "mappings"
        )

        if raw_definitions is None:
            raw_definitions = raw_configuration.get(
                "definitions"
            )

        if raw_definitions is None:
            raise MappingConfigurationError(
                "Mapping configuration must contain "
                "'mappings' or 'definitions'"
            )

        if not isinstance(
            raw_definitions,
            list,
        ):
            raise MappingConfigurationError(
                "'mappings' must be a YAML list"
            )

        if not raw_definitions:
            raise MappingConfigurationError(
                "Mapping configuration must contain at least one mapping"
            )

        definitions: list[MappingDefinition] = []

        for index, raw_definition in enumerate(
            raw_definitions,
            start=1,
        ):
            if not isinstance(
                raw_definition,
                Mapping,
            ):
                raise MappingConfigurationError(
                    f"Mapping entry {index} must be a YAML object"
                )

            try:
                definition = MappingDefinition.from_dict(
                    dict(raw_definition)
                )
            except (
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                target_name = raw_definition.get(
                    "target_name",
                    "<unknown>",
                )

                raise MappingConfigurationError(
                    "Invalid mapping entry "
                    f"{index} for target "
                    f"{target_name!r}: {exc}"
                ) from exc

            definitions.append(
                definition
            )

        try:
            return MappingConfiguration(
                definitions=tuple(definitions),
                version=version or "1",
                description=description,
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise MappingConfigurationError(
                f"Invalid mapping configuration: {exc}"
            ) from exc

    @staticmethod
    def _optional_string(
        value: Any,
        *,
        field_name: str,
    ) -> str | None:
        if value is None:
            return None

        if not isinstance(
            value,
            str,
        ):
            raise MappingConfigurationError(
                f"'{field_name}' must be a string"
            )

        normalized = value.strip()

        return normalized or None
