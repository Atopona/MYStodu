"""CLI wrapper around the official LTX pipeline for project-local rendering.

The upstream command accepts a single checkpoint path. This wrapper keeps the
same official pipeline implementation but passes a checkpoint bundle to
ltx-core so split component files such as text projection and audio VAE can be
loaded together with the selected LTX checkpoint.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Cinematic Console local LTX runner")
    p.add_argument("--checkpoint-path", required=True)
    p.add_argument("--text-projection-path", required=True)
    p.add_argument("--audio-vae-path", required=True)
    p.add_argument("--distilled-lora", nargs=2, metavar=("PATH", "STRENGTH"), required=True)
    p.add_argument("--distilled-lora-strength-stage-1", type=float, default=0.25)
    p.add_argument("--distilled-lora-strength-stage-2", type=float, default=0.5)
    p.add_argument("--spatial-upsampler-path", required=True)
    p.add_argument("--gemma-root", required=True)
    p.add_argument("--prompt", required=True)
    p.add_argument("--negative-prompt", default="")
    p.add_argument("--output-path", required=True)
    p.add_argument("--seed", type=int, default=10)
    p.add_argument("--height", type=int, default=704)
    p.add_argument("--width", type=int, default=1216)
    p.add_argument("--num-frames", type=int, default=121)
    p.add_argument("--frame-rate", type=float, default=24.0)
    p.add_argument("--num-inference-steps", type=int, default=15)
    p.add_argument("--offload", choices=["none", "cpu", "disk"], default="none")
    p.add_argument("--max-batch-size", type=int, default=1)
    p.add_argument("--quantization", choices=["fp8-cast", "fp8-scaled-mm"], default="")
    p.add_argument("--image", nargs=4, action="append", metavar=("PATH", "FRAME", "STRENGTH", "CRF"), default=[])
    p.add_argument("--lora", nargs=2, action="append", metavar=("PATH", "STRENGTH"), default=[])
    return p


def _existing(path: str) -> str:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(str(resolved))
    return str(resolved)


def _checkpoint_bundle(*paths: str) -> tuple[str, ...]:
    out = []
    seen = set()
    for path in paths:
        resolved = _existing(path)
        key = resolved.lower()
        if key not in seen:
            seen.add(key)
            out.append(resolved)
    return tuple(out)


def _run(args: argparse.Namespace) -> None:
    import torch

    with torch.inference_mode():
        _run_inference(args)


def _run_inference(args: argparse.Namespace) -> None:
    logging.basicConfig(level=logging.INFO)
    from ltx_core.components.guiders import MultiModalGuiderParams
    from ltx_core.loader import LTXV_LORA_COMFY_RENAMING_MAP, LoraPathStrengthAndSDOps
    from ltx_core.model.video_vae import TilingConfig, get_video_chunks_number
    from ltx_pipelines.ti2vid_two_stages_hq import TI2VidTwoStagesHQPipeline
    from ltx_pipelines.utils.args import ImageConditioningInput
    from ltx_pipelines.utils.constants import LTX_2_3_HQ_PARAMS
    from ltx_pipelines.utils.media_io import encode_video
    from ltx_pipelines.utils.types import OffloadMode

    quantization = None
    if args.quantization:
        from ltx_pipelines.utils.quantization_factory import QuantizationKind

        quantization = QuantizationKind(args.quantization).to_policy(checkpoint_path=_existing(args.checkpoint_path))

    checkpoint_paths = _checkpoint_bundle(
        args.checkpoint_path,
        args.text_projection_path,
        args.audio_vae_path,
    )

    distilled_lora = [
        LoraPathStrengthAndSDOps(
            _existing(args.distilled_lora[0]),
            float(args.distilled_lora[1]),
            LTXV_LORA_COMFY_RENAMING_MAP,
        )
    ]
    loras = tuple(
        LoraPathStrengthAndSDOps(_existing(path), float(strength), LTXV_LORA_COMFY_RENAMING_MAP)
        for path, strength in args.lora
    )
    images = [
        ImageConditioningInput(_existing(path), int(frame), float(strength), int(crf))
        for path, frame, strength, crf in args.image
    ]

    params = LTX_2_3_HQ_PARAMS
    pipeline = TI2VidTwoStagesHQPipeline(
        checkpoint_path=checkpoint_paths,  # type: ignore[arg-type]
        distilled_lora=distilled_lora,
        distilled_lora_strength_stage_1=args.distilled_lora_strength_stage_1,
        distilled_lora_strength_stage_2=args.distilled_lora_strength_stage_2,
        spatial_upsampler_path=_existing(args.spatial_upsampler_path),
        gemma_root=_existing(args.gemma_root),
        loras=loras,
        quantization=quantization,
        offload_mode=OffloadMode(args.offload),
    )

    tiling_config = TilingConfig.default()
    video_chunks_number = get_video_chunks_number(args.num_frames, tiling_config)
    video, audio = pipeline(
        prompt=args.prompt,
        negative_prompt=args.negative_prompt,
        seed=args.seed,
        height=args.height,
        width=args.width,
        num_frames=args.num_frames,
        frame_rate=args.frame_rate,
        num_inference_steps=args.num_inference_steps,
        video_guider_params=params.video_guider_params,
        audio_guider_params=params.audio_guider_params,
        images=images,
        tiling_config=tiling_config,
        max_batch_size=args.max_batch_size,
    )
    encode_video(
        video=video,
        fps=args.frame_rate,
        audio=audio,
        output_path=str(Path(args.output_path).expanduser().resolve()),
        video_chunks_number=video_chunks_number,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = _parser().parse_args()
    _run(args)


if __name__ == "__main__":
    main()
