import hashlib
import mimetypes
import os

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.orm.fields_binary import BinaryValueAttachment
from odoo.tools import split_every
from odoo.tools.osutil import clean_filename


class ImageExportApiLog(models.Model):
    _name = 'image.export.api.log'
    _description = "Image Exported by API"
    _order = 'id desc'
    _rec_name = 'filename'

    model = fields.Char(string="Model", required=True, index=True, readonly=True)
    res_id = fields.Integer(string="Record ID", required=True, readonly=True)
    field_name = fields.Char(string="Image Field", required=True, readonly=True)
    record_name = fields.Char(
        string="Export Name", required=True, readonly=True,
        help="File or folder name given to the record in the model's export folder.",
    )
    filename = fields.Char(
        string="File", required=True, readonly=True,
        help="Path of the exported file, relative to the model's export folder.",
    )
    checksum = fields.Char(string="Checksum", readonly=True)
    export_date = fields.Datetime(string="Exported On", default=fields.Datetime.now, readonly=True)

    _record_field_uniq = models.Constraint(
        'unique(model, res_id, field_name)',
        "An image field of a record can only be logged once.",
    )

    @api.model
    def _get_image_field_names(self, model_name):
        """ Stored image fields of the model, without the resized copies of another field. """
        return [
            name
            for name, field in self.env[model_name]._fields.items()
            if isinstance(field, fields.Image) and field.store and not field.related
        ]

    @api.model
    def _get_export_directory(self, model_name):
        base_path = self.env['ir.config_parameter'].sudo().get_str('model_image_export_api.base_path')
        if not base_path:
            raise UserError(self.env._(
                "No export folder is configured. Set the system parameter 'model_image_export_api.base_path'."
            ))
        folder_name = clean_filename(self.env['ir.model']._get(model_name).with_context(lang='en_US').name)
        return os.path.join(base_path, folder_name)

    @staticmethod
    def _get_image_checksum(image):
        if isinstance(image, BinaryValueAttachment):
            # sha1 of the content, already stored on the attachment
            return image.checksum
        return hashlib.sha1(image.content).hexdigest()

    @staticmethod
    def _get_file_checksum(path):
        with open(path, 'rb') as image_file:
            return hashlib.sha1(image_file.read()).hexdigest()

    @staticmethod
    def _iter_stems(stem):
        """ Yield ``stem``, ``stem (copy)``, ``stem (copy-1)``, ... """
        yield stem
        yield f"{stem} (copy)"
        index = 0
        while True:
            index += 1
            yield f"{stem} (copy-{index})"

    @api.model
    def _export_model_images(self, model_name):
        """ Write the images of all the records of the model to its export
        folder. An image already exported is only written again when it was
        modified, or when its file is gone.

        :return: the export folder, the image fields and the counters of the run
        :rtype: dict
        """
        field_names = self._get_image_field_names(model_name)
        if not field_names:
            raise UserError(self.env._("%(model)s has no image field.", model=model_name))
        directory = self._get_export_directory(model_name)
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as error:
            raise UserError(self.env._(
                "The export folder %(path)s cannot be used: %(error)s",
                path=directory, error=error.strerror,
            ))

        # one folder per record as soon as a record can hold several images
        folder_per_record = len(field_names) > 1
        logs_by_record = {}
        # names given to records by this module, even if the file is gone
        used_stems = set()
        for log in self.search([('model', '=', model_name)]):
            logs_by_record.setdefault(log.res_id, {})[log.field_name] = log
            used_stems.add(log.record_name)

        def get_filename(stem, field_name, extension):
            if folder_per_record:
                return os.path.join(stem, field_name + extension)
            return stem + extension

        Model = self.env[model_name]
        exported = unchanged = without_image = 0
        for record_ids in split_every(100, Model.search([]).ids):
            records = Model.browse(record_ids)
            for record in records:
                record_logs = logs_by_record.get(record.id, {})
                stem = next((log.record_name for log in record_logs.values()), None)
                has_image = False
                for field_name in field_names:
                    image = record[field_name]
                    if not image:
                        continue
                    has_image = True
                    log = record_logs.get(field_name)
                    checksum = self._get_image_checksum(image)
                    if log and log.checksum == checksum and os.path.isfile(os.path.join(directory, log.filename)):
                        unchanged += 1
                        continue
                    extension = mimetypes.guess_extension(image.mimetype or '') or '.png'
                    write_file = True
                    if not stem:
                        for stem in self._iter_stems(clean_filename(record.display_name or '')):
                            if stem in used_stems:
                                continue
                            path = os.path.join(directory, get_filename(stem, field_name, extension))
                            if not os.path.lexists(os.path.join(directory, stem)) and not os.path.lexists(path):
                                break
                            if os.path.isfile(path) and self._get_file_checksum(path) == checksum:
                                # the same image is already there, put by something else
                                write_file = False
                                break
                        used_stems.add(stem)
                    filename = get_filename(stem, field_name, extension)
                    path = os.path.join(directory, filename)
                    try:
                        if write_file:
                            os.makedirs(os.path.dirname(path), exist_ok=True)
                            with open(path, 'wb') as image_file:
                                image_file.write(image.content)
                        if log and log.filename != filename:
                            # the modified image has another format
                            old_path = os.path.join(directory, log.filename)
                            if os.path.isfile(old_path):
                                os.remove(old_path)
                    except OSError as error:
                        raise UserError(self.env._(
                            "The image of %(record)s could not be written to %(path)s: %(error)s",
                            record=record.display_name, path=directory, error=error.strerror,
                        ))
                    values = {
                        'record_name': stem,
                        'filename': filename,
                        'checksum': checksum,
                        'export_date': fields.Datetime.now(),
                    }
                    if log:
                        log.write(values)
                    else:
                        self.create({
                            'model': model_name,
                            'res_id': record.id,
                            'field_name': field_name,
                            **values,
                        })
                    if write_file:
                        exported += 1
                    else:
                        unchanged += 1
                if not has_image:
                    without_image += 1
            records.invalidate_recordset()

        return {
            'folder': directory,
            'image_fields': field_names,
            'exported': exported,
            'unchanged': unchanged,
            'records_without_image': without_image,
        }
