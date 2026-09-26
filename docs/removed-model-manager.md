# Removed Model Manager

Model Manager was a standalone panel for inspecting downloaded model resources and runtime caches. It grouped assets by their shared disk paths, showed disk usage and Hugging Face update status, linked resources to the presets that used them, and offered cleanup for model files and unattached caches.

The panel was removed because its aggregate inventory and cleanup view was not useful as a separate workflow. Its screenshot is retained at [`../screenshots/19. Model Manager.png`](../screenshots/19.%20Model%20Manager.png) as a record of the former interface.

The underlying files belong to text presets or Image models lanes. Their existing per-model cleanup controls remain available. Deleting model files can affect other presets or lanes that share those files; they may need to download them again. Cache deletion remains a separate action. Neither operation removes generated gallery media or preset configuration.

Model Manager's aggregate view, manual global update-check action, unattached-cache deletion endpoint, and their manager-only inventory totals were removed. Scheduled model update checks and per-resource update controls remain.
