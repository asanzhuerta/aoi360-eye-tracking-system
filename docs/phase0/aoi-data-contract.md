# AOI Data Contract

This document defines the AOI data contract that Unity Phase 0 expects and that the future Python pipeline should produce.

## Goal

Unity should not infer semantic AOIs from visual heuristics at runtime. Instead, it should receive:

1. an AOI map texture
2. a metadata JSON file

Together these define the AOI identity and semantics for each pixel.

## Preferred runtime mode

Preferred mode for future integration:

- `MetadataExactColor`

In this mode:
- each AOI instance is represented by one exact pixel color
- Unity reads the texture pixel color
- Unity maps that color to an `aoi_id` using metadata

This is the mode intended for Grounding DINO + segmentation + tracking outputs.

## Files

### 1. AOI map

Unity-side AOI map:

- equirectangular texture
- one exact color per AOI instance
- black background for non-AOI pixels

Example:

- `#000000` -> background
- `#00FF00` -> AOI 1
- `#FF0000` -> AOI 2

### 2. Metadata JSON

Expected filename:

- `StreamingAssets/AOIMaps/<map_name>_metadata.json`

Expected structure:

```json
{
  "video": "sample360.mp4",
  "fps": 30,
  "idMapResolution": [1920, 960],
  "aois": [
    {
      "id": 1,
      "name": "product_box_left",
      "prompt": "product box",
      "category": "product/box",
      "parentId": 0,
      "color": "#00FF00"
    }
  ]
}
```

## AOI identity model

The runtime is designed around instance-level AOIs.

That means:
- each detected object instance should receive its own `id`
- semantic grouping should happen through metadata, not by reusing the same color for multiple disconnected regions

Recommended interpretation:

- `id` -> instance identity in the runtime
- `name` -> human-readable label for that specific AOI
- `prompt` -> prompt or detector query used offline
- `category` -> semantic grouping for later analysis
- `parentId` -> optional hierarchy if needed later
- `color` -> exact color used in the AOI map

## Why exact color instead of dominant RGB

The older red-versus-green lookup was enough for early tests, but it does not scale to real automated AOI generation.

Exact-color metadata mode is better because it:
- supports many AOIs
- preserves instance identity
- keeps Unity deterministic
- lets the Python pipeline own AOI semantics cleanly

## Texture import requirements

When the AOI map is used as a data texture in Unity, it should be imported with:

- `Read/Write Enabled = On`
- `Generate Mip Maps = Off`
- `Filter Mode = Point`
- `Compression = None`
- `sRGB = Off` when possible for exact data handling

If these settings are not respected, exact color lookup can break.

## Compatibility note

The active runtime path for this phase is the exact-color metadata contract
described above. Older compatibility encodings were useful during early tests,
but they are no longer part of the maintained production flow.
