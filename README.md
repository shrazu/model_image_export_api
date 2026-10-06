# Model Image Export API

Odoo 20 module that exports the images of a model with one HTTP call.

```bash
curl -X POST http://localhost:8069/image_export/hr.employee \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "X-Odoo-Database: your_database"
```

Use the exact technical name of the model. The images of all its records are written to `<base path>/<Model name>/`, for example `Employee/` for `hr.employee`, and the call answers with JSON:

```json
{"model": "hr.employee", "folder": "/opt/odoo/photos/Employee", "image_fields": ["image_1920"],
 "exported": 20, "unchanged": 0, "records_without_image": 0}
```

- An image already exported is written again only if it was modified since the last call, or if its file is gone. Otherwise it is counted as `unchanged`.
- Files are named after the record. Duplicate names get a `(copy)`, `(copy-1)`, … suffix.
- Only real image fields are exported; automatically resized copies (`image_1024`, `image_512`, …) are ignored.
- When a model has several image fields, each record gets its own folder and the files are named after the fields.
- In developer mode, **Settings → Technical → Image Export API → Images Exported by API** lists the files written.

## Authentication

The call needs an API key (scope RPC) of an administrator: **My Preferences → Security → Create API Key**. The `X-Odoo-Database` header is only needed when the server hosts several databases.

| Status | Meaning |
| --- | --- |
| 400 | The model has no image field |
| 401 | Missing or invalid API key |
| 403 | The key does not belong to an administrator |
| 404 | Unknown model |

## Configuration

The base folder is the system parameter `model_image_export_api.base_path` (default `/opt/odoo/photos`). The Odoo server process must be able to write to it.

## Requirements

Odoo 20, `base` module only.

## License

LGPL-3
