"""
Iris Model Information Parser

Extracts model parameters and quantization from model names.
"""

import re
from dataclasses import dataclass
from typing import Optional
import structlog

logger = structlog.get_logger()


@dataclass
class ModelInfo:
    """Parsed model information."""
    name: str
    params_billions: float  # Model size in billions of parameters
    quantization: str  # Q4, Q8, F16, etc.
    family: str  # llama, mistral, phi, etc.


def parse_model_info(model_name: str) -> ModelInfo:
    """
    Extract model information from model name.

    Handles common naming patterns like:
    - llama-3.2-70b-instruct-q4_k_m
    - mistral-7b-instruct-v0.2-Q8_0
    - phi-3-mini-4k-instruct
    - qwen2.5-72b-instruct-q4_k_m

    Args:
        model_name: The model name/identifier

    Returns:
        ModelInfo with extracted details
    """
    name_lower = model_name.lower()

    params = _extract_params(name_lower)
    quantization = _extract_quantization(name_lower)
    family = _extract_family(name_lower)

    info = ModelInfo(
        name=model_name,
        params_billions=params,
        quantization=quantization,
        family=family
    )

    logger.debug(
        "model_info_parsed",
        name=model_name,
        params_b=params,
        quantization=quantization,
        family=family
    )

    return info


def _extract_params(name: str) -> float:
    """
    Extract parameter count in billions from model name.

    Examples:
        "llama-3.2-70b" -> 70.0
        "mistral-7b" -> 7.0
        "phi-3-mini" -> 3.8 (known model)
        "qwen2.5-72b" -> 72.0
        "gpt-oss-120b" -> 120.0
    """
    # Try direct pattern: number followed by 'b' (billion)
    # Match patterns like "70b", "7b", "3.8b", "0.5b", "120b"
    patterns = [
        r'[-_](\d+\.?\d*)b(?:[-_]|$)',  # -70b- or -70b (end) - most common
        r'(\d+\.?\d*)\s*b(?:illion)?(?:\s|[-_]|$)',  # 70b, 7b, 3.8b
        r'[-_](\d+\.?\d*)b[-_]',  # -70b-, _7b_
        r'(\d+\.?\d*)b[-_]',  # 70b-, 7b_
        r'(\d+)b\b',  # Simple: 120b at word boundary
    ]

    for pattern in patterns:
        match = re.search(pattern, name, re.IGNORECASE)
        if match:
            try:
                value = float(match.group(1))
                logger.debug("params_extracted", name=name, params=value, pattern=pattern)
                return value
            except ValueError:
                continue

    # Known model sizes by name
    known_models = {
        "phi-3-mini": 3.8,
        "phi-3-small": 7.0,
        "phi-3-medium": 14.0,
        "phi-2": 2.7,
        "gemma-2b": 2.0,
        "gemma-7b": 7.0,
        "tinyllama": 1.1,
        "stablelm-zephyr": 3.0,
        "rocket": 3.0,
        "orca-mini": 3.0,
        "gpt-4": 200.0,  # Estimated
        "gpt-3.5": 175.0,  # Estimated
    }

    for known_name, params in known_models.items():
        if known_name in name:
            return params

    # Default to 7B if unknown (most common size)
    logger.debug("params_not_detected", name=name, default=7.0)
    return 7.0


def _extract_quantization(name: str) -> str:
    """
    Extract quantization type from model name.

    Examples:
        "q4_k_m" -> "Q4"
        "Q8_0" -> "Q8"
        "f16" -> "F16"
        "gguf" -> "Q4" (default for GGUF)
    """
    # Quantization patterns (order matters - check specific first)
    quant_patterns = [
        (r'q4[-_]?[kms]', 'Q4'),
        (r'q5[-_]?[kms]', 'Q5'),
        (r'q6[-_]?[kms]', 'Q6'),
        (r'q8[-_]?[kms0]', 'Q8'),
        (r'q3[-_]?[kms]', 'Q3'),
        (r'q2[-_]?[kms]', 'Q2'),
        (r'int4', 'INT4'),
        (r'int8', 'INT8'),
        (r'f32', 'F32'),
        (r'fp32', 'F32'),
        (r'f16', 'F16'),
        (r'fp16', 'F16'),
        (r'bf16', 'BF16'),
        (r'q4', 'Q4'),
        (r'q5', 'Q5'),
        (r'q8', 'Q8'),
    ]

    for pattern, quant_type in quant_patterns:
        if re.search(pattern, name, re.IGNORECASE):
            return quant_type

    # If GGUF format mentioned, default to Q4
    if 'gguf' in name:
        return 'Q4'

    # Default quantization
    logger.debug("quantization_not_detected", name=name, default="Q4")
    return 'Q4'


def _extract_family(name: str) -> str:
    """
    Extract model family from model name.

    Examples:
        "llama-3.2-70b" -> "llama"
        "mistral-7b" -> "mistral"
        "phi-3-mini" -> "phi"
        "gpt-oss-120b" -> "gpt"
    """
    families = [
        'llama',
        'mistral',
        'mixtral',
        'phi',
        'qwen',
        'gemma',
        'falcon',
        'mpt',
        'codellama',
        'deepseek',
        'yi',
        'solar',
        'openchat',
        'zephyr',
        'neural-chat',
        'orca',
        'vicuna',
        'wizardlm',
        'starling',
        'dolphin',
        'nous',
        'tinyllama',
        'stablelm',
        'gpt',
        'claude',
        'command',
        'cohere',
        'internlm',
        'baichuan',
        'chatglm',
        'bloom',
        'opt',
        'pythia',
        'cerebras',
        'rwkv',
    ]

    for family in families:
        if family in name:
            return family

    # Try to extract first word as family
    match = re.match(r'^([a-zA-Z]+)', name)
    if match:
        return match.group(1).lower()

    return 'unknown'


def detect_vision_support(model_name: str) -> bool:
    """
    Detect if a model supports vision/image processing based on its name.

    Many vision-capable models have identifiable patterns in their names.
    This function checks against known vision model families and keywords.

    Args:
        model_name: The model name/identifier

    Returns:
        True if the model likely supports vision/image processing
    """
    name_lower = model_name.lower()

    # Known vision-capable model patterns
    vision_patterns = [
        # LLaVA family - most common vision LLMs
        'llava',
        'llava-1.5',
        'llava-1.6',
        'llava-next',
        'llava-onevision',

        # Qwen vision models
        'qwen-vl',
        'qwen2-vl',
        'qwen2.5-vl',
        'qwenvl',

        # Google Gemma 3 and PaliGemma (vision capable)
        'gemma-3',
        'gemma3',
        'paligemma',

        # MiniCPM-V (vision variant)
        'minicpm-v',
        'minicpm-2.6',
        'minicpm-o',

        # Other vision models
        'idefics',
        'idefics2',
        'idefics3',
        'pixtral',
        'molmo',
        'moondream',
        'cogvlm',
        'cogagent',
        'internvl',
        'internlm-xcomposer',
        'yi-vl',
        'deepseek-vl',
        'phi-3-vision',
        'phi-3.5-vision',
        'phi3-vision',
        'fuyu',
        'bakllava',
        'obsidian',
        'llama-3.2-vision',
        'llama-3.2-11b-vision',
        'llama-3.2-90b-vision',
        'nanollava',

        # Generic vision keywords
        '-vision',
        '_vision',
        '-vl-',
        '-vl_',
        'multimodal',
    ]

    for pattern in vision_patterns:
        if pattern in name_lower:
            logger.info(
                "vision_support_detected",
                model=model_name,
                pattern=pattern
            )
            return True

    return False


def estimate_model_quality_score(info: ModelInfo) -> float:
    """
    Estimate model quality based on parameters and quantization.

    Higher score = better quality potential.

    Args:
        info: Parsed model info

    Returns:
        Quality score from 0 to 100
    """
    score = 0.0

    # Parameter size contribution (0-50 points)
    if info.params_billions >= 70:
        score += 50
    elif info.params_billions >= 30:
        score += 40
    elif info.params_billions >= 13:
        score += 30
    elif info.params_billions >= 7:
        score += 20
    elif info.params_billions >= 3:
        score += 10
    else:
        score += 5

    # Quantization contribution (0-40 points)
    quant_scores = {
        'F32': 40,
        'F16': 38,
        'BF16': 38,
        'Q8': 35,
        'INT8': 32,
        'Q6': 28,
        'Q5': 25,
        'Q4': 20,
        'INT4': 18,
        'Q3': 15,
        'Q2': 10,
    }
    score += quant_scores.get(info.quantization, 20)

    # Family bonus (0-10 points for well-known high-quality families)
    premium_families = ['llama', 'mistral', 'mixtral', 'qwen', 'deepseek', 'gpt', 'claude', 'gemma']
    if info.family in premium_families:
        score += 10

    return min(score, 100.0)
