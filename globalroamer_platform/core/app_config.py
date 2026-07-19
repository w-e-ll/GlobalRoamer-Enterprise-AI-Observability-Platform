#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import yaml
import logging

from dataclasses import dataclass
from dotenv import load_dotenv

logger = logging.getLogger("app_config")

load_dotenv()


@dataclass
class AppConfig:
    env: str

    base_dir: str

    input_trace_dir: str
    input_result_dir: str
    input_report_dir: str
    input_template_dir: str
    input_campaign_dir: str

    normalized_dir: str
    chunks_dir: str
    embeddings_dir: str
    vector_db_dir: str

    ai_summary_dir: str
    root_cause_dir: str
    campaign_health_dir: str

    log_dir: str

    embedding_model: str
    llm_model: str
    chunk_size: int
    chunk_overlap: int

    vector_collection: str


def expand(value: str, base_dir: str) -> str:
    return value.replace("${base_dir}", base_dir)


def load_yaml_config(config_dir: str) -> AppConfig:
    config_path = os.path.join(
        config_dir,
        "globalroamer_ai_config.yml"
    )

    if not os.path.isfile(config_path):
        raise FileNotFoundError(
            f"Config not found: {config_path}"
        )

    logger.info(f"Loading config: {config_path}")

    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f)

    base_dir = cfg["paths"]["base_dir"]

    return AppConfig(
        env=cfg["env"],

        base_dir=base_dir,

        input_trace_dir=expand(
            cfg["paths"]["input_trace_dir"],
            base_dir
        ),
        input_result_dir=expand(
            cfg["paths"]["input_result_dir"],
            base_dir
        ),
        input_report_dir=expand(
            cfg["paths"]["input_report_dir"],
            base_dir
        ),
        input_template_dir=expand(
            cfg["paths"]["input_template_dir"],
            base_dir
        ),
        input_campaign_dir=expand(
            cfg["paths"]["input_campaign_dir"],
            base_dir
        ),

        normalized_dir=expand(
            cfg["paths"]["normalized_dir"],
            base_dir
        ),
        chunks_dir=expand(
            cfg["paths"]["chunks_dir"],
            base_dir
        ),
        embeddings_dir=expand(
            cfg["paths"]["embeddings_dir"],
            base_dir
        ),
        vector_db_dir=expand(
            cfg["paths"]["vector_db_dir"],
            base_dir
        ),

        ai_summary_dir=expand(
            cfg["paths"]["ai_summary_dir"],
            base_dir
        ),
        root_cause_dir=expand(
            cfg["paths"]["root_cause_dir"],
            base_dir
        ),
        campaign_health_dir=expand(
            cfg["paths"]["campaign_health_dir"],
            base_dir
        ),

        log_dir=expand(
            cfg["paths"]["log_dir"],
            base_dir
        ),

        embedding_model=cfg["ai"]["embedding_model"],
        llm_model=cfg["ai"]["llm_model"],
        chunk_size=cfg["ai"]["chunk_size"],
        chunk_overlap=cfg["ai"]["chunk_overlap"],

        vector_collection=cfg["vector_db"]["collection_name"],
    )
