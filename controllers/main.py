from odoo import http
from odoo.exceptions import UserError
from odoo.http import request


class ModelImageExportController(http.Controller):

    @http.route(
        '/image_export/<string:model>', type='http', auth='bearer', bearer_scope='rpc',
        methods=['POST'], csrf=False, save_session=False,
    )
    def export_model_images(self, model):
        if not request.env.user.has_group('base.group_system'):
            return self._error(403, "Only administrators can export images.")
        ir_model = request.env['ir.model'].search([
            ('model', '=', model), ('transient', '=', False), ('abstract', '=', False),
        ])
        if not ir_model:
            return self._error(404, f"Unknown model: {model}")
        try:
            result = request.env['image.export.api.log']._export_model_images(model)
        except UserError as error:
            return self._error(400, str(error))
        return request.make_json_response({'model': model, **result})

    def _error(self, status, message):
        return request.make_json_response({'error': message}, status=status)
