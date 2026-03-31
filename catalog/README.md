# Catalog Assets

This directory holds the local catalog assets used by the experimental retail matcher.

## Reference Layout

Store packshots or product reference views under:

`catalog/references/<product_id>/`

Example:

`catalog/references/dove-hair-fall-rescue-small/front.jpg`

Recommended views:

- `front.jpg`
- `back.jpg`
- `left.jpg`
- `right.jpg`
- `angle.jpg`

You can also declare `reference_images` directly in
`config/standards/retail_catalog.yaml`, but the default workflow is to place
the assets under the matching `product_id` folder.

## Useful Commands

Audit missing references:

`python scripts/build_retail_index.py --audit-only`

Build the local index:

`python scripts/build_retail_index.py`
