"""CLI wrapper around the official LTX pipeline for project-local rendering.

The upstream command accepts a single checkpoint path. This wrapper keeps the
same official pipeline implementation but passes a checkpoint bundle to
ltx-core so split component files such as text projection, audio VAE, and
optional Video VAE can be loaded together with the selected LTX checkpoint.
"""
from __future__ import annotations

import argparse
import copy
import logging
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Cinematic Console local LTX runner")
    p.add_argument("--pipeline-kind", choices=["hq", "distilled"], default="hq")
    p.add_argument("--checkpoint-path", required=True)
    p.add_argument("--text-projection-path", required=True)
    p.add_argument("--audio-vae-path", required=True)
    p.add_argument("--video-vae-path", default="")
    p.add_argument("--distilled-lora", nargs=2, metavar=("PATH", "STRENGTH"))
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


def _deep_merge_config(left: dict, right: dict) -> dict:
    """Merge split safetensors metadata without clobbering primary config."""
    out = copy.deepcopy(left)
    for key, value in (right or {}).items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge_config(out[key], value)
        elif key not in out or out[key] in ({}, None):
            out[key] = copy.deepcopy(value)
    return out


def _patch_split_checkpoint_loading() -> None:
    """Teach the official builders to read config from every split file.

    The upstream builder reads safetensors metadata from the first checkpoint
    path only. Full checkpoints work as-is, but transformer-only checkpoints
    paired with split text projection / audio VAE / video VAE files need their
    component configs merged into one model config.
    """
    from ltx_core.loader import helpers as loader_helpers
    import ltx_core.block_streaming.builder as streaming_builder
    import ltx_core.loader.single_gpu_model_builder as single_gpu_builder

    original = loader_helpers.read_model_config

    def read_merged_model_config(model_path, loader):  # type: ignore[no-untyped-def]
        if not isinstance(model_path, (tuple, list)):
            return original(model_path, loader)
        merged: dict = {}
        for path in model_path:
            try:
                config = loader.metadata(path) or {}
            except Exception:  # noqa: BLE001
                config = {}
            if config:
                merged = _deep_merge_config(merged, config)
        return merged

    loader_helpers.read_model_config = read_merged_model_config
    single_gpu_builder.read_model_config = read_merged_model_config
    streaming_builder.read_model_config = read_merged_model_config


def _patch_split_video_vae_keys() -> None:
    """Accept both bundled ``vae.*`` and standalone ``encoder/decoder.*`` VAE keys."""
    from ltx_core.loader import SDOps
    import ltx_core.model.video_vae as video_vae_pkg
    import ltx_core.model.video_vae.model_configurator as video_vae_config
    import ltx_pipelines.utils.blocks as blocks

    decoder_ops = (
        SDOps("VAE_DECODER_KEYS_BUNDLED_OR_SPLIT")
        .with_matching(prefix="vae.decoder.")
        .with_matching(prefix="vae.per_channel_statistics.")
        .with_matching(prefix="decoder.")
        .with_matching(prefix="per_channel_statistics.")
        .with_replacement("vae.decoder.", "")
        .with_replacement("decoder.", "")
        .with_replacement("vae.per_channel_statistics.", "per_channel_statistics.")
    )
    encoder_ops = (
        SDOps("VAE_ENCODER_KEYS_BUNDLED_OR_SPLIT")
        .with_matching(prefix="vae.encoder.")
        .with_matching(prefix="vae.per_channel_statistics.")
        .with_matching(prefix="encoder.")
        .with_matching(prefix="per_channel_statistics.")
        .with_replacement("vae.encoder.", "")
        .with_replacement("encoder.", "")
        .with_replacement("vae.per_channel_statistics.", "per_channel_statistics.")
    )

    video_vae_config.VAE_DECODER_COMFY_KEYS_FILTER = decoder_ops
    video_vae_config.VAE_ENCODER_COMFY_KEYS_FILTER = encoder_ops
    video_vae_pkg.VAE_DECODER_COMFY_KEYS_FILTER = decoder_ops
    video_vae_pkg.VAE_ENCODER_COMFY_KEYS_FILTER = encoder_ops
    blocks.VAE_DECODER_COMFY_KEYS_FILTER = decoder_ops
    blocks.VAE_ENCODER_COMFY_KEYS_FILTER = encoder_ops


def _patch_gemma_text_encoder_meta_device() -> None:
    """Keep text-only Gemma encoding off the meta device.

    Comfy/LTX split Gemma checkpoints used for rendering often omit the vision
    tower because the render path only needs the language model hidden states.
    The upstream builder then returns a mixed model: loaded language tensors on
    CUDA/CPU, unused vision tensors on ``meta``. Hugging Face's ``model.device``
    can report ``meta`` in that situation, which makes ``attention_mask`` a meta
    tensor and crashes inside transformers masking utilities.
    """
    import torch
    from ltx_core.text_encoders.gemma.encoders import base_encoder

    GemmaTextEncoder = base_encoder.GemmaTextEncoder
    if getattr(GemmaTextEncoder, "_cinematic_console_meta_patch", False):
        return

    def _tensor_preview(names: list[str], limit: int = 8) -> str:
        preview = ", ".join(names[:limit])
        if len(names) > limit:
            preview += f", ... (+{len(names) - limit} more)"
        return preview

    def _meta_parameters(module: torch.nn.Module, prefix: str = "") -> list[str]:
        return [
            f"{prefix}{name}" if prefix else name
            for name, param in module.named_parameters(recurse=True)
            if str(param.device) == "meta"
        ]

    def _first_real_parameter_device(module: torch.nn.Module) -> torch.device | None:
        for param in module.parameters(recurse=True):
            if str(param.device) != "meta":
                return param.device
        return None

    def _move_real_buffers(module: torch.nn.Module, device: torch.device) -> None:
        for child in module.modules():
            for name, buffer in list(child._buffers.items()):
                if buffer is None or str(buffer.device) == "meta" or buffer.device == device:
                    continue
                child._buffers[name] = buffer.to(device=device)

    def _has_streaming_hooks(module: torch.nn.Module) -> bool:
        layers = getattr(module, "layers", None)
        if not isinstance(layers, torch.nn.ModuleList):
            return False
        return any(bool(getattr(layer, "_forward_pre_hooks", None)) for layer in layers)

    def _language_model(module: object) -> torch.nn.Module:
        model = getattr(module, "model", None)
        inner = getattr(model, "model", None)
        language = getattr(inner, "language_model", None)
        if not isinstance(language, torch.nn.Module):
            raise RuntimeError("Gemma text encoder is invalid: language_model was not found.")
        return language

    def _encoding_device(module: object) -> torch.device:
        language = _language_model(module)
        missing = _meta_parameters(language, "language_model.")
        if missing and not _has_streaming_hooks(language):
            raise RuntimeError(
                "Gemma text encoder weights are incomplete: language_model still has meta parameters. "
                "This usually means TEXT_ENCODER_MODEL points to the wrong file, the file is corrupt, "
                "or the transformers key mapping is incompatible. Re-run install_linux.sh to download "
                "Comfy-Org/ltx-2 split_files/text_encoders/gemma_3_12B_it_fp8_scaled.safetensors. "
                f"Unloaded parameter examples: {_tensor_preview(missing)}"
            )
        device = _first_real_parameter_device(language)
        if device is None:
            raise RuntimeError("Gemma text encoder has no loaded real language_model parameters.")
        _move_real_buffers(language, device)
        return device

    def encode(self, text: str, padding_side: str = "left"):  # type: ignore[no-untyped-def]
        del padding_side
        if self.tokenizer is None:
            raise RuntimeError("Gemma tokenizer is not loaded.")
        device = _encoding_device(self)
        token_pairs = self.tokenizer.tokenize_with_weights(text)["gemma"]
        input_ids = torch.tensor([[t[0] for t in token_pairs]], device=device)
        attention_mask = torch.tensor([[w[1] for w in token_pairs]], device=device)
        outputs = self.model.model(input_ids=input_ids, attention_mask=attention_mask, output_hidden_states=True)
        hidden_states = outputs.hidden_states
        del outputs
        return hidden_states, attention_mask

    def _enhance(self, messages, image=None, max_new_tokens=512, seed=10):  # type: ignore[no-untyped-def]
        if self.processor is None:
            raise RuntimeError("Gemma processor is not loaded.")
        device = _encoding_device(self)
        if image is not None:
            vision = getattr(getattr(self.model, "model", None), "vision_tower", None)
            if isinstance(vision, torch.nn.Module):
                missing_vision = _meta_parameters(vision, "vision_tower.")
                if missing_vision:
                    raise RuntimeError(
                        "The selected render split Gemma text encoder does not include vision tower weights, "
                        "so Gemma image prompt enhancement cannot run with it. Use the bundled llama.cpp "
                        "Prompt Enhancer instead."
                    )
        text = self.processor.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        model_inputs = self.processor(text=text, images=image, return_tensors="pt").to(device)
        pad_token_id = self.processor.tokenizer.pad_token_id if self.processor.tokenizer.pad_token_id is not None else 0
        model_inputs = base_encoder._pad_inputs_for_attention_alignment(model_inputs, pad_token_id=pad_token_id)

        rng_devices = [device] if device.type == "cuda" else []
        with torch.inference_mode(), torch.random.fork_rng(devices=rng_devices):
            torch.manual_seed(seed)
            outputs = self.model.generate(
                **model_inputs,
                max_new_tokens=max_new_tokens,
                do_sample=True,
                temperature=0.7,
            )
            generated_ids = outputs[0][len(model_inputs.input_ids[0]) :]
            return self.processor.tokenizer.decode(generated_ids, skip_special_tokens=True)

    GemmaTextEncoder.encode = encode
    GemmaTextEncoder._enhance = _enhance
    GemmaTextEncoder._cinematic_console_meta_patch = True


def _run(args: argparse.Namespace) -> None:
    import torch

    with torch.inference_mode():
        _run_inference(args)


def _run_inference(args: argparse.Namespace) -> None:
    logging.basicConfig(level=logging.INFO)
    _patch_split_checkpoint_loading()
    _patch_gemma_text_encoder_meta_device()
    from ltx_core.loader import LTXV_LORA_COMFY_RENAMING_MAP, LoraPathStrengthAndSDOps
    from ltx_core.model.video_vae import TilingConfig, get_video_chunks_number
    from ltx_pipelines.distilled import DistilledPipeline
    from ltx_pipelines.ti2vid_two_stages_hq import TI2VidTwoStagesHQPipeline
    from ltx_pipelines.utils.args import ImageConditioningInput
    from ltx_pipelines.utils.constants import LTX_2_3_HQ_PARAMS
    from ltx_pipelines.utils.media_io import encode_video
    from ltx_pipelines.utils.types import OffloadMode

    _patch_split_video_vae_keys()

    quantization = None
    if args.quantization:
        from ltx_pipelines.utils.quantization_factory import QuantizationKind

        quantization = QuantizationKind(args.quantization).to_policy(checkpoint_path=_existing(args.checkpoint_path))

    checkpoint_paths = _checkpoint_bundle(
        args.checkpoint_path,
        args.text_projection_path,
        args.audio_vae_path,
        *( [args.video_vae_path] if args.video_vae_path else [] ),
    )

    loras = tuple(
        LoraPathStrengthAndSDOps(_existing(path), float(strength), LTXV_LORA_COMFY_RENAMING_MAP)
        for path, strength in args.lora
    )
    images = [
        ImageConditioningInput(_existing(path), int(frame), float(strength), int(crf))
        for path, frame, strength, crf in args.image
    ]

    tiling_config = TilingConfig.default()
    video_chunks_number = get_video_chunks_number(args.num_frames, tiling_config)
    if args.pipeline_kind == "distilled":
        pipeline = DistilledPipeline(
            distilled_checkpoint_path=checkpoint_paths,  # type: ignore[arg-type]
            spatial_upsampler_path=_existing(args.spatial_upsampler_path),
            gemma_root=_existing(args.gemma_root),
            loras=loras,  # type: ignore[arg-type]
            quantization=quantization,
            offload_mode=OffloadMode(args.offload),
        )
        video, audio = pipeline(
            prompt=args.prompt,
            seed=args.seed,
            height=args.height,
            width=args.width,
            num_frames=args.num_frames,
            frame_rate=args.frame_rate,
            images=images,
            tiling_config=tiling_config,
        )
    else:
        if not args.distilled_lora:
            raise ValueError("--distilled-lora is required when --pipeline-kind hq")
        distilled_lora = [
            LoraPathStrengthAndSDOps(
                _existing(args.distilled_lora[0]),
                float(args.distilled_lora[1]),
                LTXV_LORA_COMFY_RENAMING_MAP,
            )
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
