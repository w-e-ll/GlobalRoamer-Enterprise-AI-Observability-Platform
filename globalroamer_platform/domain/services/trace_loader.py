#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import zipfile

from pathlib import Path

from globalroamer_ai.core.exceptions import TraceLoaderError
from globalroamer_ai.models.operational_models import SourceArtifact

logger = logging.getLogger("trace_loader")


class TraceLoader:
    def __init__(
        self,
        trace_dir: str,
        result_dir: str,
        report_dir: str,
        template_dir: str | None = None,
    ):
        self.trace_dir = Path(trace_dir)
        self.result_dir = Path(result_dir)
        self.report_dir = Path(report_dir)
        self.template_dir = Path(template_dir) if template_dir else None

    def discover(self) -> list[SourceArtifact]:
        logger.info("Discovering testcase artifacts")

        traces = self._discover_traces()
        results = self._discover_results()
        reports = self._discover_reports()

        testcase_ids = sorted(traces.keys())

        artifacts = []

        for testcase_id in testcase_ids:
            artifact = SourceArtifact(
                testcase_id=testcase_id,
                trace_path=traces.get(testcase_id),
                result_path=results.get(testcase_id),
                report_path=reports.get(testcase_id),
                template_path=self._discover_template(),
                template_name=self._guess_template_name(testcase_id),
                campaign_name=self._guess_campaign_name(testcase_id),
                report_type="operational_trace",
                group="globalroamer",
            )

            artifacts.append(artifact)

        logger.info(
            f"Discovered {len(artifacts)} testcase artifacts"
        )

        return artifacts

    def load_trace_rows(self, trace_path: str) -> list[dict]:
        path = Path(trace_path)

        if not path.exists():
            raise TraceLoaderError(
                f"Trace file not found: {trace_path}"
            )

        logger.info(f"Loading trace rows: {path.name}")

        rows = []

        try:
            with open(
                path,
                "r",
                encoding="utf-8",
                errors="replace"
            ) as f:
                lines = f.readlines()

            if not lines:
                return rows

            header = lines[0].strip().split(",")

            for line in lines[1:]:
                values = line.rstrip("\n").split(",")

                row = {}

                for idx, column in enumerate(header):
                    row[column] = values[idx] if idx < len(values) else None

                rows.append(row)

            logger.info(
                f"Loaded {len(rows)} trace rows "
                f"from {path.name}"
            )

            return rows

        except Exception as e:
            logger.error(
                f"Failed loading trace rows "
                f"from {path.name}: {e}"
            )

            raise TraceLoaderError(
                f"Failed loading trace rows: {path}"
            )

    def load_result_log(self, result_path: str) -> str:
        path = Path(result_path)

        if not path.exists():
            raise TraceLoaderError(
                f"Result archive not found: {result_path}"
            )

        logger.info(f"Loading result archive: {path.name}")

        try:
            with zipfile.ZipFile(path, "r") as zf:
                candidates = [
                    name for name in zf.namelist()
                    if "nodejsLog" in name
                    or name.endswith(".log")
                    or name.endswith(".txt")
                ]

                if not candidates:
                    return ""

                selected = candidates[0]

                with zf.open(selected) as f:
                    content = f.read().decode(
                        "utf-8",
                        errors="replace"
                    )

                logger.info(
                    f"Loaded result log "
                    f"from {selected}"
                )

                return content

        except Exception as e:
            logger.error(
                f"Failed loading result archive "
                f"{path.name}: {e}"
            )

            raise TraceLoaderError(
                f"Failed loading result archive: {path}"
            )

    def load_result_archive_entries(
        self,
        result_path: str
    ) -> list[str]:
        path = Path(result_path)

        if not path.exists():
            raise TraceLoaderError(
                f"Result archive not found: {result_path}"
            )

        try:
            with zipfile.ZipFile(path, "r") as zf:
                return zf.namelist()

        except Exception as e:
            logger.error(
                f"Failed reading archive entries "
                f"{path.name}: {e}"
            )

            raise TraceLoaderError(
                f"Failed reading archive entries: {path}"
            )

    def _discover_traces(self) -> dict[str, str]:
        traces = {}

        for path in self.trace_dir.glob("*.csv"):
            testcase_id = self._extract_testcase_id(path.name)

            traces[testcase_id] = str(path)

        return traces

    def _discover_results(self) -> dict[str, str]:
        results = {}

        for path in self.result_dir.glob("*.zip"):
            testcase_id = self._extract_testcase_id(path.name)
            results[testcase_id] = str(path)

        return results

    def _discover_reports(self) -> dict[str, str]:
        reports = {}

        if not self.report_dir:
            return reports

        for path in self.report_dir.glob("*.xlsx"):
            testcase_id = self._extract_testcase_id(path.name)

            reports[testcase_id] = str(path)

        return reports

    def _discover_template(self) -> str | None:
        if not self.template_dir:
            return None

        templates = list(
            self.template_dir.glob("*.xlsx")
        )

        if not templates:
            return None

        return str(templates[0])

    @staticmethod
    def _extract_testcase_id(filename: str) -> str:
        import re

        match = re.search(r"(?:trace|result)[_-](\d{9})", filename, re.IGNORECASE)
        if match:
            return match.group(1)

        match = re.search(r"_(\d{9})_", filename)
        if match:
            return match.group(1)

        match = re.search(r"(\d{9})", filename)
        if match:
            return match.group(1)

        return filename

    @staticmethod
    def _guess_template_name(
        testcase_id: str
    ) -> str:
        if testcase_id.startswith("350"):
            return "IR38_3_3_1"

        return "UNKNOWN"

    @staticmethod
    def _guess_campaign_name(
        testcase_id: str
    ) -> str:
        if testcase_id.startswith("350"):
            return "GSMA_IR38"

        return "GLOBALROAMER"
