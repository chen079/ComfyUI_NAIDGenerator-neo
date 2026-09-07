from .image_codec import calculate_resolution, calculate_skip_cfg_above_sigma, image_to_base64, mask_to_base64, resize_image, resize_mask


DEFAULT_MODEL = "nai-diffusion-4-5-full"
FREE_PIXEL_LIMIT = 1024 * 1024


def build_generation_request(width, height, positive, negative, steps, cfg, decrisper, variety, smea, sampler, scheduler, seed, uncond_scale, cfg_rescale, limit_opus_free, option=None):
    width, height = calculate_resolution(width * height, (width, height))
    params = {
        "params_version": 1,
        "width": width,
        "height": height,
        "scale": cfg,
        "sampler": sampler,
        "steps": steps,
        "seed": seed,
        "n_samples": 1,
        "ucPreset": 3,
        "qualityToggle": False,
        "sm": smea in ("SMEA", "SMEA+DYN") and sampler != "ddim",
        "sm_dyn": smea == "SMEA+DYN" and sampler != "ddim",
        "dynamic_thresholding": decrisper,
        "skip_cfg_above_sigma": None,
        "controlnet_strength": 1.0,
        "legacy": False,
        "add_original_image": False,
        "cfg_rescale": cfg_rescale,
        "noise_schedule": scheduler,
        "legacy_v3_extend": False,
        "uncond_scale": uncond_scale,
        "negative_prompt": negative,
        "prompt": positive,
        "reference_image_multiple": [],
        "reference_information_extracted_multiple": [],
        "reference_strength_multiple": [],
        "extra_noise_seed": seed,
        "v4_prompt": {"use_coords": False, "use_order": False, "caption": {"base_caption": positive, "char_captions": []}},
        "v4_negative_prompt": {"use_coords": False, "use_order": False, "caption": {"base_caption": negative, "char_captions": []}},
    }
    model = option.get("model", DEFAULT_MODEL) if option else DEFAULT_MODEL
    action = "generate"

    if sampler == "k_euler_ancestral" and scheduler != "native":
        params["deliberate_euler_ancestral_bug"] = False
        params["prefer_brownian"] = True

    if option:
        if "img2img" in option:
            action = "img2img"
            image, strength, noise = option["img2img"]
            params.update(image=image_to_base64(resize_image(image, (width, height))), strength=strength, noise=noise)
        elif "infill" in option:
            action = "infill"
            image, mask, add_original_image = option["infill"]
            params["image"] = image_to_base64(resize_image(image, (width, height)))
            params["mask"] = mask_to_base64(resize_mask(mask, (width, height), "4" in model))
            params["add_original_image"] = add_original_image

        raw_vibes = option.get("vibe", [])
        if raw_vibes and model.startswith("nai-diffusion-4"):
            raise ValueError("V4/V4.5 Vibe Transfer requires EncodeVibe. Connect its output to encoded_vibe instead of image.")
        for image, information_extracted, strength in raw_vibes:
            params["reference_image_multiple"].append(image_to_base64(resize_image(image, (width, height))))
            params["reference_information_extracted_multiple"].append(information_extracted)
            params["reference_strength_multiple"].append(strength)

        encoded_vibes = option.get("encoded_vibe", [])
        for vibe, strength in encoded_vibes:
            if vibe["model"] != model:
                raise ValueError("The vibe encoding model must match the generation model.")
            params["reference_image_multiple"].append(vibe["encoding"])
            params["reference_strength_multiple"].append(strength)
        if encoded_vibes:
            del params["reference_information_extracted_multiple"]

        if "v4_prompt" in option:
            params["v4_prompt"].update(option["v4_prompt"])

    if limit_opus_free:
        if width * height > FREE_PIXEL_LIMIT:
            params["width"], params["height"] = calculate_resolution(FREE_PIXEL_LIMIT, (width, height))
        params["steps"] = min(steps, 28)
    if variety:
        params["skip_cfg_above_sigma"] = calculate_skip_cfg_above_sigma(params["width"], params["height"])
    if sampler == "ddim" and model != "nai-diffusion-2":
        params["sampler"] = "ddim_v3"
    if action == "infill" and model != "nai-diffusion-2":
        model = f"{model}-inpainting"

    return model, action, params
