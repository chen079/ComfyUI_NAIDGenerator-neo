# Domain context

## NovelAI client

The NovelAI client owns authentication and HTTP request formats for image generation, Vibe encoding, and Director tools. Nodes do not construct HTTP requests.

## Generation request

A generation request combines the Generate node inputs with an optional `NAI_NEO_OPTION` chain. It owns model selection, generation action, resolution limits, sampler adjustments, image inputs, masks, and Vibe references.

## Image codec

The image codec converts between ComfyUI image tensors, PNG data, NovelAI masks, ZIP responses, and supported resolutions.

## Prompt syntax

Prompt syntax converts ComfyUI parenthesis weights into NovelAI brace or numeric weights.

## Workflow identity

The `NAINeo...` class identifiers and `NAI_NEO_...` socket types define this project's workflow format. Legacy identifiers are intentionally not registered; workflows from the original project need their nodes replaced once with the Neo equivalents.
