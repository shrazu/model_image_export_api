import io
import os
import tempfile
from datetime import timedelta

from PIL import Image

from odoo import fields
from odoo.tests import HttpCase, tagged
from odoo.tools import BinaryBytes


@tagged('post_install', '-at_install')
class TestImageExportApi(HttpCase):

    def setUp(self):
        super().setUp()
        base_path = tempfile.TemporaryDirectory()
        self.addCleanup(base_path.cleanup)
        self.env['ir.config_parameter'].set_str('model_image_export_api.base_path', base_path.name)
        self.directory = os.path.join(base_path.name, 'Contact')
        self.api_key = self.env['res.users.apikeys'].with_user(self.env.ref('base.user_admin'))._generate(
            'rpc', 'image export test', None)

    def _image(self, color, image_format='PNG'):
        buffer = io.BytesIO()
        Image.new('RGB', (64, 64), color).save(buffer, image_format)
        return BinaryBytes(buffer.getvalue())

    def _export(self, model='res.partner', api_key=None):
        return self.url_open(
            f'/image_export/{model}', method='POST',
            headers={'Authorization': f'Bearer {api_key or self.api_key}'},
        )

    def _read(self, filename):
        with open(os.path.join(self.directory, filename), 'rb') as image_file:
            return image_file.read()

    def _log(self, partner):
        return self.env['image.export.api.log'].search([('model', '=', 'res.partner'), ('res_id', '=', partner.id)])

    def test_export_then_unchanged_then_modified(self):
        partner = self.env['res.partner'].create({'name': 'Api John', 'image_1920': self._image('#ff0000')})
        first = self._export().json()
        self.assertEqual(first['model'], 'res.partner')
        self.assertEqual(first['folder'], self.directory)
        self.assertEqual(first['image_fields'], ['image_1920'])
        self.assertGreaterEqual(first['exported'], 1)
        self.assertEqual(self._read('Api John.png'), partner.image_1920.content)

        # same image: the file is left alone
        with open(os.path.join(self.directory, 'Api John.png'), 'wb') as image_file:
            image_file.write(b'marker')
        second = self._export().json()
        self.assertEqual(second['exported'], 0)
        self.assertEqual(second['unchanged'], first['exported'])
        self.assertEqual(self._read('Api John.png'), b'marker')

        # modified image: the file is overwritten
        partner.image_1920 = self._image('#0000ff')
        self.env.invalidate_all()
        third = self._export().json()
        self.assertEqual(third['exported'], 1)
        self.assertEqual(self._read('Api John.png'), partner.image_1920.content)
        self.assertEqual(len(self._log(partner)), 1)

    def test_duplicate_names_get_copy_suffix(self):
        partners = self.env['res.partner'].create([
            {'name': 'Api Jane', 'image_1920': self._image(color)} for color in ('#ff0000', '#00ff00', '#0000ff')
        ])
        self._export()
        self.assertEqual(
            sorted(self._log(partner).filename for partner in partners),
            ['Api Jane (copy).png', 'Api Jane (copy-1).png', 'Api Jane.png'],
        )

    def test_same_image_already_in_folder_is_adopted(self):
        partner = self.env['res.partner'].create({'name': 'Api Jane', 'image_1920': self._image('#ff0000')})
        other = self.env['res.partner'].create({'name': 'Api Jim', 'image_1920': self._image('#00ff00')})
        os.makedirs(self.directory)
        with open(os.path.join(self.directory, 'Api Jane.png'), 'wb') as image_file:
            image_file.write(partner.image_1920.content)
        with open(os.path.join(self.directory, 'Api Jim.png'), 'wb') as image_file:
            image_file.write(b'another image')
        self._export()
        # same content: the file is taken over, no copy is made
        self.assertEqual(self._log(partner).filename, 'Api Jane.png')
        self.assertFalse(os.path.exists(os.path.join(self.directory, 'Api Jane (copy).png')))
        # other content: the file is not ours, it is left alone
        self.assertEqual(self._log(other).filename, 'Api Jim (copy).png')
        self.assertEqual(self._read('Api Jim.png'), b'another image')

    def test_deleted_file_is_exported_again(self):
        partner = self.env['res.partner'].create({'name': 'Api Jane', 'image_1920': self._image('#ff0000')})
        self._export()
        os.remove(os.path.join(self.directory, 'Api Jane.png'))
        self.assertEqual(self._export().json()['exported'], 1)
        self.assertEqual(self._read('Api Jane.png'), partner.image_1920.content)

    def test_errors(self):
        self.assertEqual(self._export('no.such.model').status_code, 404)
        response = self._export('res.currency.rate')
        self.assertEqual(response.status_code, 400)
        self.assertIn('no image field', response.json()['error'])
        self.assertEqual(self._export(api_key='wrong').status_code, 401)
        self.assertEqual(self.url_open('/image_export/res.partner').status_code, 405)

    def test_requires_administrator(self):
        user = self.env['res.users'].create({
            'name': 'Api User', 'login': 'api_user', 'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        api_key = self.env['res.users.apikeys'].with_user(user)._generate(
            'rpc', 'image export test', fields.Datetime.now() + timedelta(days=1))
        self.assertEqual(self._export(api_key=api_key).status_code, 403)
