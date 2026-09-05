# Image captioning prompt (used during /dhi index)

For each image listed in `pending_captions.json`, read the image file at its
`image_path` with the Read tool, then produce **one combined paragraph** using
this exact instruction:

> Describe what this image shows (chart, diagram, photo, screenshot, etc.),
> including any notable data points, labels, or relationships depicted. Then,
> separately, transcribe any text visible in the image verbatim. Combine both
> into a single paragraph: a description first, followed by "Visible text:"
> and the transcription (omit the "Visible text:" part if the image has no
> legible text).

Keep each caption focused and factual -- it becomes a searchable chunk that
must support answering questions strictly from document content, so avoid
speculation about anything not actually visible in the image.

Do not skip an image because it looks decorative -- images under 80x80 pixels
(icons, bullets, dividers) are already filtered out before reaching this step,
so anything in `pending_captions.json` is assumed to carry real content.
