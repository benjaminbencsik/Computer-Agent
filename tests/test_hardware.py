from __future__ import annotations

import sys

import pytest

from computer_agent.hardware import HardwareError, HardwareProfile, detect_hardware, recommend_model


def test_usable_gb_uses_vram_when_gpu_present():
    profile = HardwareProfile(has_gpu=True, gpu_name="RTX 4090", vram_gb=24.0, ram_gb=32.0)
    assert profile.usable_gb == 24.0


def test_usable_gb_falls_back_to_ram_without_gpu():
    profile = HardwareProfile(has_gpu=False, gpu_name="", vram_gb=0.0, ram_gb=16.0)
    assert profile.usable_gb == 16.0


@pytest.mark.parametrize(
    ("vram_gb", "expected_model"),
    [
        (24.0, "mistral-small3.1:24b"),
        (18.0, "mistral-small3.1:24b"),
        (17.9, "gemma3:12b"),
        (12.0, "gemma3:12b"),
        (9.0, "gemma3:12b"),
        (8.9, "qwen2.5vl:7b"),
        (6.0, "qwen2.5vl:7b"),
        (5.9, "qwen2.5vl:3b"),
        (2.0, "qwen2.5vl:3b"),
    ],
)
def test_recommend_model_by_gpu_vram_tier(vram_gb, expected_model):
    profile = HardwareProfile(has_gpu=True, gpu_name="Some GPU", vram_gb=vram_gb, ram_gb=32.0)
    assert recommend_model(profile).model == expected_model


def test_recommend_model_cpu_only_with_generous_ram():
    profile = HardwareProfile(has_gpu=False, gpu_name="", vram_gb=0.0, ram_gb=32.0)
    recommendation = recommend_model(profile)
    assert recommendation.model == "qwen2.5vl:7b"
    assert "CPU" in recommendation.reason


def test_recommend_model_cpu_only_with_limited_ram():
    profile = HardwareProfile(has_gpu=False, gpu_name="", vram_gb=0.0, ram_gb=8.0)
    recommendation = recommend_model(profile)
    assert recommendation.model == "qwen2.5vl:3b"


def test_recommendation_reason_mentions_gpu_name():
    profile = HardwareProfile(has_gpu=True, gpu_name="RTX 4090", vram_gb=24.0, ram_gb=32.0)
    assert "RTX 4090" in recommend_model(profile).reason


@pytest.mark.skipif(sys.platform == "win32", reason="asserts the non-Windows error path")
def test_detect_hardware_reports_a_clean_error_off_windows():
    with pytest.raises(HardwareError, match="Windows"):
        detect_hardware()
