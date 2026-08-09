import argparse
from pathlib import Path

from training.config import CLI_ARGS, build_config


def test_build_config_defaults():
    cfg = build_config(
        argparse.Namespace(
            dataset_dir="data/datasets/synth_demo",
            style="modern",
            output_dir=None,
        )
    )
    assert cfg.dataset_dir == Path("data/datasets/synth_demo")
    assert cfg.style == "modern"
    assert cfg.output_dir == Path("lora_out")
    assert cfg.resolution == 1024
    assert cfg.train_batch_size == 1
    assert cfg.learning_rate == 1e-4
    assert cfg.epochs == 50
    assert cfg.seed == 42


def test_build_config_overrides():
    cfg = build_config(
        argparse.Namespace(
            dataset_dir="ds",
            style="nordic",
            output_dir="out",
            resolution=512,
            train_batch_size=2,
            learning_rate=5e-5,
            epochs=10,
            seed=7,
        )
    )
    assert cfg.output_dir == Path("out")
    assert cfg.resolution == 512
    assert cfg.train_batch_size == 2
    assert cfg.learning_rate == 5e-5
    assert cfg.epochs == 10
    assert cfg.seed == 7


def test_cli_args_include_all_fields():
    parser = argparse.ArgumentParser()
    for names, kwargs in CLI_ARGS:
        parser.add_argument(*names, **kwargs)
    ns = parser.parse_args(
        [
            "--dataset-dir",
            "ds",
            "--style",
            "modern",
            "--output-dir",
            "out",
            "--resolution",
            "512",
            "--train-batch-size",
            "2",
            "--learning-rate",
            "5e-5",
            "--epochs",
            "10",
            "--seed",
            "7",
        ]
    )
    assert ns.dataset_dir == "ds"
    assert ns.style == "modern"
    assert ns.output_dir == "out"
    assert ns.resolution == 512
    assert ns.epochs == 10
