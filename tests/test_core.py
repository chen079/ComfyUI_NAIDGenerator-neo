import base64
import importlib.util
import io
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch
import zipfile

import requests
import torch
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
package = types.ModuleType("nai_neo_test")
package.__path__ = [str(ROOT)]
comfy = types.ModuleType("comfy")
comfy.utils = types.ModuleType("comfy.utils")
comfy.utils.common_upscale = lambda samples, width, height, method, crop: torch.nn.functional.interpolate(samples, size=(height, width), mode=method, align_corners=False)

with patch.dict(sys.modules, {"nai_neo_test": package, "comfy": comfy, "comfy.utils": comfy.utils}):
    for module_name in ("image_codec", "prompt_syntax", "nai_client", "generation", "nodes"):
        spec = importlib.util.spec_from_file_location(f"nai_neo_test.{module_name}", ROOT / f"{module_name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    image_codec = sys.modules["nai_neo_test.image_codec"]
    nai_client = sys.modules["nai_neo_test.nai_client"]
    generation = sys.modules["nai_neo_test.generation"]
    nodes = sys.modules["nai_neo_test.nodes"]
    prompt_syntax = sys.modules["nai_neo_test.prompt_syntax"]


def image_zip(mode="RGB"):
    image = io.BytesIO()
    Image.new(mode, (64, 64)).save(image, format="PNG")
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("image.png", image.getvalue())
    return archive.getvalue()


class ClientTests(unittest.TestCase):
    def test_vibe_encoding_uses_multipart(self):
        response = Mock(content=b"encoded-vibe")
        with patch.object(requests, "post", return_value=response) as post:
            encoded = nai_client.NovelAIClient("token").encode_vibe(image_codec.image_to_base64(torch.zeros((1, 32, 48, 3))), "nai-diffusion-4-5-full", 0.7, 180)
        self.assertEqual(base64.b64decode(encoded), b"encoded-vibe")
        request = post.call_args.kwargs
        payload = json.loads(request["files"]["request"][1])
        self.assertEqual(payload, {"image": "image", "model": "nai-diffusion-4-5-full", "information_extracted": 0.7})
        self.assertEqual(request["timeout"], 180)

    def test_vibe_encoding_exposes_bounded_server_error(self):
        response = requests.Response()
        response.status_code = 500
        response._content = b'{"statusCode":500,"message":"Invalid reference image"}'
        response.headers["x-correlation-id"] = "abc123"
        with patch.object(requests, "post", return_value=response):
            with self.assertRaisesRegex(requests.HTTPError, "Invalid reference image") as raised:
                nai_client.NovelAIClient("token").encode_vibe(image_codec.image_to_base64(torch.zeros((1, 8, 8, 3))), "nai-diffusion-4-5-full", 0.7)
        self.assertIn("abc123", str(raised.exception))

    def test_token_is_required(self):
        with patch.dict(nai_client.environ, {}, clear=True), patch.object(nai_client.dotenv, "load_dotenv"):
            with self.assertRaisesRegex(RuntimeError, "NAI_ACCESS_TOKEN"):
                nai_client.NovelAIClient.from_environment()


class GenerationTests(unittest.TestCase):
    def build(self, option=None):
        return generation.build_generation_request(832, 1216, "positive", "negative", 28, 5.0, False, False, "none", "k_euler", "native", 123, 1.0, 0.0, True, option)

    def test_encoded_vibes_select_model_and_preserve_order(self):
        vibe = {"model": "nai-diffusion-4-5-full", "encoding": "encoded"}
        model, action, params = self.build({"model": vibe["model"], "encoded_vibe": [(vibe, 0.6), (vibe, 0.2)]})
        self.assertEqual((model, action), (vibe["model"], "generate"))
        self.assertEqual(params["reference_image_multiple"], ["encoded", "encoded"])
        self.assertEqual(params["reference_strength_multiple"], [0.6, 0.2])
        self.assertNotIn("reference_information_extracted_multiple", params)

    def test_raw_vibe_requires_v3(self):
        image = torch.zeros((1, 32, 32, 3))
        with self.assertRaisesRegex(ValueError, "requires EncodeVibe"):
            self.build({"vibe": [(image, 1.0, 0.6)]})
        model, _, params = self.build({"model": "nai-diffusion-3", "vibe": [(image, 0.8, 0.6)]})
        self.assertEqual(model, "nai-diffusion-3")
        self.assertEqual(params["reference_information_extracted_multiple"], [0.8])

    def test_img2img_action_and_free_limits(self):
        image = torch.zeros((1, 32, 32, 3))
        model, action, params = generation.build_generation_request(1600, 1600, "p", "n", 50, 5.0, False, False, "none", "k_euler", "native", 1, 1.0, 0.0, True, {"img2img": (image, 0.7, 0.1)})
        self.assertEqual((model, action), (generation.DEFAULT_MODEL, "img2img"))
        self.assertLessEqual(params["width"] * params["height"], generation.FREE_PIXEL_LIMIT)
        self.assertEqual(params["steps"], 28)


class NodeTests(unittest.TestCase):
    def test_only_neo_node_ids_are_registered(self):
        self.assertTrue(nodes.NODE_CLASS_MAPPINGS)
        self.assertTrue(all(node_id.startswith("NAINeo") for node_id in nodes.NODE_CLASS_MAPPINGS))
        self.assertNotIn("GenerateNAID", nodes.NODE_CLASS_MAPPINGS)
        self.assertEqual(nodes.NAINeoGenerate.RETURN_TYPES, ("IMAGE",))
        self.assertEqual(nodes.NAINeoEncodeVibe.RETURN_TYPES, ("NAI_NEO_VIBE",))

    def test_locales_cover_every_registered_node_and_input(self):
        for language in ("en", "zh"):
            translations = json.loads((ROOT / "locales" / language / "nodeDefs.json").read_text(encoding="utf-8"))
            self.assertEqual(set(translations), set(nodes.NODE_CLASS_MAPPINGS))
            for node_id, node_class in nodes.NODE_CLASS_MAPPINGS.items():
                node_inputs = node_class.INPUT_TYPES()
                input_names = set(node_inputs.get("required", {})) | set(node_inputs.get("optional", {}))
                self.assertEqual(set(translations[node_id].get("inputs", {})), input_names, f"{language}: {node_id}")

    def test_generate_returns_image_without_writing_files(self):
        client = Mock()
        client.generate_image.return_value = image_zip()
        with patch.object(nodes.NovelAIClient, "from_environment", return_value=client):
            node = nodes.NAINeoGenerate()
        image, = node.generate(False, 64, 64, "p", "n", 28, 5.0, False, False, "none", "k_euler", "native", 1, 1.0, 0.0, True)
        self.assertEqual(tuple(image.shape), (1, 64, 64, 3))

    def test_ignore_errors_works_without_masking_original_error(self):
        client = Mock()
        client.generate_image.side_effect = RuntimeError("server failed")
        with patch.object(nodes.NovelAIClient, "from_environment", return_value=client):
            node = nodes.NAINeoGenerate()
        with self.assertRaisesRegex(RuntimeError, "server failed"):
            node.generate(False, 64, 64, "p", "n", 28, 5.0, False, False, "none", "k_euler", "native", 1, 1.0, 0.0, True)
        image, = node.generate(False, 64, 64, "p", "n", 28, 5.0, False, False, "none", "k_euler", "native", 1, 1.0, 0.0, True, {"ignore_errors": True})
        self.assertEqual(tuple(image.shape), (1, 1, 1))


class PromptTests(unittest.TestCase):
    def test_brace_and_numeric_conversion(self):
        self.assertEqual(prompt_syntax.prompt_to_nai("a (cat:1.1)", 0.05, "brace"), "a {{cat}}")
        self.assertEqual(prompt_syntax.prompt_to_nai("(cat:1.2)", 0.05, "numeric"), "1.2::cat ::")
        self.assertEqual(prompt_syntax.prompt_to_nai(r"\(literal\)"), "(literal)")


if __name__ == "__main__":
    unittest.main()
