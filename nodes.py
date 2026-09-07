import copy

from .generation import DEFAULT_MODEL, FREE_PIXEL_LIMIT, build_generation_request
from .image_codec import blank_image, bytes_to_image, calculate_resolution, first_image_from_zip, image_to_base64, resize_image, resize_mask
from .nai_client import NovelAIClient
from .prompt_syntax import prompt_to_nai


CATEGORY = "NAI Neo"
V4_MODELS = ["nai-diffusion-4-curated-preview", "nai-diffusion-4-full", "nai-diffusion-4-5-curated", "nai-diffusion-4-5-full"]
MODELS = ["nai-diffusion-2", "nai-diffusion-furry-3", "nai-diffusion-3", *V4_MODELS]
LIMIT_OPUS_FREE = "Limit image size and steps for free Opus generation."


def _option(value):
    return copy.deepcopy(value) if value else {}


class NAINeoPrompt:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "text": ("STRING", {"forceInput": True, "multiline": True, "dynamicPrompts": False}),
            "weight_per_brace": ("FLOAT", {"default": 0.05, "min": 0.05, "max": 0.10, "step": 0.05}),
            "syntax_mode": (["brace", "numeric"], {"default": "brace"}),
        }}

    RETURN_TYPES = ("STRING",)
    FUNCTION = "convert"
    CATEGORY = f"{CATEGORY}/utils"

    def convert(self, text, weight_per_brace, syntax_mode):
        return (prompt_to_nai(text, weight_per_brace, syntax_mode),)


class NAINeoMaskImage:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE",)}}

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "convert"
    CATEGORY = f"{CATEGORY}/utils"

    def convert(self, image):
        return (resize_mask(image),)


class NAINeoModelOption:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model": (MODELS, {"default": DEFAULT_MODEL})}, "optional": {"option": ("NAI_NEO_OPTION",)}}

    RETURN_TYPES = ("NAI_NEO_OPTION",)
    FUNCTION = "set_option"
    CATEGORY = CATEGORY

    def set_option(self, model, option=None):
        result = _option(option)
        result["model"] = model
        return (result,)


class NAINeoImg2ImgOption:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE",),
            "strength": ("FLOAT", {"default": 0.70, "min": 0.01, "max": 0.99, "step": 0.01, "display": "number"}),
            "noise": ("FLOAT", {"default": 0.00, "min": 0.00, "max": 0.99, "step": 0.02, "display": "number"}),
        }}

    RETURN_TYPES = ("NAI_NEO_OPTION",)
    FUNCTION = "set_option"
    CATEGORY = CATEGORY

    def set_option(self, image, strength, noise):
        return ({"img2img": (image, strength, noise)},)


class NAINeoInpaintingOption:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE",), "mask": ("IMAGE",), "add_original_image": ("BOOLEAN", {"default": True})}}

    RETURN_TYPES = ("NAI_NEO_OPTION",)
    FUNCTION = "set_option"
    CATEGORY = CATEGORY

    def set_option(self, image, mask, add_original_image):
        return ({"infill": (image, mask, add_original_image)},)


class NAINeoEncodeVibe:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE",),
            "model": (V4_MODELS, {"default": DEFAULT_MODEL}),
            "information_extracted": ("FLOAT", {"default": 0.7, "min": 0.01, "max": 1.0, "step": 0.01, "display": "number", "tooltip": "Changing this value requires a new paid encoding."}),
            "timeout_sec": ("INT", {"default": 120, "min": 30, "max": 3000, "step": 1}),
        }}

    RETURN_TYPES = ("NAI_NEO_VIBE",)
    RETURN_NAMES = ("encoded_vibe",)
    FUNCTION = "encode"
    CATEGORY = CATEGORY

    def __init__(self):
        self.client = NovelAIClient.from_environment()

    def encode(self, image, model, information_extracted, timeout_sec):
        if image.shape[0] != 1:
            raise ValueError("NAI Neo Encode Vibe accepts exactly one image.")
        encoding = self.client.encode_vibe(image_to_base64(image), model, information_extracted, timeout_sec)
        return ({"model": model, "encoding": encoding},)


class NAINeoVibeTransferOption:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "information_extracted": ("FLOAT", {"default": 1.0, "min": 0.01, "max": 1.0, "step": 0.01, "display": "number", "tooltip": "Used only with a raw V3 reference image."}),
                "strength": ("FLOAT", {"default": 0.6, "min": 0.01, "max": 1.0, "step": 0.01, "display": "number"}),
            },
            "optional": {"image": ("IMAGE",), "option": ("NAI_NEO_OPTION",), "encoded_vibe": ("NAI_NEO_VIBE",)},
        }

    RETURN_TYPES = ("NAI_NEO_OPTION",)
    FUNCTION = "set_option"
    CATEGORY = CATEGORY

    def set_option(self, information_extracted=1.0, strength=0.6, image=None, option=None, encoded_vibe=None):
        result = _option(option)
        if encoded_vibe is not None:
            if image is not None:
                raise ValueError("Connect either image or encoded_vibe, not both.")
            if result.get("model", encoded_vibe["model"]) != encoded_vibe["model"]:
                raise ValueError("The Vibe encoding model must match the generation model.")
            result["model"] = encoded_vibe["model"]
            result.setdefault("encoded_vibe", []).append((encoded_vibe, strength))
            return (result,)
        if image is None:
            raise ValueError("Connect an image or encoded_vibe.")
        result.setdefault("vibe", []).append((image, information_extracted, strength))
        return (result,)


class NAINeoNetworkOption:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "ignore_errors": ("BOOLEAN", {"default": True}),
                "timeout_sec": ("INT", {"default": 120, "min": 30, "max": 3000, "step": 1, "display": "number"}),
                "retry": ("INT", {"default": 3, "min": 1, "max": 100, "step": 1, "display": "number"}),
            },
            "optional": {"option": ("NAI_NEO_OPTION",)},
        }

    RETURN_TYPES = ("NAI_NEO_OPTION",)
    FUNCTION = "set_option"
    CATEGORY = CATEGORY

    def set_option(self, ignore_errors, timeout_sec, retry, option=None):
        result = _option(option)
        result.update(ignore_errors=ignore_errors, timeout=timeout_sec, retry=retry)
        return (result,)


class NAINeoGenerate:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "limit_opus_free": ("BOOLEAN", {"default": True, "tooltip": LIMIT_OPUS_FREE}),
                "width": ("INT", {"default": 832, "min": 64, "max": 1600, "step": 64, "display": "number"}),
                "height": ("INT", {"default": 1216, "min": 64, "max": 1600, "step": 64, "display": "number"}),
                "positive": ("STRING", {"default": ", best quality, amazing quality, very aesthetic, absurdres", "multiline": True, "dynamicPrompts": False}),
                "negative": ("STRING", {"default": "lowres", "multiline": True, "dynamicPrompts": False}),
                "steps": ("INT", {"default": 28, "min": 0, "max": 50, "step": 1, "display": "number"}),
                "cfg": ("FLOAT", {"default": 5.0, "min": 0.0, "max": 10.0, "step": 0.1, "display": "number"}),
                "variety": ("BOOLEAN", {"default": False}),
                "decrisper": ("BOOLEAN", {"default": False}),
                "smea": (["none", "SMEA", "SMEA+DYN"], {"default": "none"}),
                "sampler": (["k_euler", "k_euler_ancestral", "k_dpmpp_2s_ancestral", "k_dpmpp_2m_sde", "k_dpmpp_2m", "k_dpmpp_sde", "ddim"], {"default": "k_euler"}),
                "scheduler": (["native", "karras", "exponential", "polyexponential"], {"default": "native"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 9999999999, "step": 1, "display": "number"}),
                "uncond_scale": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.5, "step": 0.05}),
                "cfg_rescale": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.02}),
                "keep_alpha": ("BOOLEAN", {"default": True}),
            },
            "optional": {"option": ("NAI_NEO_OPTION",)},
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "generate"
    CATEGORY = CATEGORY

    def __init__(self):
        self.client = NovelAIClient.from_environment()

    def generate(self, limit_opus_free, width, height, positive, negative, steps, cfg, decrisper, variety, smea, sampler, scheduler, seed, uncond_scale, cfg_rescale, keep_alpha, option=None):
        model, action, params = build_generation_request(width, height, positive, negative, steps, cfg, decrisper, variety, smea, sampler, scheduler, seed, uncond_scale, cfg_rescale, limit_opus_free, option)
        try:
            archive = self.client.generate_image(positive, model, action, params, option.get("timeout") if option else None, option.get("retry") if option else None)
            return (bytes_to_image(first_image_from_zip(archive), keep_alpha),)
        except Exception as error:
            if option and option.get("ignore_errors"):
                print(f"NAI Neo ignored generation error: {error}")
                return (blank_image(),)
            raise


def _director_inputs(extra=None):
    required = {
        "image": ("IMAGE",),
        "limit_opus_free": ("BOOLEAN", {"default": True, "tooltip": LIMIT_OPUS_FREE}),
        "ignore_errors": ("BOOLEAN", {"default": False}),
    }
    if extra:
        required.update(extra)
    return {"required": required}


class _DirectorNode:
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "augment"
    CATEGORY = f"{CATEGORY}/director_tools"

    @classmethod
    def INPUT_TYPES(cls):
        return _director_inputs()

    def __init__(self):
        self.client = NovelAIClient.from_environment()

    def run(self, image, limit_opus_free, ignore_errors, req_type, options=None):
        height, width = image.shape[1:3]
        if limit_opus_free and width * height > FREE_PIXEL_LIMIT:
            width, height = calculate_resolution(FREE_PIXEL_LIMIT, (width, height))
        encoded = image_to_base64(resize_image(image, (width, height)))
        try:
            archive = self.client.augment_image(req_type, width, height, encoded, options)
            return (bytes_to_image(first_image_from_zip(archive)),)
        except Exception as error:
            if ignore_errors:
                print(f"NAI Neo ignored Director error: {error}")
                return (blank_image(),)
            raise


class NAINeoRemoveBG(_DirectorNode):
    def augment(self, image, limit_opus_free, ignore_errors):
        return self.run(image, limit_opus_free, ignore_errors, "bg-removal")


class NAINeoLineArt(_DirectorNode):
    def augment(self, image, limit_opus_free, ignore_errors):
        return self.run(image, limit_opus_free, ignore_errors, "lineart")


class NAINeoSketch(_DirectorNode):
    def augment(self, image, limit_opus_free, ignore_errors):
        return self.run(image, limit_opus_free, ignore_errors, "sketch")


class NAINeoColorize(_DirectorNode):
    @classmethod
    def INPUT_TYPES(cls):
        return _director_inputs({
            "defry": ("INT", {"default": 0, "min": 0, "max": 5, "step": 1}),
            "prompt": ("STRING", {"default": "", "multiline": True, "dynamicPrompts": False}),
        })

    def augment(self, image, limit_opus_free, ignore_errors, defry, prompt):
        return self.run(image, limit_opus_free, ignore_errors, "colorize", {"defry": defry, "prompt": prompt})


class NAINeoEmotion(_DirectorNode):
    STRENGTHS = ["normal", "slightly_weak", "weak", "even_weaker", "very_weak", "weakest"]
    MOODS = ["neutral", "happy", "sad", "angry", "scared", "surprised", "tired", "excited", "nervous", "thinking", "confused", "shy", "disgusted", "smug", "bored", "laughing", "irritated", "aroused", "embarrassed", "worried", "love", "determined", "hurt", "playful"]

    @classmethod
    def INPUT_TYPES(cls):
        return _director_inputs({
            "mood": (cls.MOODS, {"default": "neutral"}),
            "strength": (cls.STRENGTHS, {"default": "normal"}),
            "prompt": ("STRING", {"default": "", "multiline": True, "dynamicPrompts": False}),
        })

    def augment(self, image, limit_opus_free, ignore_errors, mood, strength, prompt):
        options = {"defry": self.STRENGTHS.index(strength), "prompt": f"{mood};;{prompt}"}
        return self.run(image, limit_opus_free, ignore_errors, "emotion", options)


class NAINeoDeclutter(_DirectorNode):
    def augment(self, image, limit_opus_free, ignore_errors):
        return self.run(image, limit_opus_free, ignore_errors, "declutter")


class NAINeoV4BasePrompt:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"base_caption": ("STRING", {"multiline": True})}}

    RETURN_TYPES = ("STRING",)
    FUNCTION = "convert"
    CATEGORY = f"{CATEGORY}/v4"

    def convert(self, base_caption):
        return (base_caption,)


class NAINeoV4NegativePrompt:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"negative_caption": ("STRING", {"multiline": True})}}

    RETURN_TYPES = ("STRING",)
    FUNCTION = "convert"
    CATEGORY = f"{CATEGORY}/v4"

    def convert(self, negative_caption):
        return (negative_caption,)


NODE_CLASS_MAPPINGS = {
    "NAINeoGenerate": NAINeoGenerate,
    "NAINeoModelOption": NAINeoModelOption,
    "NAINeoImg2ImgOption": NAINeoImg2ImgOption,
    "NAINeoInpaintingOption": NAINeoInpaintingOption,
    "NAINeoVibeTransferOption": NAINeoVibeTransferOption,
    "NAINeoEncodeVibe": NAINeoEncodeVibe,
    "NAINeoNetworkOption": NAINeoNetworkOption,
    "NAINeoMaskImage": NAINeoMaskImage,
    "NAINeoPrompt": NAINeoPrompt,
    "NAINeoRemoveBG": NAINeoRemoveBG,
    "NAINeoLineArt": NAINeoLineArt,
    "NAINeoSketch": NAINeoSketch,
    "NAINeoColorize": NAINeoColorize,
    "NAINeoEmotion": NAINeoEmotion,
    "NAINeoDeclutter": NAINeoDeclutter,
    "NAINeoV4BasePrompt": NAINeoV4BasePrompt,
    "NAINeoV4NegativePrompt": NAINeoV4NegativePrompt,
}

NODE_DISPLAY_NAME_MAPPINGS = {node_id: node_id.replace("NAINeo", "NAI Neo · ") for node_id in NODE_CLASS_MAPPINGS}
